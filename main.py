import os
import sys
from pathlib import Path
import uvicorn

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    port_str = os.environ.get("PORT", "8000")
    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    print(f"FlowCart server starting on 0.0.0.0:{port} (PORT env='{port_str}')...")
    uvicorn.run("api:app", host="0.0.0.0", port=port, log_level="info")
