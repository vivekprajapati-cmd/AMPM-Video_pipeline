import time
from pathlib import Path

import requests


def download_file(url: str, dest_path: str | Path, retries: int = 3, timeout: int = 60) -> Path:
    """
    Downloads a file from url to dest_path. Returns the Path.
    Retries on transient HTTP errors with a short backoff.
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, stream=True, timeout=timeout)
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return dest
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to download {url} after {retries} attempts: {last_exc}")
