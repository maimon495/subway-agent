# GCP Deployment Guide - GTFS Data Download

## Will GTFS Download Work on GCP?

**Yes, in most cases.** GCP Compute Engine instances have outbound internet access by default, and the GTFS file is hosted on a public S3 bucket.

## Requirements

### Network Access
- **Outbound HTTPS (port 443)** to `rrgtfsfeeds.s3.amazonaws.com`
- Most GCP projects have default egress rules that allow this
- File size: ~10-20MB (downloads in 10-30 seconds on typical connections)

### Firewall Rules
If your instance can't download, check:

1. **VPC Firewall Rules**: Ensure egress rule allows HTTPS (TCP 443) to internet
   ```bash
   gcloud compute firewall-rules list --filter="direction=EGRESS"
   ```

2. **Default Rule**: Most projects have `default-allow-egress` that allows all outbound traffic

3. **Private GKE Clusters**: If using private GKE, you may need:
   - Cloud NAT for outbound internet access
   - Or download GTFS during Docker build (see below)

## Options for GTFS Data

### Option 1: Runtime Download (Default)
- Downloads on first use when the app starts
- Cached in `data/gtfs_subway.zip` for subsequent runs
- **Pros**: Always gets latest data
- **Cons**: Requires network access at runtime, ~10-30 second delay on first start

### Option 2: Pre-download in Docker Build
Uncomment this line in `Dockerfile`:
```dockerfile
RUN python3 -c "from src.subway_agent.gtfs_static import get_gtfs_parser; get_gtfs_parser()" || echo "GTFS download failed during build, will retry at runtime"
```

- Downloads during Docker image build
- **Pros**: No runtime download needed, faster startup
- **Cons**: Data may be slightly stale, larger Docker image

### Option 3: Include GTFS File in Image
1. Download GTFS file locally: `wget https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip`
2. Add to Dockerfile:
   ```dockerfile
   COPY gtfs_subway.zip /app/data/gtfs_subway.zip
   ```
3. Ensure `data/` directory exists in image

## Testing Network Access

Test from your GCP instance:
```bash
# Test HTTPS connectivity
curl -I https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip

# Test download
wget https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip
```

## Troubleshooting

### Download Fails at Runtime
1. **Check logs**: Look for "Error downloading GTFS data" messages
2. **Verify network**: Test HTTPS access from instance
3. **Check firewall**: Ensure egress rules allow HTTPS
4. **Fallback**: System gracefully falls back to estimates (2 min per stop)

### Private GKE Clusters
If using private GKE without Cloud NAT:
- Use Option 2 (pre-download in Docker build) from a machine with internet access
- Or configure Cloud NAT for your cluster

## Current Implementation

The code:
- ✅ Uses 120-second timeout (increased from 60)
- ✅ Streams download for better memory usage
- ✅ Provides clear error messages
- ✅ Gracefully falls back to estimates if download fails
- ✅ Caches file locally for subsequent runs

## Recommendations

1. **For Production**: Consider pre-downloading in Docker build for faster startup
2. **For Development**: Runtime download is fine (allows getting latest data)
3. **For Private Clusters**: Use Docker build option or Cloud NAT
