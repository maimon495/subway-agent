# Subway Agent Architecture

Walkthrough of how the NYC subway agent is structured and how data flows.

---

## 1. High-level flow

```
User (CLI or API)
    → chat(message, user_id)
    → LangGraph agent (Groq LLM + tools)
    → Tool calls (routing, MTA real-time, compare local vs express, etc.)
    → Tool results back to LLM
    → Final reply to user
```

- **Entry points:** `cli.py` (REPL) and `api.py` (FastAPI + web UI) both call `agent.chat(message, user_id)`.
- **State:** Conversation history is stored in SQLite via `database.py` and passed into the graph as message history.
- **Agent:** A LangGraph `StateGraph` with two nodes—**agent** (LLM) and **tools**—and a loop: agent → (tool calls?) → tools → agent → … → end.

---

## 2. LangGraph graph

Defined in `agent.create_agent()`.

### State

- **`messages`**: List of `BaseMessage` (system, human, AI, tool). Uses `add_messages` so new messages are appended.
- **`user_id`**: For personalization (e.g. preferences, history).

### Nodes

| Node    | What it does |
|---------|----------------|
| **agent** | `call_model(state)`: Prepends system prompt if needed, calls Groq LLM with `llm_with_tools.invoke(messages)`. Handles **legacy** tool calls (see below) and **error recovery** when Groq returns 400 for XML-style tool use. Returns `{"messages": [response]}`. |
| **tools** | LangGraph’s `ToolNode(ALL_TOOLS)`: Executes tool calls from the last AI message and returns `ToolMessage`s. |

### Edges

- `START → agent`
- `agent → (conditional)`:
  - If last message has `tool_calls` → **tools**
  - Else → **END**
- `tools → agent` (loop until the model stops calling tools)

So the loop is: **agent → tools → agent → … → END** when the model responds with content and no tool calls.

### LLM and tools

- **LLM:** `ChatGroq` (Groq API) with `bind_tools(ALL_TOOLS, tool_choice="auto")`.
- **System prompt:** NYC subway assistant; real-time data preference; which tool to use when (local vs express → `compare_local_vs_express`, “right now” → `get_route_with_arrivals`, “next train” → `get_train_arrivals`, etc.).

---

## 3. Tools (what the agent can call)

All tools live in `tools.py` and are in `ALL_TOOLS` / `TOOL_MAP`.

### Routing (static or real-time)

| Tool | Purpose |
|------|--------|
| **get_route** | Best route A→B from graph (GTFS/line sequences). No real-time. Use for “how do I get there” when user doesn’t care about “right now”. |
| **get_route_with_arrivals** | Same route **plus** real-time next-train times at origin (MTA feed). Use for “fastest way right now” / “how do I get there now”. |
| **get_train_arrivals** | Real-time arrivals at a station (optional line filter). Use for “when is the next X train” / “trains at Y”. |

### Local vs express (generic)

| Tool | Purpose |
|------|--------|
| **compare_local_vs_express** | For **any** corridor: compare “stay on local” vs “transfer to express” using **real-time** arrivals and **travel times on line** from routing. Params: `from_station`, `to_station`, `transfer_station`, `local_line`, `express_lines`. Handles same-station case (e.g. 14th St → 96th St: 6 vs 4/5 at 14th) and transfer case (e.g. South Ferry → Penn: 1 to Chambers, then 2/3). |
| **plan_trip_with_transfers** | Thin wrapper: calls `compare_local_vs_express("South Ferry", "Penn Station", "Chambers St", "1", "2,3")`. Use for South Ferry → Penn only. |

### Station and preferences

| Tool | Purpose |
|------|--------|
| **get_station_info** | Lines, accessibility, etc. for a station. |
| **find_stations_on_line** | List stations on a given line. |
| **save_preference** / **get_preference** | User preferences (e.g. home station). |
| **get_common_trips** | Frequent trips from DB. |

---

## 4. Data flow: where numbers come from

### Stations

- **`stations.py`**: In-memory list of stations (id, name, lines, GTFS stop id, lat/lon) + aliases (e.g. `"14th st"` → Union Square, `"96th st lexington"` → 96th on Lex).
- **`find_station(name)`**: Resolves a user-facing name to a `Station` (and thus `station.id` for routing/arrivals).

### Routing and travel times

- **`routing.py`**: Graph of stations and line sequences (`LINE_SEQUENCES`). Uses GTFS static when available for segment times; fallback 2 min/stop.
- **`find_route(from_id, to_id)`**: Best path (with transfers) A→B.
- **`get_travel_time_on_line(from_id, to_id, line)`**: Minutes from A to B **on a single line** (BFS on that line). Used by `compare_local_vs_express` for:
  - origin → transfer on local,
  - origin → destination on local,
  - transfer → destination on express.

### Real-time arrivals

- **`mta_feed.py`**: Fetches MTA GTFS-Realtime feeds (optional `MTA_API_KEY` in headers). Caches ~30s.
- **`get_arrivals(station_id, lines?)`**: Returns list of `TrainArrival` (line, direction, `minutes_until`) for that station.
- Used by: `get_route_with_arrivals`, `get_train_arrivals`, `compare_local_vs_express`, `plan_trip_with_transfers`.

### Local vs express math (`compare_local_vs_express`)

1. Resolve stations; get direction (N/S) from lat/lon.
2. **Travel times (routing):**  
   `get_travel_time_on_line` for: origin→transfer (local), origin→destination (local), transfer→destination (express).
3. **Real-time:**  
   Next local at origin (`get_arrivals`); if transfer ≠ origin, next express at transfer that you can catch (arrival at transfer + 1 min buffer).
4. **Same-station case** (e.g. 14th → 96th): compare “next 6” vs “next 4/5” at 14th; total time = wait + travel on that line.
5. **Transfer case** (e.g. South Ferry → Penn): time to Chambers on 1, then first 2/3 at Chambers you can make; total = when that 2/3 departs + travel Chambers→Penn on 2/3.
6. Returns a short report: next local time, Option 1 (stay) total min, Option 2 (transfer) total min, wait at transfer, and a recommendation.

---

## 5. Legacy tool calls and error recovery

Some models (e.g. via Groq) sometimes output **XML-style** tool calls instead of structured `tool_calls`:

```text
<function=get_train_arrivals {"station_name": "South Ferry"}></function>
```

Groq can return **400** and put that string in `failed_generation`.

- **In the agent node:**  
  - If the LLM response has **content** with that pattern and **no** structured `tool_calls`, we parse it with `parse_legacy_tool_call(response.content)` and execute the tool; the “response” we add is the tool result.  
  - If the LLM call **raises** (e.g. 400) and the error contains `tool_use_failed` or `failed_generation`, we parse the **full error string** (or an extracted `failed_generation` value) with `parse_legacy_tool_call`, then run the tool and return its result as the AI message so the user still gets an answer.

So even when the model triggers a 400 with a legacy-format tool call, the agent still runs the intended tool and returns that result.

---

## 6. Config and entry points

- **`config.py`**: `GROQ_API_KEY`, `GROQ_MODEL`, optional `MTA_API_KEY`, `MTA_FEEDS`, paths, DB path.
- **`cli.py`**: REPL; reads input, calls `agent.chat()`, prints reply; supports `/clear`, `/quit`.
- **`api.py`**: FastAPI app; `/chat` (and optional others) call `agent.chat()`; optional `SUBWAY_API_KEY`; serves `static/index.html` for the web UI.
- **`database.py`**: SQLite for conversation history, preferences, and trip counts.

---

## 7. File map

| File | Role |
|------|------|
| **agent.py** | LangGraph graph, system prompt, tool binding, legacy parsing, `chat()`, `get_agent()`. |
| **tools.py** | All tools: routing, arrivals, compare_local_vs_express, plan_trip_with_transfers, station/prefs. |
| **routing.py** | Graph, LINE_SEQUENCES, find_route, get_travel_time_on_line. |
| **stations.py** | Station list, aliases, find_station, find_stations_by_line. |
| **mta_feed.py** | GTFS-Realtime fetch, cache, get_arrivals. |
| **gtfs_static.py** | Optional GTFS static data for travel times. |
| **config.py** | Env and constants. |
| **database.py** | SQLite: messages, preferences, trips. |
| **cli.py** | REPL entry. |
| **api.py** | HTTP API and web UI. |

---

## 8. Summary

- **Agent** = LangGraph loop: Groq LLM (with tools) ↔ ToolNode; state = messages + user_id.
- **Real-time** is preferred for “right now”, “next train”, and “local vs express”; those use `get_arrivals` and tools that call it.
- **Local vs express** is generic: `compare_local_vs_express` works for any corridor (1 vs 2/3, 6 vs 4/5, etc.) using routing travel times and MTA real-time; South Ferry → Penn is a one-line wrapper.
- **Legacy** XML-style tool calls are parsed and executed so 400s from Groq still produce a tool result for the user.
