"""
Quick test: generate a video from a hardcoded image URL using seedance_2_0 fast.
Run: python test_seedance.py
Output saved to: output/test_seedance.mp4
"""
from pathlib import Path
from utils.cli_runner import run_higgsfield
from utils.downloader import download_file
from core.higgsfield_cli import _extract_url
import config

IMAGE_URL = r"C:\Users\HR 1\OneDrive\ドキュメント\ampm-video-pipeline\output\Culture-SLUG-DRAMA-20260622-1258\images\char2_avatar.jpg"

PROMPT = (
    "Mid 40s male, formal suit, serious expression. Modern office interior, "
    "soft natural light from window. Locked medium close-up, chest-up, eye-level. "
    "No zoom, no shake. Realistic skin texture. Subtle head movement, natural blinking. "
    "Exclude: no captions, no subtitles, no text overlay, no logos, no watermark, no UI. "
    "Dialogue: Our emergency response system is flawed. "
    "We have known about the issues for years, but nothing changes. "
    "Eight lives were lost. We need to take responsibility and make real changes now."
)

OUTPUT = Path("output/test_seedance.mp4")
OUTPUT.parent.mkdir(exist_ok=True)

print(f"Model  : seedance_2_0 --mode fast")
print(f"Image  : {IMAGE_URL}")
print(f"Output : {OUTPUT}")
print("Submitting job — waiting up to 20 min...\n")

response = run_higgsfield([
    "generate", "create", "seedance_2_0",
    "--prompt", PROMPT,
    "--image", IMAGE_URL,
    "--aspect_ratio", "9:16",
    "--duration", "8",
    "--mode", "fast",
    "--generate_audio", "true",
    "--resolution", "480p",
])

print(f"Raw response: {response}")

cdn_url = _extract_url(response)
print(f"CDN URL: {cdn_url}")

download_file(cdn_url, OUTPUT)
print(f"\nDone — {OUTPUT}")
