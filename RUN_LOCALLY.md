# Running the Subway Agent Locally

## Prerequisites

1. **Set up environment variables** (create a `.env` file in the project root):
   ```bash
   GROQ_API_KEY=your_groq_api_key_here
   SUBWAY_API_KEY=your_api_key_for_web_interface  # Optional, for API server
   MTA_API_KEY=your_mta_api_key  # Optional; MTA says keys no longer required for subway real-time feeds
   ```

2. **Install dependencies** (if not already installed):
   ```bash
   pip install -e .
   ```

## Running the CLI

### Option 1: Using the installed script (recommended)
```bash
subway-agent
```

### Option 2: Using Python module
```bash
python3 -m subway_agent.cli
```

### Option 3: Direct Python execution
```bash
python3 -m src.subway_agent.cli
```

### Option 4: Using the entry point directly
```bash
python3 -c "from src.subway_agent.cli import main; main()"
```

## Running the API Server

### Option 1: Using the installed script
```bash
subway-api
```

### Option 2: Using Python module
```bash
python3 -m subway_agent.api
```

### Option 3: Direct Python execution
```bash
python3 -m src.subway_agent.api
```

Then access the web interface at: http://localhost:8000

## CLI Usage

Once running, you can:
- Ask questions like: "How do I get from Times Square to Brooklyn Bridge?"
- Check train arrivals: "When is the next 1 train at 72nd St?"
- Get station info: "What lines stop at Union Square?"
- Use commands:
  - `/clear` - Clear conversation history
  - `/quit` or `/exit` - Exit the program

## Troubleshooting

### Missing GROQ_API_KEY
If you see errors about missing API key:
1. Create a `.env` file in the project root
2. Add: `GROQ_API_KEY=your_key_here`
3. Or export: `export GROQ_API_KEY=your_key_here`

### GTFS Download Fails
The system will automatically fall back to estimates (2 min per stop) if GTFS data can't be downloaded. This is normal and the agent will still work.

### Import Errors
Make sure you're in the project root directory and dependencies are installed:
```bash
pip install -e .
```
