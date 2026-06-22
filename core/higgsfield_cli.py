"""
Higgsfield CLI wrapper — image generation (nano_banana_2) and cutaway animation (seedance_2_0).

Authentication is handled by the CLI itself via `higgsfield auth login` (browser OAuth).
No API key required in code.
"""
import logging
from pathlib import Path

import config
import prompts
from models.scene import Scene
from utils.cli_runner import run_higgsfield
from utils.downloader import download_file

logger = logging.getLogger(__name__)


def _ensure_video_duration(dest: Path, target_seconds: int) -> None:
    """
    If Higgsfield returns a clip shorter than target_seconds (e.g. 5s instead of 10s),
    loop it using ffmpeg to fill exactly target_seconds.
    """
    import subprocess, json as _json

    # Get actual duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(dest)],
        capture_output=True, text=True,
    )
    try:
        actual = float(_json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        logger.warning(f"  Could not probe duration for {dest.name} — skipping duration check.")
        return

    if actual >= target_seconds - 0.5:
        logger.info(f"  Duration OK: {actual:.2f}s")
        return

    logger.warning(f"  Clip is {actual:.2f}s — looping to fill {target_seconds}s.")
    tmp = dest.with_suffix(".loop.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(dest),
        "-t", str(target_seconds),
        "-c", "copy",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        dest.unlink()
        tmp.rename(dest)
        logger.info(f"  Looped to {target_seconds}s -> {dest.name}")
    else:
        logger.warning(f"  Loop failed: {result.stderr[:200]} — keeping original {actual:.2f}s clip.")
        if tmp.exists():
            tmp.unlink()


_GENERIC_MOTION_FALLBACK = (
    "Gentle slow zoom in, subtle parallax motion, smooth editorial animation, "
    "cinematic lighting, no text, no people, no faces, no camera shake"
)

_BEAT_IMAGE_FALLBACK = {
    "Finance": (
        "Bold flat editorial illustration. A single market curve collapsing downward into void, electric lime (#AAFF47) line tracing the fall. "
        "9:16 vertical frame. Subject fills upper two-thirds. Lower third empty for overlay. "
        "Near-black (#0D0D0B) background. Bold, high-contrast. Bloomberg editorial energy. "
        "No text, no numbers, no captions, no subtitles, no labels, no logos, no watermarks, no UI, no faces, no people."
    ),
    "Business": (
        "Bold flat editorial illustration. A growth arrow surging upward, amber (#F5A623) accent on the tip, trajectory confident and forward. "
        "9:16 vertical frame. Subject centered upper frame. Lower third clear. "
        "Warm cream (#F0EDE5) background. Clean vector lines. Startup energy. "
        "No text, no logos, no readable labels, no captions, no subtitles, no watermarks, no UI, no faces, no people."
    ),
    "Politics": (
        "Dark editorial illustration. Two opposing bold forms held in standoff, thin line between them, heavy shadow below. "
        "9:16 vertical frame. Monumental upper composition. Lower third empty. "
        "Near-black (#0A0F1E) background. Slate grey primary forms. Single muted crimson accent. Maximum contrast. "
        "No text, no flags, no party symbols, no captions, no subtitles, no logos, no watermarks, no UI, no faces, no people."
    ),
    "Culture": (
        "Vibrant flat editorial illustration. A vertical cascade of abstract content cards, neon glow radiating upward, scroll energy. "
        "9:16 vertical frame. Diagonal kinetic tension. Lower third clear. "
        "Dark background with vivid purple (#8B5CF6) and electric blue (#3B82F6) neon pop. High saturation. Gen Z energy. "
        "No text, no readable UI, no logos, no icons, no captions, no subtitles, no watermarks, no faces, no people."
    ),
    "Global Affairs": (
        "Dark editorial illustration. Two massive opposing forms pressing toward each other, fragile thin line between them, heavy atmospheric weight. "
        "9:16 vertical frame. Wide monumental composition. Lower third clear. "
        "Deep olive (#3D4A2E) to near-black background. Single blood orange (#92400E) accent on the critical point. Crushed blacks, consequence. "
        "No text, no map labels, no flags, no symbols, no captions, no subtitles, no logos, no watermarks, no UI, no faces, no people."
    ),
}
_GENERIC_IMAGE_FALLBACK = (
    "Bold flat editorial illustration. A single bold form rising through center frame, strong directional vector, high contrast against dark background. "
    "9:16 vertical frame. Lower third completely empty for overlay. "
    "Near-black background. Electric lime (#AAFF47) accent on the apex. Clean, precise, minimal. "
    "No text, no numbers, no captions, no subtitles, no labels, no logos, no watermarks, no UI, no faces, no people."
)


def generate_image(
    prompt: str,
    aspect_ratio: str = config.HIGGSFIELD_IMAGE_ASPECT,
    resolution: str = config.HIGGSFIELD_IMAGE_RESOLUTION,
) -> dict:
    """
    Runs: higgsfield generate create nano_banana_2 --prompt ... --aspect_ratio ... --resolution ... --wait --json
    Returns the parsed JSON response dict.
    """
    return run_higgsfield([
        "generate", "create", config.HIGGSFIELD_IMAGE_MODEL,
        "--prompt", prompt,
        "--aspect_ratio", aspect_ratio,
        "--resolution", resolution,
    ])


_KLING_SUPPORTED_RATIOS = {"16:9", "9:16", "1:1"}

def animate_cutaway(
    image_path: str,
    motion_prompt: str,
    video_model: str = config.HIGGSFIELD_VIDEO_MODEL,
    aspect_ratio: str = config.HIGGSFIELD_IMAGE_ASPECT,
    **kwargs,
) -> dict:
    """
    Animates a cutaway image using the specified video model.

    grok_video  — duration 9s, no sound param.
    kling2_6    — duration 5s, sound off (news content).
                  Supported ratios: 16:9, 9:16, 1:1. 4:3 → remapped to 1:1.
    Returns the parsed JSON response dict.
    """
    if video_model == "kling2_6":
        # Kling 2.6 does not support 4:3 — remap to 1:1
        kling_ratio = aspect_ratio if aspect_ratio in _KLING_SUPPORTED_RATIOS else "1:1"
        if kling_ratio != aspect_ratio:
            logger.info(f"  Kling 2.6 does not support {aspect_ratio} — using {kling_ratio}.")
        args = [
            "generate", "create", "kling2_6",
            "--prompt", motion_prompt,
            "--image", image_path,
            "--aspect_ratio", kling_ratio,
            "--duration", "5",
            "--sound", "false",
        ]
    elif video_model == "seedance_2_0":
        args = [
            "generate", "create", "seedance_2_0",
            "--prompt", motion_prompt,
            "--image", image_path,
            "--aspect_ratio", aspect_ratio,
            "--duration", str(config.HIGGSFIELD_VIDEO_DURATION),
            "--mode", config.HIGGSFIELD_VIDEO_MODE,
            "--generate_audio", "true",
            "--genre", kwargs.get("genre", "auto"),
            "--resolution", config.HIGGSFIELD_VIDEO_RESOLUTION,
        ]
    else:  # grok_video
        args = [
            "generate", "create", "grok_video",
            "--prompt", motion_prompt,
            "--start-image", image_path,
            "--aspect_ratio", aspect_ratio,
            "--duration", str(config.HIGGSFIELD_VIDEO_DURATION),
        ]
    return run_higgsfield(args)


def _extract_url(response) -> str:
    """
    Extracts the output URL from a Higgsfield CLI JSON response.
    Handles dict, list-of-dicts, and nested response shapes.
    Raises descriptive errors for nsfw/failed statuses.
    """
    # If response is a list, unwrap the first element
    if isinstance(response, list):
        if not response:
            raise RuntimeError("Higgsfield returned empty list response.")
        logger.debug(f"Response is a list ({len(response)} items) — using first element.")
        response = response[0]

    # If still a plain string after unwrap, it's a bare job ID — not a completed result
    if isinstance(response, str):
        raise RuntimeError(
            f"Higgsfield returned a job ID instead of a result — job may still be processing: {response}"
        )

    # Check status before looking for URL
    status = response.get("status", "")
    if status == "nsfw":
        raise RuntimeError("NSFW")
    if status == "failed":
        raise RuntimeError(
            f"Higgsfield job failed. Response: {response}"
        )

    # Flat dict
    for key in ("result_url", "output_url", "url", "video_url", "image_url"):
        if response.get(key):
            return response[key]

    # Nested under "result", "data", or "output"
    for container in ("result", "data", "output"):
        sub = response.get(container)
        if isinstance(sub, list) and sub:
            sub = sub[0]
        if isinstance(sub, dict):
            for key in ("result_url", "output_url", "url", "video_url", "image_url"):
                if sub.get(key):
                    return sub[key]
        elif isinstance(sub, str) and sub.startswith("http"):
            return sub

    raise RuntimeError(f"Cannot find output URL in Higgsfield response: {response}")


def generate_all_images(
    scenes: list[Scene],
    output_dir: Path,
    beat: str = "Finance",
    aspect_ratio: str = config.HIGGSFIELD_IMAGE_ASPECT,
    progress_callback=None,
) -> list[Scene]:
    """
    Generates images for CUTAWAY scenes only via Higgsfield CLI.
    AVATAR scenes are skipped — HeyGen uses a pre-registered avatar_id, no image needed.
    Auto-retries with a safe beat fallback if the original prompt is flagged NSFW.
    """
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    cutaway_scenes = [s for s in scenes if s.type == "CUTAWAY"]
    beat_fallback = _BEAT_IMAGE_FALLBACK.get(beat, _GENERIC_IMAGE_FALLBACK)

    for i, scene in enumerate(cutaway_scenes):
        dest = images_dir / f"scene{scene.scene_number}_cutaway.jpg"

        # Skip if already generated (resume support)
        if dest.exists():
            scene.image_path = str(dest)
            logger.info(f"  Scene {scene.scene_number} image already exists — skipping.")
            if progress_callback:
                progress_callback(i + 1, len(cutaway_scenes))
            continue

        # Type 1: use scene_description (NSFW-safe concept) as the Higgsfield prompt.
        # Type 2: LLM generates a fully formatted image_prompt already — use that directly.
        # Fallback chain: image_prompt → scene_description → empty string guard.
        if scene.image_prompt:
            img_prompt = scene.image_prompt
        elif scene.scene_description:
            img_prompt = scene.scene_description
        else:
            img_prompt = ""

        logger.info(f"Image gen — scene {scene.scene_number} ({i+1}/{len(cutaway_scenes)})")
        logger.debug(f"  prompt: {img_prompt[:80]}...")

        try:
            response = generate_image(img_prompt, aspect_ratio=aspect_ratio)
            cdn_url = _extract_url(response)
        except RuntimeError as e:
            if "NSFW" in str(e) and img_prompt != beat_fallback:
                logger.warning(
                    f"  Scene {scene.scene_number} image flagged NSFW — retrying with safe {beat} fallback."
                )
                try:
                    response = generate_image(beat_fallback, aspect_ratio=aspect_ratio)
                    cdn_url = _extract_url(response)
                    logger.info(f"  Fallback image OK — scene {scene.scene_number}")
                except RuntimeError as e2:
                    logger.warning(f"  Scene {scene.scene_number} fallback also failed: {e2} — skipping.")
                    if progress_callback:
                        progress_callback(i + 1, len(cutaway_scenes))
                    continue
            else:
                logger.warning(f"  Scene {scene.scene_number} image failed: {e} — skipping.")
                if progress_callback:
                    progress_callback(i + 1, len(cutaway_scenes))
                continue

        logger.debug(f"  raw response cdn_url: {cdn_url}")
        scene.image_cdn_url = cdn_url

        download_file(cdn_url, dest)
        scene.image_path = str(dest)
        logger.info(f"  Image saved -> {dest.name}")

        if progress_callback:
            progress_callback(i + 1, len(cutaway_scenes))

    return scenes


def animate_cutaway_scenes(
    scenes: list[Scene],
    output_dir: Path,
    beat: str = "Finance",
    video_model: str = config.HIGGSFIELD_VIDEO_MODEL,
    aspect_ratio: str = config.HIGGSFIELD_IMAGE_ASPECT,
    clip_duration: int = config.VIDEO_CLIP_DURATION,
    progress_callback=None,
) -> list[Scene]:
    """
    Animates CUTAWAY scenes via Higgsfield.
    video_model: "grok_video" (14 credits, 9s + loop) or "kling2_6" (10 credits, 10s native).
    Requires scene.image_path to be set (run generate_all_images first).
    Downloads the animated MP4 and sets scene.cutaway_video_path.
    """
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    cutaway_scenes = [s for s in scenes if s.type == "CUTAWAY"]
    beat_fallback = prompts.BEAT_ANIMATION_STYLE.get(beat, _GENERIC_MOTION_FALLBACK)
    seedance_genre = prompts.BEAT_SEEDANCE_GENRE.get(beat, "auto")

    logger.info(f"Animating {len(cutaway_scenes)} cutaway scenes via {video_model}...")

    for i, scene in enumerate(cutaway_scenes):
        dest = clips_dir / f"scene{scene.scene_number}_cutaway.mp4"

        # Skip if already generated (resume support)
        if dest.exists():
            scene.cutaway_video_path = str(dest)
            logger.info(f"  Scene {scene.scene_number} clip already exists — skipping.")
            if progress_callback:
                progress_callback(i + 1, len(cutaway_scenes))
            continue

        if not scene.image_path:
            logger.warning(f"Scene {scene.scene_number} has no image_path — skipping animation.")
            if progress_callback:
                progress_callback(i + 1, len(cutaway_scenes))
            continue

        motion_prompt = scene.animation_prompt or beat_fallback

        logger.info(f"Animate — scene {scene.scene_number} ({i+1}/{len(cutaway_scenes)}) [{video_model}]")
        logger.debug(f"  motion prompt: {motion_prompt[:80]}...")

        try:
            response = animate_cutaway(
                image_path=scene.image_path,
                motion_prompt=motion_prompt,
                video_model=video_model,
                aspect_ratio=aspect_ratio,
                genre=seedance_genre,
            )
            video_url = _extract_url(response)
            download_file(video_url, dest)
            _ensure_video_duration(dest, clip_duration)
            scene.cutaway_video_path = str(dest)
            logger.info(f"  Clip saved -> {dest.name}")
        except RuntimeError as e:
            if "NSFW" in str(e) and motion_prompt != beat_fallback:
                logger.warning(f"  Scene {scene.scene_number} NSFW on custom prompt — retrying with safe fallback.")
                try:
                    response = animate_cutaway(
                        image_path=scene.image_path,
                        motion_prompt=beat_fallback,
                        video_model=video_model,
                        aspect_ratio=aspect_ratio,
                        genre=seedance_genre,
                    )
                    video_url = _extract_url(response)
                    download_file(video_url, dest)
                    _ensure_video_duration(dest, clip_duration)
                    scene.cutaway_video_path = str(dest)
                    logger.info(f"  Retry OK -> {dest.name}")
                except RuntimeError as e2:
                    logger.warning(f"  Scene {scene.scene_number} retry also failed: {e2} — skipping scene.")
            else:
                logger.warning(f"  Scene {scene.scene_number} animation failed: {e} — skipping scene.")

        if progress_callback:
            progress_callback(i + 1, len(cutaway_scenes))

    return scenes
