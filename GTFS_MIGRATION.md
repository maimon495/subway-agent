# GTFS Static Data Migration

This document describes the migration from hardcoded travel time estimates to real GTFS static data.

## Changes Made

### 1. New Module: `gtfs_static.py`
- **Purpose**: Downloads and parses MTA GTFS static data to extract real travel times between stations
- **Features**:
  - Downloads GTFS data from MTA's S3 bucket
  - Parses `stops.txt`, `routes.txt`, `trips.txt`, and `stop_times.txt`
  - Calculates travel times between consecutive stops for each route
  - Handles express vs local train differences automatically (express trains skip stops, so travel times differ)
  - Caches downloaded GTFS data locally

### 2. Updated: `routing.py`
- **Changes**:
  - Now uses GTFS parser to get real travel times when building the graph
  - Falls back to estimates (2 min per stop) if GTFS data unavailable
  - `_calculate_segment_time()` method sums real travel times for route segments
  - Handles both directions (N/S) for stop IDs

### 3. Updated: `tools.py`
- **Changes**:
  - `plan_trip_with_transfers()` now uses GTFS data for:
    - South Ferry → Chambers travel time
    - Chambers → Penn Station on 1 train (local)
    - Chambers → Penn Station on 2/3 trains (express)
  - Automatically selects faster express option (2 or 3)
  - Falls back to estimates if GTFS unavailable

### 4. Updated: `config.py`
- Ensures data directory exists for GTFS file storage

## How It Works

1. **First Run**: Downloads GTFS static data zip file (~10-20MB) to `data/gtfs_subway.zip`
2. **Parsing**: Extracts and parses CSV files from the zip
3. **Travel Time Calculation**: 
   - For each trip, calculates time between consecutive stops
   - Stores minimum travel time for each (from_stop, to_stop, route) combination
   - Express trains naturally have shorter times since they skip stops
4. **Usage**: When routing, looks up real travel times from GTFS data
5. **Fallback**: If GTFS unavailable, uses original 2-minute estimate per stop

## Benefits

- ✅ **Real Data**: Uses actual scheduled travel times from MTA
- ✅ **Express vs Local**: Automatically handles express/local differences
- ✅ **Accurate Routing**: More accurate route time estimates
- ✅ **Graceful Degradation**: Falls back to estimates if GTFS unavailable
- ✅ **Cached**: Downloads once, reuses cached file

## GTFS Data Source

- **Regular GTFS**: `https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip`
- **Supplemented GTFS** (with service changes): `https://rrgtfsfeeds.s3.amazonaws.com/gtfs_supplemented.zip`

The supplemented version includes service changes for the next 7 days and is updated hourly.

## Testing

To test the GTFS integration:

```python
from src.subway_agent.gtfs_static import get_gtfs_parser
from src.subway_agent.stations import find_station

gtfs = get_gtfs_parser()
if gtfs:
    south_ferry = find_station("South Ferry")
    chambers = find_station("Chambers St")
    
    # Get travel time on 1 train
    time = gtfs.get_travel_time_minutes(
        south_ferry.gtfs_stop_id, 
        chambers.gtfs_stop_id, 
        route_id="1"
    )
    print(f"South Ferry to Chambers on 1 train: {time} minutes")
```

## Notes

- GTFS data is downloaded on first use (may take 10-30 seconds)
- File is cached in `data/gtfs_subway.zip` for subsequent runs
- Network connectivity required for initial download
- If download fails, system gracefully falls back to estimates
