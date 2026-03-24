import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
import uvicorn

if __name__ == "__main__":
    reload = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=reload)