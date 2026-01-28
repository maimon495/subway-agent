FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install -e .

# Optionally pre-download GTFS data during build (comment out if you prefer runtime download)
# This ensures the file is available even if runtime network access is restricted
# RUN python3 -c "from src.subway_agent.gtfs_static import get_gtfs_parser; get_gtfs_parser()" || echo "GTFS download failed during build, will retry at runtime"

EXPOSE 8080

CMD ["uvicorn", "subway_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
