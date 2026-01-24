"""FastAPI web interface for the subway agent."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from .agent import chat, clear_history
from .stations import find_station, STATIONS
from .mta_feed import get_arrivals
from .routing import find_route
from .database import db

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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "NYC Subway Agent"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Chat with the subway agent."""
    try:
        response = chat(request.message, request.user_id)
        return ChatResponse(response=response, user_id=request.user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear")
async def clear_chat(user_id: str = "default"):
    """Clear conversation history."""
    clear_history(user_id)
    return {"status": "cleared", "user_id": user_id}


@app.post("/route")
async def get_route_endpoint(request: RouteRequest):
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
async def get_arrivals_endpoint(request: ArrivalsRequest):
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
async def list_stations(borough: Optional[str] = None, line: Optional[str] = None):
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
async def get_preferences(user_id: str):
    """Get all preferences for a user."""
    prefs = db.get_all_preferences(user_id)
    return {"user_id": user_id, "preferences": prefs}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
