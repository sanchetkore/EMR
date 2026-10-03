"""Run the local API against the existing database configured in backend/.env."""
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import uvicorn

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.chdir(root)
load_dotenv(root / '.env', override=True)

if __name__ == '__main__':
    uvicorn.run('app.main:app', host='127.0.0.1', port=9000, access_log=False)
