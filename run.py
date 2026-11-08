"""Start Hookline:  python run.py  [--port 8765] [--data-dir data] [--fake] [--no-browser]

Always binds to 127.0.0.1, so the app (and the API key it stores) is only reachable from this machine.
"""

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

import uvicorn

from app import config
from app.main import create_app

HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Hookline: find the best promos in microdrama screenplays.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, help="where hookline.db lives (default: data/, or data-fake/ with --fake)")
    parser.add_argument("--fake", action="store_true", help="use a simulated LLM (no API key, no network)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()
    # Simulated promos never mix with real ones unless a data dir is chosen explicitly.
    data_dir = args.data_dir or (config.BASE_DIR / "data-fake" if args.fake else config.DEFAULT_DATA_DIR)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(data_dir, fake=args.fake)
    url = f"http://{HOST}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"Hookline running at {url}" + ("  (fake LLM mode)" if args.fake else ""))
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
