"""Wait for the API server to be ready."""

import logging
import sys
import time

import httpx

# Configure logging to stdout (default is stderr)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def wait_for_server(url: str = "http://localhost:8000/health", timeout: int = 30) -> bool:
    """Wait for the server to respond to health checks."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                logger.info(f"Server ready at {url}")
                return True
        except httpx.RequestError:
            pass
        logger.info("Waiting for server...")
        time.sleep(1)
    logger.error(f"Timeout waiting for server at {url}")
    return False


if __name__ == "__main__":
    success = wait_for_server()
    sys.exit(0 if success else 1)
