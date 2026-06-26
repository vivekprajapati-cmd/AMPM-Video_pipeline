"""
stitch.py — standalone FFmpeg stitcher for AMPM video pipeline output folders.

Usage:
    python stitch.py <output_folder_path>

Examples:
    python stitch.py output/CRIME-TRAGEDY-MUMBAI-STAB-DRAMA-20260626-1218
    python stitch.py "C:/Users/HR 1/.../output/Finance-20260526-1837"

Reads script.json, resolves clip order from storyboard, stitches with FFmpeg.
Output: <folder>/FINAL_<video_id>.mp4
"""

import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path


# ── Resolution all clips are normalised to ────────────────────────────────────
TARGET_W = 1080
TARGET_H = 1920
TARGET_FPS = 30


def err(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str):
    print(f"[WARN]  {msg}")


def info(msg: str):
    print(f"[OK]    {msg}")


def probe_duration(path: Path) -> float:
    """Return clip duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def resolve_clips_drama(folder: Path, script: dict) -> list[Path]:
    """
    Drama order (from storyboard):
      0:00-0:02  title card (black + text — generated as cards/title_card.mp4 OR synthesised)
      0:02-0:08  char1_take1
      0:08-0:13  textcard_1
      0:13-0:22  char1_take2
      0:22-0:30  char2_take1
      0:30-0:38  char2_take2
      0:38-0:44  split screen (char1_take3 + char2_take3 side-by-side)
      0:44-0:50  textcard_2
      0:50-1:00  AMPM-FINAL_CARD
    """
    clips_dir = folder / "clips"
    cards_dir = folder / "cards"

    order = []

    # Title card
    title_mp4 = cards_dir / "title_card.mp4"
    if title_mp4.exists():
        order.append(("title_card", title_mp4))
    else:
        warn("title_card.mp4 not found — will generate black card with hook text overlay.")
        tc = script.get("title_card", {})
        hook = tc.get("hook_line", "")
        synth = _make_title_card(hook, folder)
        if synth:
            order.append(("title_card_synth", synth))

    # char1 take1
    _add(order, clips_dir / "char1_take1.mp4", "char1_take1")

    # text card 1
    _add(order, cards_dir / "textcard_1.mp4", "textcard_1")

    # char1 take2
    _add(order, clips_dir / "char1_take2.mp4", "char1_take2")

    # char2 take1 + take2
    _add(order, clips_dir / "char2_take1.mp4", "char2_take1")
    _add(order, clips_dir / "char2_take2.mp4", "char2_take2")

    # split screen — char1_take3 (left) + char2_take3 (right)
    c1t3 = clips_dir / "char1_take3.mp4"
    c2t3 = clips_dir / "char2_take3.mp4"
    if c1t3.exists() and c2t3.exists():
        split_path = folder / "split_screen.mp4"
        if not split_path.exists():
            info("Building split screen from char1_take3 + char2_take3...")
            _make_split_screen(c1t3, c2t3, split_path)
        if split_path.exists():
            order.append(("split_screen", split_path))
    else:
        warn("char1_take3 or char2_take3 missing — split screen skipped.")

    # text card 2
    _add(order, cards_dir / "textcard_2.mp4", "textcard_2")

    # final card
    _add(order, folder / "AMPM-FINAL_CARD.mp4", "AMPM-FINAL_CARD")

    return order


def resolve_clips_type1(folder: Path, script: dict) -> list[Path]:
    """
    Type 1 order: scenes in scene_number order, text cards injected after scenes 2 and 4.
    Final -> clips/scene{N}_final.mp4 (with audio merged) or clips/scene{N}_cutaway.mp4.
    Avatar scenes: clips/scene{N}_lipsync.mp4 or clips/scene{N}_avatar.mp4.
    """
    clips_dir = folder / "clips"
    cards_dir = folder / "cards"
    final_dir = folder / "final"

    scenes = script.get("scenes", [])
    text_cards = script.get("text_cards", [])
    tc_by_pos = {}
    # text cards are injected after scenes 2 and 4
    if len(text_cards) >= 1:
        tc_by_pos[2] = cards_dir / "textcard_1.mp4"
    if len(text_cards) >= 2:
        tc_by_pos[4] = cards_dir / "textcard_2.mp4"

    order = []
    for scene in sorted(scenes, key=lambda s: s["scene_number"]):
        n = scene["scene_number"]
        stype = scene.get("type", "")

        # Prefer final (audio-merged) over raw cutaway
        candidates = [
            final_dir / f"scene{n}_final.mp4",
            clips_dir / f"scene{n}_lipsync.mp4",
            clips_dir / f"scene{n}_avatar.mp4",
            clips_dir / f"scene{n}_cutaway.mp4",
        ]
        found = next((p for p in candidates if p.exists()), None)
        if found:
            order.append((f"scene{n}_{stype}", found))
        else:
            warn(f"Scene {n} ({stype}) — no clip found. Skipped.")

        # Inject text card after this scene if applicable
        if n in tc_by_pos:
            tc_path = tc_by_pos[n]
            if tc_path.exists():
                order.append((f"textcard_after_{n}", tc_path))
            else:
                warn(f"textcard after scene {n} not found — skipped.")

    _add(order, folder / "AMPM-FINAL_CARD.mp4", "AMPM-FINAL_CARD")
    return order


def resolve_clips_type2(folder: Path, script: dict) -> list[Path]:
    """
    Type 2: avatar narrations (full 30s each) + cutaway clips interspersed + text cards.
    """
    clips_dir = folder / "clips"
    cards_dir = folder / "cards"
    final_dir = folder / "final"

    scenes = script.get("scenes", [])
    order = []

    for scene in sorted(scenes, key=lambda s: s["scene_number"]):
        n = scene["scene_number"]
        stype = scene.get("type", "")

        if stype == "TEXT_CARD":
            card_id = scene.get("card_id", "")
            tc_path = cards_dir / f"textcard_{card_id}.mp4"
            if tc_path.exists():
                order.append((f"textcard_{card_id}", tc_path))
            else:
                warn(f"TEXT_CARD scene {n} — textcard_{card_id}.mp4 not found. Skipped.")
            continue

        candidates = [
            final_dir / f"scene{n}_final.mp4",
            clips_dir / f"scene{n}_lipsync.mp4",
            clips_dir / f"scene{n}_avatar.mp4",
            clips_dir / f"scene{n}_cutaway.mp4",
        ]
        found = next((p for p in candidates if p.exists()), None)
        if found:
            order.append((f"scene{n}_{stype}", found))
        else:
            warn(f"Scene {n} ({stype}) — no clip found. Skipped.")

    _add(order, folder / "AMPM-FINAL_CARD.mp4", "AMPM-FINAL_CARD")
    return order


def _add(order: list, path: Path, label: str):
    if path.exists():
        order.append((label, path))
    else:
        warn(f"{label} — {path.name} not found. Skipped.")


def _make_title_card(hook: str, folder: Path) -> Path | None:
    """Synthesise a 2s black card with white hook text via FFmpeg drawtext."""
    out = folder / "cards" / "title_card_synth.mp4"
    out.parent.mkdir(exist_ok=True)
    safe_hook = hook.replace("'", "\\'").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=black:s={TARGET_W}x{TARGET_H}:r={TARGET_FPS}:d=2",
        "-vf", (
            f"drawtext=text='{safe_hook}':fontcolor=white:fontsize=72:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:font=Arial"
        ),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode == 0:
        return out
    warn(f"Title card synthesis failed: {result.stderr[-200:]}")
    return None


def _make_split_screen(left: Path, right: Path, out: Path):
    """
    Side-by-side split screen: left clip on left half, right clip on right half.
    Both scaled to 540x1920, placed at x=0 and x=540.
    Duration = longer of the two clips.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(left),
        "-i", str(right),
        "-filter_complex",
        (
            f"[0:v]scale=540:{TARGET_H},setsar=1[l];"
            f"[1:v]scale=540:{TARGET_H},setsar=1[r];"
            f"[l][r]hstack=inputs=2[v];"
            # mix audio equally if both have audio
            "[0:a][1:a]amix=inputs=2:duration=longest[a]"
        ),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Retry without audio (clips may be silent)
        cmd_noaudio = [
            "ffmpeg", "-y",
            "-i", str(left), "-i", str(right),
            "-filter_complex",
            (
                f"[0:v]scale=540:{TARGET_H},setsar=1[l];"
                f"[1:v]scale=540:{TARGET_H},setsar=1[r];"
                "[l][r]hstack=inputs=2[v]"
            ),
            "-map", "[v]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        subprocess.run(cmd_noaudio, capture_output=True, check=True)


def normalise_clip(src: Path, dest: Path):
    """
    Re-encode clip to consistent spec: 1080x1920, 30fps, H.264, AAC.
    Adds silent audio track if clip has no audio stream.
    Pads with black bars (no crop) if aspect differs.
    """
    # Check if clip has audio
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    )
    has_audio = "audio" in probe.stdout

    vf = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={TARGET_FPS},setsar=1"
    )

    if has_audio:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-pix_fmt", "yuv420p",
            str(dest),
        ]
    else:
        # Add silent audio so concat doesn't break on mixed audio/no-audio clips
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(dest),
        ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Normalise failed for {src.name}:\n{result.stderr[-300:].decode(errors='replace')}")


def stitch(folder_path: str):
    folder = Path(folder_path).resolve()
    if not folder.exists():
        err(f"Folder not found: {folder}")

    script_file = folder / "script.json"
    if not script_file.exists():
        err(f"script.json not found in {folder}")

    with open(script_file, encoding="utf-8") as f:
        script = json.load(f)

    video_id   = script.get("video_id", folder.name)
    video_type = script.get("video_type", "type1")

    print(f"\n=== AMPM Stitcher ===")
    print(f"Folder  : {folder}")
    print(f"Video ID: {video_id}")
    print(f"Type    : {video_type}")
    print()

    # Resolve clip order
    if video_type == "drama":
        ordered = resolve_clips_drama(folder, script)
    elif video_type == "type2":
        ordered = resolve_clips_type2(folder, script)
    else:
        ordered = resolve_clips_type1(folder, script)

    if not ordered:
        err("No clips found — nothing to stitch.")

    print(f"Clips to stitch ({len(ordered)}):")
    for label, path in ordered:
        dur = probe_duration(path)
        print(f"  [{label}]  {path.name}  ({dur:.1f}s)")
    print()

    # Normalise all clips to consistent spec in a temp dir
    tmp_dir = folder / "_stitch_tmp"
    tmp_dir.mkdir(exist_ok=True)

    normalised = []
    for i, (label, src) in enumerate(ordered):
        dest = tmp_dir / f"{i:02d}_{label}.mp4"
        if dest.exists():
            info(f"Already normalised: {dest.name}")
        else:
            print(f"  Normalising {src.name} → {dest.name} ...", end=" ", flush=True)
            try:
                normalise_clip(src, dest)
                print("done")
            except RuntimeError as e:
                print("FAILED")
                warn(str(e))
                continue
        normalised.append(dest)

    if not normalised:
        err("All normalisation steps failed.")

    # Write FFmpeg concat list
    concat_file = tmp_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in normalised:
            f.write(f"file '{p.as_posix()}'\n")

    # Final output path
    out_path = folder / f"FINAL_{video_id}.mp4"

    print(f"\nStitching {len(normalised)} clips → {out_path.name} ...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",   # no re-encode — all clips already normalised
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        err(f"Stitch failed:\n{result.stderr[-500:].decode(errors='replace')}")

    dur = probe_duration(out_path)
    info(f"Final video: {out_path}")
    info(f"Duration   : {dur:.1f}s")

    # Clean up temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stitch.py <output_folder_path>")
        print("Example: python stitch.py output/CRIME-TRAGEDY-MUMBAI-STAB-DRAMA-20260626-1218")
        sys.exit(1)
    stitch(sys.argv[1])
