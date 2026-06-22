"""
test_ken_burns.py — Ken Burns motion presets via ffmpeg.

SIMPLE PRESETS:   single move, fast and aggressive.
COMPOUND PRESETS: 2-3 moves chained via concat — news broadcast style.
CINEMATIC:        stacks vignette + film grain + contrast on top of any preset.

Toggle CINEMATIC = True/False to compare with/without effects.

Run: python test_ken_burns.py
"""
import subprocess
from pathlib import Path


# ── CONFIG ────────────────────────────────────────────────────────────────────
IMAGE_PATH  = r"C:\Users\HR 1\OneDrive\ドキュメント\ampm-video-pipeline\output\POL-TEST1-20260527-1832\images\scene3_cutaway.jpg"
DURATION    = 5            # seconds
OUTPUT_SIZE = "1440x1080"  # 4:3. Use 1080x1920 for 9:16, 1080x1080 for 1:1

# Cinematic effects stack — toggle on/off
CINEMATIC   = True

# Individual effect toggles (only matter when CINEMATIC = True)
USE_CONTRAST   = True   # punch up contrast and shadows — most impactful
USE_VIGNETTE   = True   # darken edges, draw eye to center
USE_GRAIN      = True   # film grain — adds texture, reduces "digital" look
USE_COOL_GRADE = True   # slight cool/desaturated tone — editorial news feel
# ─────────────────────────────────────────────────────────────────────────────

FPS = 30


def _cinematic_filters() -> str:
    """
    Builds the cinematic post-processing filter chain.
    Applied after zoompan + scale.

    curves=strong_contrast  — punchy shadows and highlights
    vignette                — darkens edges, natural lens falloff
    noise                   — film grain (allf=t = temporal, changes per frame)
    colorbalance            — cool midtones = editorial news palette
                              params: rs/gs/bs=shadows, rm/gm/bm=mids, rh/gh/bh=highlights
    """
    parts = []
    if USE_CONTRAST:
        parts.append("curves=preset=strong_contrast")
    if USE_COOL_GRADE:
        # Reduce red mids, boost blue mids slightly — cool editorial tone
        parts.append("colorbalance=rm=-0.04:gm=0:bm=0.03:rh=-0.02:gh=0:bh=0.02")
    if USE_VIGNETTE:
        # angle controls falloff strength (PI/4 = subtle, PI/2 = heavy)
        parts.append("vignette=PI/4")
    if USE_GRAIN:
        # alls=noise strength (8-20 is subtle-to-visible), allf=t = temporal grain
        parts.append("noise=alls=10:allf=t")
    return ",".join(parts)


# ── SIMPLE PRESETS ────────────────────────────────────────────────────────────
SIMPLE_PRESETS = {
    "push_in_fast": (
        "fast push in — aggressive, news energy",
        lambda d: f"zoompan=z='min(1+on*(0.5/{d}),1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:fps={FPS}",
    ),
    "pull_out_fast": (
        "fast pull out from center",
        lambda d: f"zoompan=z='max(1.5-on*(0.5/{d}),1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:fps={FPS}",
    ),
    "diagonal_fast": (
        "fast diagonal drift + zoom — most cinematic",
        lambda d: f"zoompan=z='min(1.1+on*(0.3/{d}),1.4)':x='(iw*0.04)+(on*(iw*0.12/{d}))':y='(ih*0.04)+(on*(ih*0.12/{d}))':d={d}:fps={FPS}",
    ),
    "pan_fast": (
        "fast horizontal pan right to left",
        lambda d: f"zoompan=z='1.3':x='(iw*0.25)-(on*(iw*0.18/{d}))':y='ih/2-(ih/zoom/2)':d={d}:fps={FPS}",
    ),
}


# ── COMPOUND PRESETS ──────────────────────────────────────────────────────────
def _build_compound_presets(total_frames: int) -> dict:
    f       = total_frames
    half    = f // 2
    third   = f // 3
    quarter = f // 4
    rest2   = f - half
    rest3a  = f - third
    rest3b  = f - third * 2

    return {
        "punch_settle": (
            "fast punch in → slow ease back — most news-like",
            [
                (quarter, f"zoompan=z='min(1+on*(0.45/{quarter}),1.45)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={quarter}:fps={FPS}"),
                (f - quarter, f"zoompan=z='max(1.45-on*(0.15/{f - quarter}),1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f - quarter}:fps={FPS}"),
            ]
        ),
        "push_then_pan": (
            "push in → pan across — camera operator style",
            [
                (half, f"zoompan=z='min(1+on*(0.3/{half}),1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={half}:fps={FPS}"),
                (rest2, f"zoompan=z='1.3':x='(iw*0.12)+(on*(iw*0.14/{rest2}))':y='ih/2-(ih/zoom/2)':d={rest2}:fps={FPS}"),
            ]
        ),
        "pull_then_push": (
            "pull out wide → tighten on subject — reveal style",
            [
                (third, f"zoompan=z='max(1.4-on*(0.4/{third}),1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={third}:fps={FPS}"),
                (rest3a, f"zoompan=z='min(1+on*(0.4/{rest3a}),1.4)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={rest3a}:fps={FPS}"),
            ]
        ),
        "drift_refocus": (
            "diagonal drift → reframe → push — 3-move",
            [
                (third, f"zoompan=z='min(1.05+on*(0.15/{third}),1.2)':x='(iw*0.05)+(on*(iw*0.08/{third}))':y='(ih*0.05)+(on*(ih*0.08/{third}))':d={third}:fps={FPS}"),
                (third, f"zoompan=z='1.2':x='(iw*0.13)-(on*(iw*0.08/{third}))':y='(ih*0.13)-(on*(ih*0.04/{third}))':d={third}:fps={FPS}"),
                (rest3b, f"zoompan=z='min(1.2+on*(0.25/{rest3b}),1.45)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={rest3b}:fps={FPS}"),
            ]
        ),
    }


# ── RUNNERS ───────────────────────────────────────────────────────────────────
def _post_filters(base_filter: str, cinematic: bool) -> str:
    """Appends cinematic filters after the base motion filter if enabled."""
    if not cinematic:
        return base_filter
    cine = _cinematic_filters()
    return f"{base_filter},{cine}" if cine else base_filter


def run_simple(image_path: str, name: str, filter_fn, output_dir: Path, frames: int):
    suffix = "_cine" if CINEMATIC else ""
    out = output_dir / f"simple_{name}{suffix}.mp4"
    zp = filter_fn(frames)
    vf = _post_filters(f"{zp},scale={OUTPUT_SIZE}", CINEMATIC)
    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED:\n{result.stderr[-800:]}")
        return False
    print(f"  OK -> {out.name}")
    return True


def run_compound(name: str, segments: list, image_path: str, output_dir: Path):
    suffix = "_cine" if CINEMATIC else ""
    out = output_dir / f"compound_{name}{suffix}.mp4"

    filter_parts = []
    stream_labels = []
    cine = _cinematic_filters() if CINEMATIC else ""

    for i, (frames, zp_filter) in enumerate(segments):
        label = f"s{i}"
        seg_filters = f"{zp_filter},scale={OUTPUT_SIZE}"
        if cine:
            seg_filters += f",{cine}"
        filter_parts.append(f"[0:v]{seg_filters}[{label}]")
        stream_labels.append(f"[{label}]")

    n = len(segments)
    concat_str = "".join(stream_labels) + f"concat=n={n}:v=1:a=0[out]"
    filter_complex = ";".join(filter_parts) + ";" + concat_str

    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED:\n{result.stderr[-800:]}")
        return False
    print(f"  OK -> {out.name}")
    return True


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    image_path = Path(IMAGE_PATH)
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return

    frames = DURATION * FPS
    output_dir = Path("test_ken_burns_output")
    output_dir.mkdir(exist_ok=True)

    cine_label = "ON  (contrast + vignette + grain + color grade)" if CINEMATIC else "OFF"
    print(f"\nImage:      {image_path.name}")
    print(f"Duration:   {DURATION}s  |  Size: {OUTPUT_SIZE}")
    print(f"Cinematic:  {cine_label}")
    print(f"Output:     {output_dir}/\n")

    results = {}

    print("=== SIMPLE (single move) ===")
    for name, (desc, filter_fn) in SIMPLE_PRESETS.items():
        print(f"[{name}] {desc}")
        ok = run_simple(str(image_path), name, filter_fn, output_dir, frames)
        results[f"simple_{name}"] = ok

    print("\n=== COMPOUND (2-3 moves, news style) ===")
    for name, (desc, segments) in _build_compound_presets(frames).items():
        print(f"[{name}] {desc}")
        ok = run_compound(name, segments, str(image_path), output_dir)
        results[f"compound_{name}"] = ok

    print("\n--- Results ---")
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}.mp4")

    print(f"\nAll outputs: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
