"""FastAPI web interface for the subway agent."""

import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from .agent import chat, clear_history
from .stations import find_station, STATIONS
from .mta_feed import get_arrivals
from .routing import find_route
from .database import db

STATIC_DIR = Path(__file__).parent / "static"

# Comma-separated, so several keys can be valid at once. The iOS app compiles
# its key into the binary, so a single accepted key makes rotation a hard
# cutover: change it and every already-installed build starts getting 401s.
# Accepting a list allows add-new -> ship the app -> drop-old, with no moment
# where a shipped build is broken.
SUBWAY_API_KEYS = [
    k.strip() for k in (os.getenv("SUBWAY_API_KEY") or "").split(",") if k.strip()
]


async def verify_api_key(
    key: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None),
):
    """Verify API key from query param or header."""
    provided_key = key or x_api_key
    # compare_digest keeps the check constant-time, so responses do not leak
    # how much of a guessed key was right.
    if not provided_key or not any(
        secrets.compare_digest(provided_key, valid) for valid in SUBWAY_API_KEYS
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return provided_key


app = FastAPI(
    title="NYC Subway Agent",
    description="AI-powered NYC subway routing assistant",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    response: str
    user_id: str


class RouteRequest(BaseModel):
    from_station: str
    to_station: str


class ArrivalsRequest(BaseModel):
    station: str
    line: Optional[str] = None


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "service": "NYC Subway Agent"}


@app.get("/")
async def root(_: str = Depends(verify_api_key)):
    """Serve the chat interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, _: str = Depends(verify_api_key)):
    """Chat with the subway agent."""
    try:
        response = chat(request.message, request.user_id)
        return ChatResponse(response=response, user_id=request.user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear")
async def clear_chat(user_id: str = "default", _: str = Depends(verify_api_key)):
    """Clear conversation history."""
    clear_history(user_id)
    return {"status": "cleared", "user_id": user_id}


@app.post("/route")
async def get_route_endpoint(request: RouteRequest, _: str = Depends(verify_api_key)):
    """Get a route between two stations (direct API, no LLM)."""
    from_st = find_station(request.from_station)
    to_st = find_station(request.to_station)

    if not from_st:
        raise HTTPException(status_code=404, detail=f"Station not found: {request.from_station}")
    if not to_st:
        raise HTTPException(status_code=404, detail=f"Station not found: {request.to_station}")

    route = find_route(request.from_station, request.to_station)
    if not route:
        raise HTTPException(status_code=404, detail="No route found")

    return {
        "from": from_st.name,
        "to": to_st.name,
        "segments": [
            {
                "line": seg.line,
                "from_station": seg.from_station.name,
                "to_station": seg.to_station.name,
                "stops": len(seg.stops) - 1,
                "travel_time_minutes": seg.travel_time_minutes
            }
            for seg in route.segments
        ],
        "total_time_minutes": route.total_time_minutes,
        "transfers": route.transfer_count
    }


@app.post("/arrivals")
async def get_arrivals_endpoint(request: ArrivalsRequest, _: str = Depends(verify_api_key)):
    """Get real-time arrivals for a station (direct API, no LLM)."""
    station = find_station(request.station)
    if not station:
        raise HTTPException(status_code=404, detail=f"Station not found: {request.station}")

    lines = [request.line] if request.line else None
    arrivals = get_arrivals(station.id, lines)

    return {
        "station": station.name,
        "arrivals": [
            {
                "line": arr.line,
                "direction": "Uptown" if arr.direction == "N" else "Downtown",
                "minutes_until": arr.minutes_until,
                "arrival_time": arr.arrival_time.isoformat()
            }
            for arr in arrivals[:10]
        ]
    }


@app.get("/stations")
async def list_stations(borough: Optional[str] = None, line: Optional[str] = None, _: str = Depends(verify_api_key)):
    """List all stations, optionally filtered."""
    stations = list(STATIONS.values())

    if borough:
        stations = [s for s in stations if s.borough.lower() == borough.lower()]

    if line:
        stations = [s for s in stations if line.upper() in s.lines]

    return {
        "count": len(stations),
        "stations": [
            {
                "id": s.id,
                "name": s.name,
                "lines": s.lines,
                "borough": s.borough
            }
            for s in stations
        ]
    }


@app.get("/preferences/{user_id}")
async def get_preferences(user_id: str, _: str = Depends(verify_api_key)):
    """Get all preferences for a user."""
    prefs = db.get_all_preferences(user_id)
    return {"user_id": user_id, "preferences": prefs}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()


@app.get("/turns")
async def list_turns(
    limit: int = 50,
    only_failures: bool = False,
    search: Optional[str] = None,
    _: str = Depends(verify_api_key),
):
    """Recent agent turns, newest first — the data behind the viewer.

    A wrong answer is a 200, so request logs cannot show which turns went
    badly. These rows carry the question, the tools chosen with their
    arguments, what each returned, and the final answer.
    """
    from google.cloud import bigquery

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "subway-agent-nyc")
    dataset = os.getenv("AGENT_BQ_DATASET", "agent")
    table = os.getenv("AGENT_BQ_TABLE", "turns")

    where = []
    params = [bigquery.ScalarQueryParameter("lim", "INT64", max(1, min(limit, 500)))]
    if only_failures:
        # "Failure" here means the agent reached for nothing, or blew up — the
        # cases worth reading first. A wrong answer that used a tool still
        # needs a human eye.
        where.append("(used_any_tool = FALSE OR error IS NOT NULL)")
    if search:
        where.append("(LOWER(question) LIKE @q OR LOWER(answer) LIKE @q)")
        params.append(bigquery.ScalarQueryParameter("q", "STRING", f"%{search.lower()}%"))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    try:
        client = bigquery.Client(project=project)
        rows = client.query(
            f"""SELECT turn_at, user_id, question, answer, tool_calls, tool_names,
                       used_any_tool, latency_ms, model, error
                FROM `{project}.{dataset}.{table}`
                {clause}
                ORDER BY turn_at DESC
                LIMIT @lim""",
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"turn store unavailable: {exc}")

    out = []
    for r in rows:
        try:
            calls = json.loads(r.tool_calls) if r.tool_calls else []
        except ValueError:
            calls = []
        out.append({
            "turn_at": r.turn_at.isoformat() if r.turn_at else None,
            "user_id": r.user_id,
            "question": r.question,
            "answer": r.answer,
            "tool_calls": calls,
            "tool_names": r.tool_names,
            "used_any_tool": r.used_any_tool,
            "latency_ms": r.latency_ms,
            "model": r.model,
            "error": r.error,
        })
    return {"turns": out, "count": len(out)}


@app.get("/logs")
async def turn_viewer(_: str = Depends(verify_api_key)):
    """Browser view of recent turns."""
    return FileResponse(STATIC_DIR / "logs.html")
