"""
ffmpeg local subprocess calls.

Two jobs:
1. Convert avatar image → static video (required by Sync.so which needs video input, not images).
2. Merge narration audio onto cutaway video clips.
"""
import json
import logging
import subprocess
from pathlib import Path

from models.scene import Scene

logger = logging.getLogger(__name__)


def _run_ffmpeg(args: list[str]) -> None:
    """Runs ffmpeg with the given args. Raises RuntimeError on non-zero exit."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg error (exit {result.returncode}):\n{result.stderr[-1000:]}"
        )


def get_audio_duration(audio_path: str) -> float:
    """Uses ffprobe to get audio duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr[:300]}")

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def image_to_static_video(
    image_path: str,
    audio_path: str,
    output_path: str,
    fps: int = 25,
) -> str:
    """
    Converts a still image to a looped static video whose duration matches the audio clip.
    Output is a silent MP4 (audio is added by Sync.so or separately).

    Returns output_path.
    """
    duration = get_audio_duration(audio_path)
    _run_ffmpeg([
        "-loop", "1",
        "-i", image_path,
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dimensions
        output_path,
    ])
    return output_path


def merge_audio_onto_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    fade_duration: float = 0.7,
) -> str:
    """
    Merges narration audio onto a cutaway video.
    Output duration = video duration (audio is always shorter, video sets the length).
    Applies a smooth fade-out to the last `fade_duration` seconds of audio
    so the narration ends cleanly rather than hard-cutting.

    Returns output_path.
    """
    audio_dur = get_audio_duration(audio_path)
    fade_start = max(0.0, audio_dur - fade_duration)

    _run_ffmpeg([
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-af", f"afade=t=out:st={fade_start:.3f}:d={fade_duration:.3f}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path,
    ])
    return output_path


def prepare_avatar_static_videos(
    scenes: list[Scene],
    output_dir: Path,
    progress_callback=None,
) -> list[Scene]:
    """
    For all AVATAR scenes: converts image → static video sized to audio duration.
    Sets scene.static_video_path.
    """
    avatar_scenes = [s for s in scenes if s.type == "AVATAR"]
    static_dir = output_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(avatar_scenes):
        if not scene.image_path:
            raise RuntimeError(f"Scene {scene.scene_number} missing image_path")
        if not scene.audio_path:
            raise RuntimeError(f"Scene {scene.scene_number} missing audio_path")

        dest = str(static_dir / f"scene{scene.scene_number}_static.mp4")
        image_to_static_video(scene.image_path, scene.audio_path, dest)
        scene.static_video_path = dest

        if progress_callback:
            progress_callback(i + 1, len(avatar_scenes))

    return scenes


def merge_cutaway_audio(
    scenes: list[Scene],
    output_dir: Path,
    progress_callback=None,
) -> list[Scene]:
    """
    For all CUTAWAY scenes: merges narration audio onto the animated video.
    Sets scene.final_video_path.
    """
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    cutaway_scenes = [s for s in scenes if s.type == "CUTAWAY"]

    for i, scene in enumerate(cutaway_scenes):
        if not scene.cutaway_video_path:
            logger.warning(f"Scene {scene.scene_number} has no video — skipping merge.")
            if progress_callback:
                progress_callback(i + 1, len(cutaway_scenes))
            continue
        if not scene.audio_path:
            logger.warning(f"Scene {scene.scene_number} has no audio — skipping merge.")
            if progress_callback:
                progress_callback(i + 1, len(cutaway_scenes))
            continue

        dest = str(final_dir / f"scene{scene.scene_number}_final.mp4")
        logger.info(f"ffmpeg merge — scene {scene.scene_number} ({i+1}/{len(cutaway_scenes)})")
        merge_audio_onto_video(scene.cutaway_video_path, scene.audio_path, dest)
        scene.final_video_path = dest
        logger.info(f"  Merged -> {Path(dest).name}")

        if progress_callback:
            progress_callback(i + 1, len(cutaway_scenes))

    return scenes


def set_lipsync_as_final(scenes: list[Scene]) -> list[Scene]:
    """
    For AVATAR scenes: lipsync clips already have audio baked in, so just copy the path.
    """
    for scene in scenes:
        if scene.type == "AVATAR" and scene.lipsync_video_path:
            scene.final_video_path = scene.lipsync_video_path
    return scenes
