# subway-agent — Project Context

NYC subway + LIRR conversational agent: LangGraph + Groq LLM, FastAPI web/API, CLI.
Backend for the MTAGPT iOS app (`maimon495/MTAGPT-IOS`); new capabilities ship by
deploying this, with no app build.

## Layout
- `src/subway_agent/` — `agent.py` (LangGraph graph), `tools.py` (agent tools),
  `routing.py` + `gtfs_static.py` (graph built from GTFS), `mta_feed.py` (real-time),
  `lirr/`, `api.py` (FastAPI), `cli.py`, `telemetry.py` (turn logging), `database.py` (SQLite history)
- `docs/ARCHITECTURE.md` — how it fits together. `RUN_LOCALLY.md`, `GCP_DEPLOYMENT.md`.
- Tests: `tests/` (pytest).

## Run
`pip install -e .`, put `GROQ_API_KEY` (and `SUBWAY_API_KEY`) in `.env`, then
`subway-agent` (CLI) or `subway-api` (http://localhost:8000).

## Deployed
Cloud Run service `subway-agent`, project `subway-agent-nyc`, region `us-east1`.
When MTAGPT looks broken, check here first: an expired Groq key or a withdrawn
model took it dark April–September 2026. The Groq model is configurable for that reason.

## Working with Brian
- Work on a feature branch and open a PR; never commit to `main`. Brian merges.
- Do the work end to end. Only hand back secrets, spending, irreversible
  outward-facing actions, and product decisions such as naming.
- Never commit secrets. Where each one lives is listed in STATUS.md.
- Other projects: see `docs/ALL-PROJECTS.md` in `maimon495/DailyGratitudeJournal`.

@STATUS.md
