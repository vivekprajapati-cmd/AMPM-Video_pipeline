"""
test_higgsfield_drama.py — Higgsfield model tester for drama scenes.

Story: Mumbai local train stabbing — Mayank Lohar, June 24 2026.
Each scene: generate reference image → animate it → save clip.

Usage:
    python test_higgsfield_drama.py
    python test_higgsfield_drama.py --model kling2_6
    python test_higgsfield_drama.py --model seedance_2_0 --scenes 1 3 5
    python test_higgsfield_drama.py --image-only     # skip animation
    python test_higgsfield_drama.py --animate-only   # skip image gen, use existing images

Output: test_output/drama_<timestamp>/
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

IMAGE_MODEL  = "nano_banana_2"
VIDEO_MODELS = ["seedance_2_0", "kling2_6"]   # models to compare
OUTPUT_DIR   = Path("test_output")

HIGGSFIELD_FALLBACK = (
    r"C:\Users\HR 1\AppData\Roaming\fnm\node-versions\v20.20.2\installation\higgsfield.cmd"
)

# ── Art direction (matches screenshot reference) ──────────────────────────────

STYLE = (
    "semi-realistic illustration, graphic novel quality, "
    "cinematic still, detailed linework, warm ambient lighting, "
    "editorial anime aesthetic, high detail background, "
    "9:16 vertical frame"
)

NO_TEXT = (
    "No text, no subtitles, no captions, no watermarks, no logos, no UI"
)

# ── Scenes ────────────────────────────────────────────────────────────────────

SCENES = [
    {
        "id": 1,
        "label": "crowded_train_night",
        "image_prompt": (
            f"Interior of a packed Mumbai local train at 10:30 PM. Rain streaks on the windows. "
            f"Overhead handrails packed with commuters. Harsh fluorescent ceiling lights. "
            f"A 21-year-old man with curly black hair and silver chain necklace stands near the open door. "
            f"Tense atmosphere. {STYLE}. {NO_TEXT}."
        ),
        "animation_prompt": (
            "Slow dolly push in toward the standing figure. Rain visible outside the open door. "
            "Train sways subtly. Overhead lights flicker once. Passengers shift nervously."
        ),
    },
    {
        "id": 2,
        "label": "door_argument",
        "image_prompt": (
            f"Two men face each other in a Mumbai local train, standing near the open coach door. "
            f"Left: young man 21 years old, curly dark hair, black t-shirt, silver chain, jaw clenched. "
            f"Right: older man in dark striped polo shirt, confrontational stance, pointing finger. "
            f"Rain and city lights blurred behind the open door. Low-angle shot, tension at peak. "
            f"{STYLE}. {NO_TEXT}."
        ),
        "animation_prompt": (
            "Slow rack focus from the older man's pointing finger to the younger man's face. "
            "Camera drifts forward. Train lurches. Passengers in background turn to watch."
        ),
    },
    {
        "id": 3,
        "label": "panic_passengers",
        "image_prompt": (
            f"Interior of Mumbai local train. Passengers recoiling in horror, mouths open. "
            f"A woman covers her face. A seated man stands up abruptly, knocking into others. "
            f"Chaos near the door. One person pressing against the far wall. "
            f"Dim train lighting. Extreme emotional distress on every face. "
            f"{STYLE}. {NO_TEXT}."
        ),
        "animation_prompt": (
            "Handheld-style shake as passengers scatter. Quick cut-like pan left then right. "
            "Someone runs past camera. Train continues moving, rain still outside."
        ),
    },
    {
        "id": 4,
        "label": "accused_flees",
        "image_prompt": (
            f"A man in a dark striped polo shirt running through a crowded Mumbai train platform at night. "
            f"Motion blur on his legs. Platform signs above, harsh sodium vapor lighting. "
            f"Back view, face not visible. Other commuters frozen in shock watching him run. "
            f"Dramatic low-angle perspective. {STYLE}. {NO_TEXT}."
        ),
        "animation_prompt": (
            "Camera holds low on the platform as the figure sprints away into distance. "
            "People part to let him through. Depth of field compresses. Platform lights streak."
        ),
    },
    {
        "id": 5,
        "label": "police_scene",
        "image_prompt": (
            f"Mumbai Railway Police officers in khaki uniforms at a local train platform. "
            f"Blue police light casts cold light on the wet platform. "
            f"Night scene, rain, yellow sodium platform lights. "
            f"Officers with radios, serious expressions. Crowd held back behind. "
            f"Wide establishing shot. {STYLE}. {NO_TEXT}."
        ),
        "animation_prompt": (
            "Slow crane-style pull back revealing the full platform scene. "
            "Police radio crackles. Rain falls steadily. Platform crowd watches in silence."
        ),
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_higgsfield() -> str:
    found = shutil.which("higgsfield")
    if found:
        return found
    if Path(HIGGSFIELD_FALLBACK).exists():
        return HIGGSFIELD_FALLBACK
    sys.exit("[ERROR] higgsfield CLI not found. Install: npm install -g @higgsfield/cli")


_UNSAFE = str.maketrans({"&": "and", "|": ",", "<": "", ">": "", "^": ""})

def sanitize(text: str) -> str:
    return text.translate(_UNSAFE)


def run_cmd(cmd: list[str], timeout: int = 60) -> str:
    safe = [sanitize(a) if not a.startswith("--") and a not in
            ("generate", "create", "wait", "get") else a for a in cmd]
    result = subprocess.run(safe, capture_output=True, text=True, timeout=timeout, shell=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    raise RuntimeError(f"Non-JSON output: {raw[:200]}")


def extract_url(response) -> str:
    if isinstance(response, list):
        response = response[0]
    if isinstance(response, str):
        raise RuntimeError(f"Got job ID instead of result: {response}")
    status = response.get("status", "")
    if status == "nsfw":
        raise RuntimeError("NSFW")
    if status == "failed":
        raise RuntimeError(f"Job failed: {response}")
    for key in ("result_url", "output_url", "url", "video_url", "image_url"):
        if response.get(key):
            return response[key]
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
    raise RuntimeError(f"No URL in response: {response}")


def download(url: str, dest: Path):
    print(f"    Downloading → {dest.name} ...", end=" ", flush=True)
    urllib.request.urlretrieve(url, dest)
    size_kb = dest.stat().st_size // 1024
    print(f"{size_kb} KB")


def submit_and_wait(exe: str, args: list[str], wait_timeout: int = 900) -> dict:
    # Step 1: submit
    raw = run_cmd([exe] + args + ["--json"], timeout=60)
    job_id = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            job_id = str(parsed[0])
        elif isinstance(parsed, dict):
            job_id = parsed.get("id") or parsed.get("job_id")
    except json.JSONDecodeError:
        job_id = raw.strip().splitlines()[0].strip()
    if not job_id:
        raise RuntimeError(f"No job ID in: {raw[:200]}")
    print(f"    Job submitted: {job_id}")

    # Step 2: wait
    raw_result = run_cmd(
        [exe, "generate", "wait", job_id, "--timeout", "20m", "--interval", "10s", "--json"],
        timeout=wait_timeout,
    )
    return parse_json(raw_result)

# ── Core operations ───────────────────────────────────────────────────────────

def generate_image(exe: str, prompt: str, out_path: Path) -> Path:
    if out_path.exists():
        print(f"    Image exists — skipping: {out_path.name}")
        return out_path
    print(f"    Generating image [{IMAGE_MODEL}] ...")
    response = submit_and_wait(exe, [
        "generate", "create", IMAGE_MODEL,
        "--prompt", prompt,
        "--aspect_ratio", "9:16",
        "--resolution", "1k",
    ])
    url = extract_url(response)
    download(url, out_path)
    return out_path


def animate_image(exe: str, image_path: Path, prompt: str, model: str, out_path: Path) -> Path:
    if out_path.exists():
        print(f"    Clip exists — skipping: {out_path.name}")
        return out_path
    print(f"    Animating [{model}] ...")

    if model == "kling2_6":
        args = [
            "generate", "create", "kling2_6",
            "--prompt", prompt,
            "--image", str(image_path),
            "--aspect_ratio", "9:16",
            "--duration", "5",
            "--sound", "false",
        ]
    elif model == "seedance_2_0":
        args = [
            "generate", "create", "seedance_2_0",
            "--prompt", prompt,
            "--image", str(image_path),
            "--aspect_ratio", "9:16",
            "--duration", "8",
            "--mode", "fast",
            "--generate_audio", "true",
            "--resolution", "480p",
        ]
    else:
        raise ValueError(f"Unknown model: {model}")

    response = submit_and_wait(exe, args)
    url = extract_url(response)
    download(url, out_path)
    return out_path

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["seedance_2_0", "kling2_6", "both"], default="both",
                        help="Video model to test (default: both)")
    parser.add_argument("--scenes", nargs="+", type=int,
                        help="Scene IDs to run (default: all 5)")
    parser.add_argument("--image-only", action="store_true",
                        help="Only generate images, skip animation")
    parser.add_argument("--animate-only", action="store_true",
                        help="Only animate — requires images to already exist")
    args = parser.parse_args()

    exe = resolve_higgsfield()
    timestamp = time.strftime("%Y%m%d-%H%M")
    run_dir = OUTPUT_DIR / f"drama_test_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    models = (
        ["seedance_2_0", "kling2_6"] if args.model == "both"
        else [args.model]
    )
    scene_ids = set(args.scenes) if args.scenes else {s["id"] for s in SCENES}
    scenes = [s for s in SCENES if s["id"] in scene_ids]

    print(f"\n=== Higgsfield Drama Test ===")
    print(f"Output : {run_dir}")
    print(f"Scenes : {[s['id'] for s in scenes]}")
    print(f"Models : {models}")
    print(f"Mode   : {'image only' if args.image_only else 'animate only' if args.animate_only else 'full'}")
    print()

    results = []

    for scene in scenes:
        print(f"\n── Scene {scene['id']}: {scene['label']} ──")
        img_path = run_dir / f"scene{scene['id']}_image.jpg"

        # Image generation
        if not args.animate_only:
            try:
                generate_image(exe, scene["image_prompt"], img_path)
            except RuntimeError as e:
                print(f"    [FAILED] Image: {e}")
                results.append({"scene": scene["id"], "step": "image", "status": "failed", "error": str(e)})
                continue
        else:
            if not img_path.exists():
                print(f"    [SKIP] No image found at {img_path.name} — run without --animate-only first.")
                continue

        if args.image_only:
            results.append({"scene": scene["id"], "step": "image", "status": "ok", "path": str(img_path)})
            continue

        # Animation — one clip per model
        for model in models:
            clip_path = run_dir / f"scene{scene['id']}_{model}.mp4"
            try:
                animate_image(exe, img_path, scene["animation_prompt"], model, clip_path)
                results.append({"scene": scene["id"], "model": model, "status": "ok", "path": str(clip_path)})
            except RuntimeError as e:
                print(f"    [FAILED] {model}: {e}")
                results.append({"scene": scene["id"], "model": model, "status": "failed", "error": str(e)})

    # Save results summary
    summary_path = run_dir / "results.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n=== Done ===")
    ok  = [r for r in results if r["status"] == "ok"]
    err = [r for r in results if r["status"] == "failed"]
    print(f"Succeeded : {len(ok)}")
    print(f"Failed    : {len(err)}")
    if err:
        for r in err:
            print(f"  Scene {r['scene']} [{r.get('model','image')}]: {r['error']}")
    print(f"Output    : {run_dir}")
    print(f"Summary   : {summary_path.name}")


if __name__ == "__main__":
    main()
