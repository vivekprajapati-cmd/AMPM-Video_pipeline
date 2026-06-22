"""
File hosting via Sync.so's own asset upload endpoint.
Upload local files, get back a Sync.so-hosted URL — no external storage needed.
"""
from pathlib import Path

import requests

import config

_ASSET_URL = "https://api.sync.so/v2/assets"


def upload_to_sync(local_path: str | Path, api_key: str | None = None) -> str:
    """
    Uploads a local file to Sync.so's asset storage.
    Returns a publicly accessible URL that can be passed to the generate endpoint.
    """
    key = api_key or config.SYNC_API_KEY
    if not key:
        raise RuntimeError("SYNC_API_KEY not set. Add it to your .env file.")

    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    with path.open("rb") as f:
        resp = requests.post(
            _ASSET_URL,
            headers={"x-api-key": key},
            files={"file": (path.name, f)},
            timeout=120,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Sync.so asset upload failed {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    url = data.get("url") or data.get("asset_url") or data.get("id")
    if not url:
        raise RuntimeError(f"Sync.so upload returned no URL: {data}")
    return url


def upload_for_sync(
    video_path: str | Path,
    audio_path: str | Path,
    api_key: str | None = None,
) -> tuple[str, str]:
    """
    Uploads avatar static video and audio to Sync.so.
    Returns (video_url, audio_url).
    """
    video_url = upload_to_sync(video_path, api_key)
    audio_url = upload_to_sync(audio_path, api_key)
    return video_url, audio_url
