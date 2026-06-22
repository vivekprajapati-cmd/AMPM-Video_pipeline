"""
HeyGen Avatar 4 — talking photo lipsync.

Flow per AVATAR scene:
1. Upload user's avatar photo (JPG/PNG) to HeyGen → talking_photo_id
2. Upload ElevenLabs MP3 to HeyGen → audio_asset_id
3. POST /v2/video/generate with talking_photo character + audio voice
4. Poll until COMPLETED, download MP4

Avatar photo source: config.HEYGEN_AVATAR_IMG_* paths (per persona),
or overridden at runtime via avatar_image_path argument (UI upload).

Higgsfield image generation is NOT used for avatar scenes.
It is used only for CUTAWAY infographic scenes (see higgsfield_cli.py).
"""
import mimetypes
import time
from pathlib import Path

import requests

import config
from models.scene import Scene
from utils.downloader import download_file

_UPLOAD_URL = "https://upload.heygen.com/v1/asset"
_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
_STATUS_URL = "https://api.heygen.com/v1/video_status.get"

_POLL_INTERVAL = 10
_MAX_POLL_WAIT = 600


def _upload_asset(file_path: str, api_key: str) -> str:
    """
    Uploads any file (image or audio) to HeyGen asset storage.
    Returns the asset id, which becomes talking_photo_id or audio_asset_id.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content_type, _ = mimetypes.guess_type(str(path))
    content_type = content_type or "application/octet-stream"

    with path.open("rb") as f:
        resp = requests.post(
            _UPLOAD_URL,
            headers={"x-api-key": api_key, "Content-Type": content_type},
            data=f,
            timeout=120,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"HeyGen asset upload failed {resp.status_code}: {resp.text[:300]}"
        )

    asset_id = resp.json().get("data", {}).get("id")
    if not asset_id:
        raise RuntimeError(f"HeyGen upload returned no id: {resp.json()}")
    return asset_id


def _submit_job(talking_photo_id: str, audio_asset_id: str, api_key: str) -> str:
    """Submits video generation. Returns video_id."""
    resp = requests.post(
        _GENERATE_URL,
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json={
            "test": False,
            "use_avatar_iv_model": True,
            "dimension": {"width": 720, "height": 1280},  # 9:16 vertical
            "video_inputs": [
                {
                    "character": {
                        "type": "talking_photo",
                        "talking_photo_id": talking_photo_id,
                    },
                    "voice": {
                        "type": "audio",
                        "audio_asset_id": audio_asset_id,
                    },
                }
            ],
        },
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"HeyGen generate failed {resp.status_code}: {resp.text[:300]}"
        )

    video_id = resp.json().get("data", {}).get("video_id")
    if not video_id:
        raise RuntimeError(f"HeyGen generate returned no video_id: {resp.json()}")
    return video_id


def _poll_job(video_id: str, api_key: str) -> str:
    """Polls until COMPLETED. Returns output video URL."""
    deadline = time.time() + _MAX_POLL_WAIT
    while time.time() < deadline:
        resp = requests.get(
            _STATUS_URL,
            headers={"X-Api-Key": api_key},
            params={"video_id": video_id},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HeyGen poll error {resp.status_code}: {resp.text[:300]}")

        data = resp.json().get("data", {})
        status = data.get("status", "").upper()

        if status == "COMPLETED":
            url = data.get("video_url")
            if not url:
                raise RuntimeError(f"HeyGen job completed but no video_url: {data}")
            return url

        if status in ("FAILED", "ERROR"):
            raise RuntimeError(f"HeyGen job {video_id} failed: {data.get('error', status)}")

        time.sleep(_POLL_INTERVAL)

    raise RuntimeError(f"HeyGen job {video_id} timed out after {_MAX_POLL_WAIT}s")


def generate_lipsync_for_scene(
    scene: Scene,
    output_dir: Path,
    avatar_image_path: str | None = None,
    persona_id: str | None = None,
    api_key: str | None = None,
) -> Scene:
    """
    Generates lipsync video for a single AVATAR scene.

    avatar_image_path: path to the persona's face photo. If None, resolved from
    config using persona_id. This is NOT a Higgsfield-generated image —
    it's a real photo of the avatar uploaded by the user.
    """
    key = api_key or config.HEYGEN_API_KEY
    if not key:
        raise RuntimeError("HEYGEN_API_KEY not set in .env")

    if not scene.audio_path:
        raise RuntimeError(f"Scene {scene.scene_number} missing audio_path")

    img_path = avatar_image_path or config.resolve_avatar_image(persona_id)
    if not img_path:
        raise RuntimeError(
            "No avatar image configured. Set HEYGEN_AVATAR_IMG_DEFAULT in .env "
            "or upload an image in the UI."
        )

    talking_photo_id = _upload_asset(img_path, key)
    audio_asset_id = _upload_asset(scene.audio_path, key)
    video_id = _submit_job(talking_photo_id, audio_asset_id, key)
    output_url = _poll_job(video_id, key)

    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    dest = clips_dir / f"scene{scene.scene_number}_lipsync.mp4"

    download_file(output_url, dest)
    scene.lipsync_video_path = str(dest)
    return scene


def generate_lipsync_for_avatar_scenes(
    scenes: list[Scene],
    output_dir: Path,
    avatar_image_path: str | None = None,
    persona_id: str | None = None,
    api_key: str | None = None,
    progress_callback=None,
) -> list[Scene]:
    """Runs HeyGen lipsync for all AVATAR scenes sequentially."""
    avatar_scenes = [s for s in scenes if s.type == "AVATAR"]

    for i, scene in enumerate(avatar_scenes):
        generate_lipsync_for_scene(
            scene, output_dir, avatar_image_path, persona_id, api_key
        )
        if progress_callback:
            progress_callback(i + 1, len(avatar_scenes))

    return scenes
