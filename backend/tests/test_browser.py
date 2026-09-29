import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from app.config import BACKEND_DIR


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Set RUN_BROWSER_TESTS=1 to run the browser flow")
def test_browser_booking_flow(clean_database, tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND_DIR, stdout=log, stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    with urlopen(base_url + "/api/health", timeout=1):
                        break
                except OSError:
                    if server.poll() is not None:
                        pytest.fail("Test server did not start; inspect server.log")
                    time.sleep(0.1)
            else:
                pytest.fail("Test server startup timed out")
            env = os.environ | {"WILLOW_BASE_URL": base_url, "WILLOW_TEST_OUTPUT": str(tmp_path)}
            subprocess.run(
                ["node", str(BACKEND_DIR.parent / "frontend/tests/browser.mjs")],
                env=env, cwd=BACKEND_DIR.parent / "frontend", check=True, timeout=120,
            )
        finally:
            server.terminate()
            server.wait(timeout=10)
