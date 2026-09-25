"""Predict a track from what a train has actually used before.

The MTA posts a track only minutes ahead, which is too late to be useful when
you are deciding whether to run. Trains are creatures of habit, though, so the
track a given train has used on comparable days is a good guess — and one
worth stating with its evidence rather than as a fact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "subway-agent-nyc")
BQ_DATASET = os.getenv("LIRR_BQ_DATASET", "lirr")
BQ_TABLE = os.getenv("LIRR_BQ_TABLE", "track_observations")

# Below this many past runs the modal track is noise dressed up as a number.
MIN_SAMPLES = 4
LOOKBACK_DAYS = 60


@dataclass(frozen=True)
class TrackPrediction:
    track: str
    samples: int
    share: float
    alternatives: list[tuple[str, int]]

    @property
    def confidence(self) -> str:
        if self.share >= 0.85:
            return "very consistent"
        if self.share >= 0.6:
            return "usually"
        return "mixed"

    def describe(self) -> str:
        percent = round(self.share * 100)
        text = (
            f"Track {self.track} — {percent}% of the last {self.samples} comparable runs"
        )
        if self.alternatives:
            others = ", ".join(f"track {t} ({n})" for t, n in self.alternatives[:2])
            text += f"; otherwise {others}"
        return text


def day_type(day: date_cls) -> str:
    weekday = day.weekday()
    if weekday == 5:
        return "saturday"
    if weekday == 6:
        return "sunday"
    return "weekday"


def predict_track(
    train_number: str,
    stop_id: str,
    day: date_cls,
    event_type: str = "departure",
) -> Optional[TrackPrediction]:
    """Modal track for this train at this stop on this kind of day.

    Returns None when there is not enough history yet, which is the honest
    answer for a while after collection starts — it cannot be backfilled.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=GCP_PROJECT)
    query = f"""
        WITH first_seen AS (
          SELECT service_date, track,
                 ROW_NUMBER() OVER (
                   PARTITION BY service_date ORDER BY observed_at
                 ) AS rn
          FROM `{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`
          WHERE train_number = @train
            AND stop_id = @stop
            AND event_type = @event_type
            AND service_date >= DATE_SUB(@day, INTERVAL {LOOKBACK_DAYS} DAY)
            AND service_date < @day
            AND FORMAT_DATE('%A', service_date) IN UNNEST(@weekdays)
        )
        SELECT track, COUNT(*) AS n
        FROM first_seen
        WHERE rn = 1
        GROUP BY track
        ORDER BY n DESC
    """
    weekday_names = {
        "weekday": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "saturday": ["Saturday"],
        "sunday": ["Sunday"],
    }[day_type(day)]

    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("train", "STRING", str(train_number)),
                bigquery.ScalarQueryParameter("stop", "STRING", stop_id),
                bigquery.ScalarQueryParameter("event_type", "STRING", event_type),
                bigquery.ScalarQueryParameter("day", "DATE", day),
                bigquery.ArrayQueryParameter("weekdays", "STRING", weekday_names),
            ]
        ),
    )
    rows = [(r.track, r.n) for r in job.result()]
    total = sum(n for _, n in rows)
    if total < MIN_SAMPLES:
        return None

    track, count = rows[0]
    return TrackPrediction(
        track=track,
        samples=total,
        share=count / total,
        alternatives=rows[1:],
    )
