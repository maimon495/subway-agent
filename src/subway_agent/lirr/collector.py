"""Collect LIRR track assignments into BigQuery, to learn what is habitual.

The MTA publishes the track a train is using, but keeps no history, so a
question like "what track does the 5:22 usually come in on" cannot be answered
from the live feed alone. This job runs on a schedule and appends what it sees,
building the history that makes a prediction possible.

Only new or changed assignments are written. A train keeping the same track all
morning produces one row, not one row per poll, so the table stays small enough
to sit comfortably in the BigQuery free tier.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Iterable

from .feed import TrackObservation, fetch_feed, parse_track_observations

log = logging.getLogger(__name__)

BQ_DATASET = os.getenv("LIRR_BQ_DATASET", "lirr")
BQ_TABLE = os.getenv("LIRR_BQ_TABLE", "track_observations")
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "subway-agent-nyc")

SCHEMA = [
    ("observed_at", "TIMESTAMP"),
    ("service_date", "DATE"),
    ("trip_id", "STRING"),
    ("train_number", "STRING"),
    ("route_id", "STRING"),
    ("direction_id", "INTEGER"),
    ("stop_id", "STRING"),
    ("stop_sequence", "INTEGER"),
    ("origin_stop_id", "STRING"),
    ("destination_stop_id", "STRING"),
    ("track", "STRING"),
    ("train_status", "STRING"),
    ("event_type", "STRING"),
    ("event_time", "TIMESTAMP"),
    ("minutes_before_event", "INTEGER"),
    ("is_terminal", "BOOLEAN"),
]


def _service_date(obs: TrackObservation) -> str | None:
    if not obs.service_date or len(obs.service_date) != 8:
        return None
    return f"{obs.service_date[:4]}-{obs.service_date[4:6]}-{obs.service_date[6:]}"


def to_row(obs: TrackObservation, observed_at: datetime) -> dict:
    minutes_before = None
    if obs.event_time:
        minutes_before = int((obs.event_time - observed_at).total_seconds() // 60)
    return {
        "observed_at": observed_at.isoformat(),
        "service_date": _service_date(obs),
        "trip_id": obs.trip_id,
        "train_number": obs.train_number,
        "route_id": obs.route_id,
        "direction_id": obs.direction_id,
        "stop_id": obs.stop_id,
        "stop_sequence": obs.stop_sequence,
        "origin_stop_id": obs.origin_stop_id,
        "destination_stop_id": obs.destination_stop_id,
        "track": obs.track,
        "train_status": obs.train_status,
        "event_type": obs.event_type,
        "event_time": obs.event_time.isoformat() if obs.event_time else None,
        "minutes_before_event": minutes_before,
        "is_terminal": obs.is_terminal,
    }


def _key(row: dict) -> tuple:
    return (row["service_date"], row["trip_id"], row["stop_id"], row["event_type"])


def ensure_table(client) -> None:
    from google.cloud import bigquery

    dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)
        log.info("created dataset %s", BQ_DATASET)

    table_ref = dataset_ref.table(BQ_TABLE)
    try:
        client.get_table(table_ref)
    except Exception:
        table = bigquery.Table(
            table_ref,
            schema=[bigquery.SchemaField(n, t) for n, t in SCHEMA],
        )
        # Partitioning keeps the per-run dedupe query scanning one day, not the
        # whole history, which is what keeps this inside the free tier.
        table.time_partitioning = bigquery.TimePartitioning(field="service_date")
        table.clustering_fields = ["stop_id", "train_number"]
        client.create_table(table, exists_ok=True)
        log.info("created table %s.%s", BQ_DATASET, BQ_TABLE)


def existing_tracks(client, service_dates: Iterable[str]) -> dict[tuple, str]:
    """Latest track already recorded for each trip/stop/event on these dates."""
    dates = sorted({d for d in service_dates if d})
    if not dates:
        return {}
    from google.cloud import bigquery

    query = f"""
        SELECT service_date, trip_id, stop_id, event_type, track
        FROM (
          SELECT service_date, trip_id, stop_id, event_type, track,
                 ROW_NUMBER() OVER (
                   PARTITION BY service_date, trip_id, stop_id, event_type
                   ORDER BY observed_at DESC
                 ) AS rn
          FROM `{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`
          WHERE service_date IN UNNEST(@dates)
        )
        WHERE rn = 1
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("dates", "DATE", dates)]
        ),
    )
    return {
        (str(r.service_date), r.trip_id, r.stop_id, r.event_type): r.track
        for r in job.result()
    }


def collect(dry_run: bool = False) -> dict:
    observed_at = datetime.now(timezone.utc)
    observations = list(parse_track_observations(fetch_feed()))
    rows = [to_row(o, observed_at) for o in observations]

    # One trip can appear twice for the same stop and event within a feed;
    # keep the last, so the dedupe key stays unique before comparison.
    deduped: dict[tuple, dict] = {}
    for row in rows:
        deduped[_key(row)] = row

    if dry_run:
        return {
            "observations": len(rows),
            "unique": len(deduped),
            "would_insert": len(deduped),
            "dry_run": True,
        }

    from google.cloud import bigquery

    client = bigquery.Client(project=GCP_PROJECT)
    ensure_table(client)

    known = existing_tracks(client, {r["service_date"] for r in deduped.values()})
    new_rows = [r for k, r in deduped.items() if known.get(k) != r["track"]]

    if new_rows:
        table = client.get_table(f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}")
        errors = client.insert_rows_json(table, new_rows)
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors[:3]}")

    return {
        "observations": len(rows),
        "unique": len(deduped),
        "already_known": len(known),
        "inserted": len(new_rows),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Collect LIRR track assignments")
    parser.add_argument("--dry-run", action="store_true", help="parse only, write nothing")
    args = parser.parse_args()
    log.info("collected %s", collect(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
