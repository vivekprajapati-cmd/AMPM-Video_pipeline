"""
ElevenLabs — 6 individual audio clips, one per scene.

Uses previous_text / next_text for prosody continuity across scenes.
Uses seed=42 on all calls for consistent voice timbre.

Falls back to gTTS if ElevenLabs fails (free plan / bad voice ID / quota exceeded).
"""
import logging
from pathlib import Path

import requests

import config
from models.scene import Scene

logger = logging.getLogger(__name__)

_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def _tts_request(
    text: str,
    previous_text: str,
    next_text: str,
    voice_id: str,
    api_key: str,
) -> bytes:
    url = _TTS_URL.format(voice_id=voice_id)
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "seed": config.ELEVENLABS_SEED,
        "previous_text": previous_text,
        "next_text": next_text,
        "voice_settings": config.ELEVENLABS_VOICE_SETTINGS,
    }
    resp = requests.post(
        url,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json=payload,
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs error {resp.status_code}: {resp.text[:300]}"
        )
    return resp.content


def _gtts_fallback(text: str, dest: Path) -> None:
    """Generates audio using gTTS and saves to dest. No return value — writes file directly."""
    from gtts import gTTS
    logger.warning("Using gTTS fallback — quality will be lower than ElevenLabs.")
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(str(dest))


def _get_duration(path: Path) -> float:
    """Returns audio duration in seconds using ffprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0



def _trim_to_max(dest: Path, max_seconds: float) -> None:
    """
    Trims audio to max_seconds if it exceeds that duration.
    If audio is already within max_seconds, leaves it untouched — no stretching, no padding.
    This keeps natural speech pace and ensures audio never overruns the video clip.
    """
    import subprocess

    current = _get_duration(dest)
    if current <= 0:
        logger.warning(f"Could not read duration for {dest.name} — skipping trim check.")
        return

    logger.info(f"  Audio duration: {current:.2f}s (max allowed: {max_seconds}s)")

    if current <= max_seconds:
        logger.info(f"  Audio within limit — no trim needed.")
        return

    tmp = dest.with_suffix(".tmp.mp3")
    try:
        dest.rename(tmp)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(tmp),
            "-t", str(max_seconds),
            "-c:a", "copy",
            str(dest),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Audio trim failed: {result.stderr[:300]} — keeping original {current:.2f}s.")
            tmp.rename(dest)
        else:
            final = _get_duration(dest)
            logger.info(f"  Trimmed {current:.2f}s → {final:.2f}s")
    except Exception as e:
        logger.warning(f"Audio trim error: {e} — keeping original.")
        if tmp.exists():
            tmp.rename(dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def generate_audio_for_scenes(
    scenes: list[Scene],
    output_dir: Path,
    voice_id: str | None = None,
    persona_id: str | None = None,
    api_key: str | None = None,
    audio_cap_seconds: float | None = None,
    progress_callback=None,
) -> list[Scene]:
    """
    Generates one MP3 per scene and writes it to output_dir/audio/seg{n}.mp3.
    Updates scene.audio_path in-place. Returns the updated scenes list.

    Falls back to gTTS per scene if ElevenLabs fails.
    voice_id: explicit override. If None, resolved from persona_id via config.
    progress_callback: optional callable(scene_index, total) for UI progress.
    """
    vid = voice_id or config.resolve_voice_id(persona_id)
    key = api_key or config.ELEVENLABS_API_KEY

    elevenlabs_available = bool(vid and key)
    if not elevenlabs_available:
        logger.warning(
            "ElevenLabs not configured (missing voice ID or API key) — using gTTS for all scenes."
        )

    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    narrations = [s.narration for s in scenes]

    for i, scene in enumerate(scenes):
        dest = audio_dir / f"seg{scene.scene_number}.mp3"
        logger.info(f"Audio — scene {scene.scene_number}/{len(scenes)}: '{scene.narration[:50]}...'")

        if elevenlabs_available:
            prev_text = narrations[i - 1] if i > 0 else ""
            next_text = narrations[i + 1] if i < len(scenes) - 1 else ""
            try:
                audio_bytes = _tts_request(
                    text=scene.narration,
                    previous_text=prev_text,
                    next_text=next_text,
                    voice_id=vid,
                    api_key=key,
                )
                dest.write_bytes(audio_bytes)
                logger.info(f"  ElevenLabs OK — {len(audio_bytes)} bytes -> {dest.name}")
            except Exception as e:
                logger.warning(f"  ElevenLabs failed scene {scene.scene_number}: {e} — falling back to gTTS")
                _gtts_fallback(scene.narration, dest)
                logger.info(f"  gTTS fallback OK -> {dest.name}")
        else:
            _gtts_fallback(scene.narration, dest)
            logger.info(f"  gTTS OK -> {dest.name}")

        # Trim audio to cap — never stretch.
        # Type 1: 9s cap. Type 2 avatar: 30s cap (passed in). None = skip trim.
        cap = audio_cap_seconds if audio_cap_seconds is not None else config.AUDIO_CLIP_DURATION
        if cap > 0:
            _trim_to_max(dest, cap)

        scene.audio_path = str(dest)

        if progress_callback:
            progress_callback(i + 1, len(scenes))

    return scenes
