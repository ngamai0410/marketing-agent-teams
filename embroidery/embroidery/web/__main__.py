"""
Launch the dashboard:  cd embroidery && venv/bin/python -m embroidery.web [--yes] [--no-browser]

Starts uvicorn on config.web.{host,port} and opens the browser once the server
is up. --yes sets EMBROIDERY_YES so QC gates auto-approve (useful for a hands-off
run while still watching live).
"""

import os
import sys
import threading
import webbrowser

import uvicorn

from embroidery.core.config import settings
from embroidery.core.logger import get_logger

log = get_logger(__name__)


def _open_browser_when_up(url: str) -> None:
    # uvicorn's startup is fast; a short delay avoids racing the listen socket.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()


def main() -> None:
    if "--yes" in sys.argv:
        os.environ["EMBROIDERY_YES"] = "1"

    host, port = settings.web.host, settings.web.port
    url = f"http://{host}:{port}/"
    log.info("dashboard starting at %s", url)

    if settings.web.open_browser and "--no-browser" not in sys.argv:
        _open_browser_when_up(url)

    uvicorn.run("embroidery.web.server:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
