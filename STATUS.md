# Status — subway-agent

_Handoff snapshot, 2026-10-01._

NYC subway + LIRR conversational agent (LangGraph + Groq, FastAPI). Backend for the
MTAGPT iOS app (`maimon495/MTAGPT-IOS`). Architecture: `docs/ARCHITECTURE.md`.

## Where it stands
- **Live** on Cloud Run: service `subway-agent`, project `subway-agent-nyc`, region
  `us-east1`, URL `https://subway-agent-2chjutnyma-ue.a.run.app` (Ready as of 2026-10-01).
- Was dark April–September 2026 (expired Groq key + withdrawn `llama-3.3-70b`);
  revived 2026-09-25. The Groq model is now configurable.
- Work merged 2026-09-25 → 09-28 (PRs #1–#10): LIRR track assignments collected into
  BigQuery; fixed 190 of 260 wrong subway GTFS stop ids; multiple API keys for
  rotation; arrival-track reporting; "can I make that train" across subway + LIRR;
  turn logging and a turn viewer; routing graph rebuilt from GTFS; four route tools
  collapsed into one.
- No open PRs or stray branches.

## Next steps
- Use the turn viewer to look at real failures and fix what it shows.
- Confirm the BigQuery track collector is still running on schedule.
- Rotate the API key the iOS app embeds once the app reads it from somewhere safer.

## Not in git
- Groq API key and agent API keys: Cloud Run env/secrets in `subway-agent-nyc`.
- `gcloud` auth on the old Mac (personal Google account).
