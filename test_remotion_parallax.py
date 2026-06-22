"""
test_remotion_parallax.py — Render spring physics + parallax clip via Remotion.

Copies IMAGE_PATH into remotion-test/public/image.jpg, installs deps if needed,
then renders both 4:3 and 9:16 compositions.

Run: python test_remotion_parallax.py
"""
import shutil
import subprocess
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
IMAGE_PATH    = r"C:\Users\HR 1\OneDrive\ドキュメント\ampm-video-pipeline\output\POL-TEST1-20260527-1832\images\scene3_cutaway.jpg"
COMPOSITIONS  = ["Finance-Clip", "Business-Clip", "Politics-Clip", "Culture-Clip", "GlobalAffairs-Clip"]  # render both, comment one out to skip
OUTPUT_DIR    = Path("test_remotion_output")
# ─────────────────────────────────────────────────────────────────────────────

REMOTION_DIR = Path(__file__).parent / "remotion-test"
PUBLIC_DIR   = REMOTION_DIR / "public"
NPX          = shutil.which("npx") or "npx"


def run(cmd: list, cwd: Path, label: str) -> bool:
    print(f"\n>> {label}")
    # shell=True required on Windows — npm/npx are .cmd files, not executables
    result = subprocess.run(
        " ".join(f'"{c}"' if " " in c else c for c in cmd),
        cwd=str(cwd),
        shell=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAILED (exit {result.returncode})")
        return False
    return True


def main():
    image_src = Path(IMAGE_PATH)
    if not image_src.exists():
        print(f"Image not found: {image_src}")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    # Copy image into Remotion public folder
    dest_img = PUBLIC_DIR / "image.jpg"
    shutil.copy2(image_src, dest_img)
    print(f"Image copied -> {dest_img}")

    # Install deps (skips if node_modules exists)
    nm = REMOTION_DIR / "node_modules"
    if not nm.exists():
        print("\nInstalling Remotion dependencies (one-time, ~1 min)...")
        ok = run(["npm", "install"], REMOTION_DIR, "npm install")
        if not ok:
            print("npm install failed. Make sure Node.js is installed.")
            return
    else:
        print("node_modules found — skipping install.")

    # Render each composition
    for comp_id in COMPOSITIONS:
        out_file = OUTPUT_DIR / f"{comp_id}.mp4"
        ok = run(
            [
                NPX, "remotion", "render",
                "src/index.ts",
                comp_id,
                str(out_file.resolve()),
            ],
            REMOTION_DIR,
            f"Rendering {comp_id}",
        )
        if ok:
            print(f"Output -> {out_file.resolve()}")

    print(f"\nAll outputs: {OUTPUT_DIR.resolve()}")
    print("\nTo tune a beat, edit BEAT_CONFIGS in remotion-test/src/ParallaxClip.tsx")


if __name__ == "__main__":
    main()
