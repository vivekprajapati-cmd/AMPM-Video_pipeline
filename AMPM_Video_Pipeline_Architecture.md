# AM:PM — AI News Video Production Pipeline

## System Architecture Document
**Version:** 1.0
**Date:** May 21, 2026
**Target:** 60-second vertical AI news videos at scale

---

## 1. PIPELINE OVERVIEW

```
┌─────────────────────────────────────────────────────────┐
│                   STREAMLIT UI                          │
│  Input: topic, beat, language, tone, persona preference │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│               CLAUDE API (Anthropic)                    │
│  → Scene-wise script (6 scenes × 10s each)             │
│  → Image prompts per scene                             │
│  → Scene type assignment (AVATAR vs CUTAWAY)            │
│  → Story template selection                             │
│  → Persona selection                                    │
└────────────────────┬────────────────────────────────────┘
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
┌──────────────┐ ┌─────────────────────────────────────┐
│ ELEVENLABS   │ │ HIGGSFIELD CLI                      │
│ API          │ │ (single auth, single credit pool)   │
│              │ │                                     │
│ 6 individual │ │ Cutaway images: nano_banana_2       │
│ audio clips  │ │   (4 images, CUTAWAY scenes only)   │
│ one per scene│ │                                     │
│              │ │ Cutaway animation: seedance_2_0     │
│              │ │   --start-image ...                 │
│              │ │   (4 animated clips)                │
└──────┬───────┘ └───────────────┬─────────────────────┘
       │                         │
       ▼                         │
┌──────────────────────────┐     │
│ HEYGEN API               │     │
│ (Avatar 4 / Talking Photo│     │
│                          │     │
│ Input: persona face photo│     │
│      + ElevenLabs audio  │     │
│ Output: talking head MP4 │     │
│ (audio baked in)         │     │
│                          │     │
│ No file hosting needed — │     │
│ assets uploaded to HeyGen│     │
└──────────┬───────────────┘     │
           │                     │
           ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│                    FFMPEG (Local)                        │
│  → Merge ElevenLabs audio onto cutaway video clips      │
│  → Lipsync clips from HeyGen already have audio baked in│
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                OUTPUT: 6 CLIPS                          │
│  → 2 avatar lipsync clips (from HeyGen Avatar 4)        │
│  → 4 animated cutaway clips with narration (Higgsfield) │
│  → Edit timeline JSON for editor handoff                │
└─────────────────────────────────────────────────────────┘
```

---

## 2. API SERVICES — COMPLETE SETUP GUIDE

### 2A. ANTHROPIC (Claude API) — Script Generation

**What it does:** Takes topic input, generates scene-by-scene script, image prompts, story template, persona selection.

**Signup:** https://console.anthropic.com
**Pricing page:** https://www.anthropic.com/pricing
**Model to use:** `claude-sonnet-4-20250514`

**Pricing:**
- Input: $3 / million tokens
- Output: $15 / million tokens
- Per video script generation: ~$0.02–0.05

**API endpoint:**
```
POST https://api.anthropic.com/v1/messages
Headers:
  x-api-key: YOUR_API_KEY
  anthropic-version: 2023-06-01
  Content-Type: application/json
```

**How to get API key:**
1. Go to https://console.anthropic.com
2. Sign up / sign in
3. Go to API Keys section
4. Create new key
5. Copy and store securely

**Rate limits (free tier):** 5 RPM, 20K tokens/min
**Rate limits (paid tier 1):** 50 RPM, 40K tokens/min
**Recommended plan:** Pay-as-you-go. At $0.03/video, even 1000 videos = $30.

---

### 2B. ELEVENLABS — Voice/Narration Generation

**What it does:** Generates 6 individual audio clips, one per scene. Each clip is a complete sentence/thought with natural start and end. No ffmpeg splitting needed.

**Signup:** https://elevenlabs.io
**API docs:** https://elevenlabs.io/docs/capabilities/text-to-speech
**Dashboard:** https://elevenlabs.io/app/speech-synthesis

**Plans (as of May 2026):**

| Plan | Monthly Cost | Credits | ~Minutes of Audio | Overage Rate |
|------|-------------|---------|-------------------|--------------|
| Free | $0 | 10,000 | ~10 min | N/A |
| Starter | $5/mo | 30,000 | ~30 min | $0.30/1K chars |
| Creator | $22/mo | 100,000 | ~100 min | $0.30/1K chars |
| Pro | $99/mo | 500,000 | ~500 min | $0.24/1K chars |
| Scale | $330/mo | 2,000,000 | ~2000 min | $0.18/1K chars |

**Per-video math:**
- 60s narration ≈ 150 words ≈ 900 characters total across 6 scenes
- ElevenLabs charges per character, not per API call — 6 calls cost the same as 1
- ~1 credit per character = ~900 credits per video
- Creator plan (100K credits) = ~111 videos/month
- Pro plan (500K credits) = ~555 videos/month

**Recommended plan:** Creator ($22/mo) to start. Upgrade to Pro ($99/mo) when scaling.

**Why 6 separate calls instead of 1 full audio + ffmpeg split:**
- ffmpeg splits at exact timestamps regardless of speech — words get chopped mid-syllable
- 6 separate calls = each clip is a complete thought with natural start/end
- Same cost (character-based billing, not per-call)
- Each scene is independently regenerable if audio sounds off
- Natural duration per scene (~8-12s) instead of forced 10.000s blocks

**API call per scene (with prosody context):**
```python
import requests

def generate_scene_audio(scene_text, previous_scene_text, next_scene_text,
                         voice_id, api_key, seed=42):
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        },
        json={
            "text": scene_text,
            "model_id": "eleven_multilingual_v2",
            "seed": seed,
            "previous_text": previous_scene_text or "",
            "next_text": next_scene_text or "",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
    )
    return response.content  # raw MP3 bytes

# Generate all 6 scenes with prosody context
for i, scene in enumerate(scenes):
    prev_text = scenes[i-1].narration if i > 0 else None
    next_text = scenes[i+1].narration if i < 5 else None
    audio_bytes = generate_scene_audio(
        scene.narration, prev_text, next_text,
        voice_id=VOICE_ID, api_key=ELEVENLABS_KEY, seed=42
    )
    with open(f"output/{video_id}/segments/seg{i+1}.mp3", "wb") as f:
        f.write(audio_bytes)
```

**Consistency across 6 calls:**
- `seed=42` (same seed for all 6 calls) — keeps voice timbre consistent
- `previous_text` / `next_text` — gives ElevenLabs prosody context so scene 3 doesn't sound like a brand new thought, it flows from scene 2
- `stability: 0.6` (slightly higher than default 0.5) — reduces variation between calls
- Same `voice_id` and `model_id` across all calls — obvious but critical

**How to get API key:**
1. Go to https://elevenlabs.io
2. Sign up / sign in
3. Click your profile icon → Profile + API key
4. Copy your API key

**Voice selection:**
- Browse voices at https://elevenlabs.io/voice-library
- Filter by: Indian accent, Female/Male, Young, Conversational
- Note the `voice_id` from the URL when you select one
- For Hinglish: use Multilingual v2 model (`eleven_multilingual_v2`)

---

### 2C. HIGGSFIELD CLI — Image Generation + Cutaway Animation

**What it does:** Single tool for two jobs — generates all 6 base images (Nano Banana 2) AND animates 4 cutaway scenes (Seedance 2.0). Uses your existing Higgsfield account and credit pool.

**GitHub:** https://github.com/higgsfield-ai/cli
**Platform:** https://higgsfield.ai
**Pricing:** https://higgsfield.ai/pricing

**Install:**
```bash
# npm (recommended)
npm install -g @higgsfield/cli

# or curl
curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh

# or brew
brew update && brew upgrade higgsfield
```

**Requires:** Node.js 18+

**Authenticate (one-time, opens browser):**
```bash
higgsfield auth login
```
This stores your session locally. No API key needed — it uses your Higgsfield account directly.

**Your current plan:** Plus ($34–49/mo), 1,000 credits/month.

**Credit costs (verified via MCP):**
- Nano Banana 2 image: 1.5 credits per image
- Seedance 2.0 video (10s, 720p): 45 credits per clip
- Seedance 2.0 video (5s, 720p): 22.5 credits per clip

**Per-video credit math:**
- 6 images × 1.5 credits = 9 credits
- 4 cutaway animations × 45 credits = 180 credits
- **Total: ~189 credits per video**
- 1,000 credits ÷ 189 = ~5 videos/month on Plus plan

**Note:** This is the main cost bottleneck. Seedance 2.0 at 45 credits per 10s clip is expensive at scale. Options to reduce:
- Use 5s clips instead of 10s (22.5 credits each → 90 credits for 4 cutaways → ~99 credits/video total)
- Check if cheaper models (Kling 2.6 at ~6 credits) work for simple cutaway animation
- Upgrade to Ultra (3,000 credits/mo) or Business plan for volume

**CLI commands used in pipeline:**

Generate image:
```bash
higgsfield generate create nano_banana_2 \
  --prompt "A realistic young Indian woman, mid-20s, calm expression, looking directly at camera, modern home office background, soft lighting, chest-up medium close-up, 9:16 vertical. No text no captions no logos no watermark" \
  --aspect_ratio 9:16 \
  --resolution 1k \
  --wait
```

Generate cutaway animation (image-to-video):
```bash
higgsfield generate create seedance_2_0 \
  --prompt "Gentle slow zoom into finance infographic, subtle parallax motion on layered cards, smooth editorial animation" \
  --start-image ./cutaway_scene2.jpg \
  --aspect_ratio 9:16 \
  --duration 10 \
  --resolution 720p \
  --mode std \
  --wait
```

Check job status:
```bash
higgsfield generate get <job_id>
higgsfield generate get <job_id> --json  # machine-readable output
```

List available models:
```bash
higgsfield model list
higgsfield model get seedance_2_0  # see all params for a model
```

**Key CLI features for the pipeline:**
- `--wait` flag blocks until generation completes (no manual polling needed)
- `--json` flag returns machine-parseable output for Python subprocess integration
- Local file paths auto-upload: `--start-image ./local.jpg` stages the file automatically
- Previous job IDs can be used as input: `--start-image <job_id_from_image_gen>`

**How the Streamlit app calls the CLI:**
```python
import subprocess, json

def generate_image(prompt, aspect_ratio="9:16"):
    result = subprocess.run(
        ["higgsfield", "generate", "create", "nano_banana_2",
         "--prompt", prompt,
         "--aspect_ratio", aspect_ratio,
         "--resolution", "1k",
         "--wait", "--json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def animate_cutaway(image_path, motion_prompt, duration=10):
    result = subprocess.run(
        ["higgsfield", "generate", "create", "seedance_2_0",
         "--prompt", motion_prompt,
         "--start-image", image_path,
         "--aspect_ratio", "9:16",
         "--duration", str(duration),
         "--resolution", "720p",
         "--mode", "std",
         "--wait", "--json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)
```

**Image prompt rules (from your system doc):**
- Always include: "No captions, no subtitles, no text overlay, no logos, no watermark, no UI"
- Always use 9:16 aspect ratio for vertical video
- Avatar images: close-up, front-facing, well-lit, single subject
- Cutaway images: editorial style, clean space for manual overlays

---

### 2D. HEYGEN — Avatar Lipsync Video (Avatar 4 / Talking Photo)

**What it does:** Takes a real photo of the avatar + ElevenLabs audio clip → produces a 9:16 MP4 with Avatar 4 quality lip sync and facial motion. No static video conversion needed — HeyGen accepts the image directly.

**Important distinction:**
- Higgsfield is used ONLY for infographic/cutaway scene images and animation.
- Avatar scene images (scenes 1 and 4) come from real persona photos you supply — NOT Higgsfield-generated images.

**Signup:** https://www.heygen.com
**API docs:** https://docs.heygen.com
**Dashboard:** https://app.heygen.com
**Pricing:** Pay-as-you-go, starts at $5

**API endpoints used:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `https://upload.heygen.com/v1/asset` | POST | Upload avatar image + audio → asset ids |
| `https://api.heygen.com/v2/video/generate` | POST | Submit talking photo lipsync job |
| `https://api.heygen.com/v1/video_status.get` | GET | Poll job status |

**Auth:** `X-Api-Key: YOUR_HEYGEN_API_KEY` on all requests.

**Step 1 — Upload image and audio (binary upload):**
```python
import requests

def upload_asset(file_path, content_type, api_key):
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://upload.heygen.com/v1/asset",
            headers={"x-api-key": api_key, "Content-Type": content_type},
            data=f,
        )
    return resp.json()["data"]["id"]  # → talking_photo_id or audio_asset_id

talking_photo_id = upload_asset("avatar.jpg", "image/jpeg", API_KEY)
audio_asset_id   = upload_asset("seg1.mp3",  "audio/mpeg",  API_KEY)
```

**Step 2 — Submit lipsync job:**
```python
resp = requests.post(
    "https://api.heygen.com/v2/video/generate",
    headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"},
    json={
        "test": False,
        "use_avatar_iv_model": True,
        "dimension": {"width": 720, "height": 1280},  # 9:16
        "video_inputs": [{
            "character": {
                "type": "talking_photo",
                "talking_photo_id": talking_photo_id,
            },
            "voice": {
                "type": "audio",
                "audio_asset_id": audio_asset_id,
            },
        }],
    },
)
video_id = resp.json()["data"]["video_id"]
```

**Step 3 — Poll until complete:**
```python
import time
while True:
    r = requests.get(
        "https://api.heygen.com/v1/video_status.get",
        headers={"X-Api-Key": API_KEY},
        params={"video_id": video_id},
    )
    data = r.json()["data"]
    if data["status"] == "COMPLETED":
        video_url = data["video_url"]
        break
    time.sleep(10)
```

**How to get API key:**
1. Go to https://www.heygen.com and sign up
2. Go to Settings → API
3. Copy your API key
4. Set `HEYGEN_API_KEY=your_key` in .env

**No external file hosting needed** — assets are uploaded directly to HeyGen and referenced by asset ID internally.

---

### 2E. FFMPEG — Audio Merge (Local, Free)

**What it does:** One job in the pipeline:
- Merges ElevenLabs narration audio onto Higgsfield cutaway animated videos.

Static video conversion is no longer needed — HeyGen accepts the avatar photo directly.
Lipsync clips from HeyGen already have audio baked in, so no merge needed for those.

**Install:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

**Merge narration audio onto cutaway video:**
```bash
# Use -shortest to match the shorter of video/audio
ffmpeg -i cutaway_scene3.mp4 -i seg3.mp3 \
  -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 -shortest \
  scene3_final.mp4
```

**Concat all 6 final clips (if needed):**
```bash
# Create file list
echo "file 'scene1_final.mp4'" > filelist.txt
echo "file 'scene2_final.mp4'" >> filelist.txt
echo "file 'scene3_final.mp4'" >> filelist.txt
echo "file 'scene4_final.mp4'" >> filelist.txt
echo "file 'scene5_final.mp4'" >> filelist.txt
echo "file 'scene6_final.mp4'" >> filelist.txt

ffmpeg -f concat -safe 0 -i filelist.txt -c copy final_video.mp4
```

---

## 3. STREAMLIT APP STRUCTURE

```
ampm-video-pipeline/
│
├── app.py                    # Main Streamlit UI
├── config.py                 # API keys, model configs, defaults
├── requirements.txt          # Python dependencies
│
├── core/
│   ├── script_generator.py   # Claude API → scene-wise script
│   ├── voice_generator.py    # ElevenLabs API → 6 audio clips
│   ├── higgsfield_cli.py     # Higgsfield CLI → infographic images + cutaway animation
│   ├── lipsync_generator.py  # HeyGen Avatar 4 → talking photo lipsync
│   └── ffmpeg_utils.py       # ffmpeg → audio merge on cutaway clips only
│
├── models/
│   ├── scene.py              # Scene dataclass
│   ├── persona.py            # Persona bank definitions
│   └── templates.py          # Story template definitions
│
├── utils/
│   ├── file_hosting.py       # HeyGen asset upload helper
│   ├── downloader.py         # Download generated assets
│   └── cli_runner.py         # subprocess wrapper for Higgsfield CLI with --json parsing
│
├── avatars/                  # Real persona face photos for HeyGen lipsync
│   ├── fin_f_01.jpg
│   ├── pol_f_01.jpg
│   └── ...
│
├── output/                   # Generated assets per video
│   └── {video_id}/
│       ├── audio/
│       │   ├── seg1.mp3 ... seg6.mp3  (ElevenLabs, one per scene)
│       ├── images/
│       │   ├── scene2_cutaway.jpg ... scene6_cutaway.jpg  (Higgsfield, CUTAWAY only)
│       ├── clips/
│       │   ├── scene1_lipsync.mp4  (HeyGen Avatar 4)
│       │   ├── scene4_lipsync.mp4  (HeyGen Avatar 4)
│       │   ├── scene2_cutaway.mp4 ... scene6_cutaway.mp4  (Higgsfield seedance_2_0)
│       ├── final/
│       │   ├── scene2_final.mp4 ... scene6_final.mp4  (cutaways with audio merged)
│       └── edit_timeline.json
│
└── .env                      # API keys (gitignored)
```

**requirements.txt:**
```
streamlit>=1.35.0
anthropic>=0.40.0
requests>=2.31.0
python-dotenv>=1.0.0
```

**System dependencies (must be installed separately):**
```bash
# Higgsfield CLI (Node.js 18+ required)
npm install -g @higgsfield/cli
higgsfield auth login  # one-time browser auth

# ffmpeg
brew install ffmpeg  # or apt install ffmpeg
```

**.env file:**
```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=xi-...
ELEVENLABS_VOICE_ID=voice_id_here
HEYGEN_API_KEY=your_heygen_api_key
HEYGEN_AVATAR_IMG_DEFAULT=./avatars/default.jpg
```

**Note:** Higgsfield CLI does NOT use an API key in .env. It uses browser-based OAuth stored locally after `higgsfield auth login`. No key management needed.

---

## 4. STREAMLIT UI FLOW

### Screen 1: Input
- Topic (text input)
- Beat selector: Finance / Politics / Business / Culture / Global Affairs
- Language: English / Hindi / Hinglish
- Tone: Calm / Energetic / Serious / Casual
- Persona override (optional): FIN-F-01, POL-F-01, BIZ-M-01, POP-F-01, GLO-F-01
- Avatar photo upload (JPG/PNG) — real persona face photo for HeyGen lipsync
- Mode: [PACK] Prompts Only / [ASSET] Generate Assets / [FULL] Full Pipeline

### Screen 2: Script Review
- Claude-generated 6-scene breakdown displayed
- Each scene shows: narration text, scene type (AVATAR/CUTAWAY), image prompt
- Editable — user can modify any scene before proceeding
- Story template shown with reasoning
- Selected persona shown

### Screen 3: Generation Progress
- Progress bars for each API call
- Step 1: Generating 6 narration audio clips (ElevenLabs API)
- Step 2: Generating 4 cutaway images (Higgsfield CLI → nano_banana_2, CUTAWAY scenes only)
- Step 3: Generating 2 lipsync videos (HeyGen Avatar 4 — photo upload + audio upload → MP4)
- Step 4: Generating 4 cutaway animations (Higgsfield CLI → seedance_2_0)
- Step 5: Merging audio onto cutaway videos (ffmpeg)

### Screen 4: Output
- 6 final clips displayed with video players
- Edit timeline JSON displayed
- Download all button (ZIP of all clips + timeline)
- Overlay instructions shown per scene

---

## 5. SCENE BREAKDOWN LOGIC

For a 60-second video, the system generates exactly 6 scenes:

| Scene | Target Duration | Type | Audio | Visual |
|-------|----------------|------|-------|--------|
| 1 | ~8-12s | AVATAR | Individual ElevenLabs clip | Lipsync talking head |
| 2 | ~8-12s | CUTAWAY | Individual ElevenLabs clip | Animated infographic |
| 3 | ~8-12s | CUTAWAY | Individual ElevenLabs clip | Animated infographic |
| 4 | ~8-12s | AVATAR | Individual ElevenLabs clip | Lipsync talking head |
| 5 | ~8-12s | CUTAWAY | Individual ElevenLabs clip | Animated infographic |
| 6 | ~8-12s | CUTAWAY | Individual ElevenLabs clip | Animated infographic |

**Duration note:** Each scene's audio is generated individually by ElevenLabs, so durations are natural (~8-12s) rather than a forced 10.000s. The total video will be approximately 60s but may vary by ±5s. Claude should be prompted to write scene narrations that are roughly 25 words each (≈10s spoken) to stay close to the 60s target.

**Rules:**
- Scenes 1 and 4 are ALWAYS avatar (gives 20s avatar screen time)
- Scenes 2, 3, 5, 6 are ALWAYS cutaway (gives 40s cutaway time)
- Scene 1 = hook (avatar delivers the hook directly to camera)
- Scene 4 = midpoint return (avatar re-engages audience)
- This ordering is default. System doc templates can override.

---

## 6. FILE HOSTING

**No external file hosting required.**

- Higgsfield CLI accepts local file paths directly — handles its own uploads internally.
- HeyGen accepts binary file uploads to its own asset endpoint (`upload.heygen.com/v1/asset`) and references them by asset ID internally. No public URLs needed.
- ffmpeg runs locally.

All pipeline steps work entirely from local disk. The only network calls are to the three API services (ElevenLabs, HeyGen, Higgsfield).

---

## 7. COST SUMMARY

### Per-Video Cost Breakdown

| Service | What | Cost |
|---------|------|------|
| Claude API | Script generation | ~$0.03 |
| ElevenLabs | 60s narration (~900 chars) | ~$0.27 (Creator plan) |
| Higgsfield CLI | 4 cutaway images (Nano Banana 2) | 6 credits |
| Higgsfield CLI | 4 cutaway animations (Seedance 2.0, 10s each) | 180 credits |
| HeyGen Avatar 4 | 2 × ~10s talking photo lipsync | check heygen.com/pricing |
| ffmpeg | Audio merge on cutaway clips | $0 |
| **TOTAL** | | **186 Higgsfield credits + ~$0.30 cash + HeyGen usage** |

**Higgsfield credit cost in dollars (Plus plan, 1,000 credits for ~$40):**
- 186 credits ≈ $7.44 per video (Higgsfield portion only)

**Cost reduction options:**
- Use 5s cutaway clips instead of 10s: 4 × 22.5 = 90 credits → lower Higgsfield cost
- Check if Kling 2.6 (~6 credits/clip) works for cutaway animation → 4 × 6 = 24 credits
- Upgrade Higgsfield to Ultra plan (3,000 credits/mo) for volume

### Monthly Service Costs (Fixed)

| Service | Plan | Monthly Cost |
|---------|------|-------------|
| ElevenLabs | Creator | $22/mo |
| Higgsfield | Plus (existing) | $34–49/mo |
| HeyGen | Pay-as-you-go | $5 minimum + usage |
| Claude API | Pay-as-you-go | ~$0/mo fixed |

### API Keys Required (Total: 3)

| Service | Auth Method |
|---------|------------|
| Anthropic (Claude) | API key in .env |
| ElevenLabs | API key in .env |
| HeyGen | API key in .env |
| Higgsfield CLI | Browser OAuth (no key needed in code) |

---

## 8. PROCESS FLOW — STEP BY STEP

### Step 1: User inputs topic in Streamlit
User enters: "RBI credit growth data shows services sector leading"
Selects: Beat = Finance, Language = Hinglish, Tone = Calm

### Step 2: Claude generates scene breakdown
System prompt includes your full production agent instructions.
Claude returns JSON:
```json
{
  "video_id": "FIN-RBI-CREDIT-20260521",
  "persona": "FIN-F-01",
  "template": "TEMPLATE_A_EXPLAINER",
  "angle": "India's credit growth story is shifting from personal loans to services sector",
  "scenes": [
    {
      "scene_number": 1,
      "type": "AVATAR",
      "duration_seconds": 10,
      "narration": "India ki credit growth story badal rahi hai. Ab yeh sirf personal loans ke baare mein nahi hai.",
      "image_prompt": "A realistic young Indian woman in her mid-20s, calm expression, looking directly at camera, modern home office background with soft lighting, wearing a casual smart top, 9:16 vertical, chest-up medium close-up, no text no captions no logos no watermark",
      "overlay_text": null
    },
    {
      "scene_number": 2,
      "type": "CUTAWAY",
      "duration_seconds": 10,
      "narration": "Services sector ne sabse zyada growth lead ki. Manufacturing aur agriculture peeche reh gaye.",
      "image_prompt": "Clean vertical editorial infographic showing three stacked visual cards representing services sector, manufacturing, and agriculture. Modern finance style, dark background, symbolic icons for each sector, empty space for manual labels, no generated text no captions no logos no watermark, 9:16 aspect ratio",
      "animation_prompt": "Gentle slow zoom in, subtle parallax motion on layered cards, each card slightly shifts to reveal depth, smooth editorial animation, no camera shake",
      "overlay_text": "Services leads credit growth"
    }
  ]
}
```

### Step 3: ElevenLabs generates 6 individual audio clips
- For each scene, call ElevenLabs TTS API with that scene's narration text
- Use `previous_text` and `next_text` parameters for prosody continuity
- Use same `seed=42` across all 6 calls for voice consistency
- Each call returns a complete MP3 for that scene — no splitting needed
- Audio durations will be natural (~8-12s per scene, not forced 10.000s)

### Step 4: Higgsfield CLI generates 6 images (parallel with Step 3)
- For each scene, run `higgsfield generate create nano_banana_2` with the image prompt
- Use `--wait --json` flags to block and get machine-readable output
- Save images locally from the returned CDN URLs

### Step 5: HeyGen generates 2 talking photo lipsync clips
- For scenes 1 and 4 (type=AVATAR):
  - Upload persona's real face photo to HeyGen asset endpoint → `talking_photo_id`
  - Upload ElevenLabs audio segment to HeyGen asset endpoint → `audio_asset_id`
  - POST to `/v2/video/generate` with `use_avatar_iv_model: true`, 720×1280 dimension
  - Poll `/v1/video_status.get` until status == "COMPLETED"
  - Download resulting MP4 (audio baked in, no ffmpeg needed for avatar scenes)
  - No static video conversion needed — HeyGen accepts the photo directly
  - No external file hosting needed — assets uploaded directly to HeyGen

### Step 7: Higgsfield CLI generates 4 cutaway animations
- For scenes 2, 3, 5, 6 (type=CUTAWAY):
  - Run `higgsfield generate create seedance_2_0` with `--start-image` pointing to the cutaway image
  - Use `--wait --json`
  - Download resulting MP4 from returned URL

### Step 8: ffmpeg merges audio onto cutaways
- Cutaway videos from Seedance 2.0 may have AI-generated audio or be silent
- Replace/merge the correct narration audio onto each cutaway:
```bash
ffmpeg -i cutaway3.mp4 -i seg3.mp3 -c:v copy -c:a aac \
  -map 0:v:0 -map 1:a:0 -shortest scene3_final.mp4
```

### Step 9: Output 6 final clips
- 2 lipsync clips (audio already baked in from HeyGen)
- 4 cutaway clips (narration merged via ffmpeg)
- Edit timeline JSON for editor handoff
- ZIP archive for download

---

## 9. WHAT YOUR EDITORS DO MANUALLY

The pipeline outputs 6 raw clips. Editors then:
1. Import 6 clips into editing software (CapCut / Premiere / DaVinci)
2. Arrange per edit timeline
3. Add text overlays (from the overlay suggestions in the JSON)
4. Add lower-thirds, captions, AM:PM branding
5. Add transitions between clips
6. Color grade if needed
7. Export final 9:16 vertical video

---

## 10. KNOWN LIMITATIONS + WORKAROUNDS

**Higgsfield credit burn on Seedance 2.0:**
At 45 credits per 10s clip, 4 cutaways = 180 credits per video. On your Plus plan (1,000 credits/mo), that's ~5 videos before credits run out. Mitigation options:
- Use 5s clips (22.5 credits each) and let editors extend in post
- Test Kling 2.6 (~6 credits/clip) for simple editorial animations — run `higgsfield model get kling2_6` to check if it accepts `--start-image`
- Upgrade to Ultra plan (3,000 credits/mo) or buy top-up packs (~$5/100 credits)

**HeyGen lipsync quality depends on photo quality:**
Use a front-facing, well-lit, high-resolution photo for each persona. Side angles or low-res photos will degrade lip sync accuracy. One good photo per persona is sufficient — it gets re-uploaded each time (assets are ephemeral on HeyGen's free tier).

**Rate limiting:**
- ElevenLabs: varies by plan (5-15 concurrent requests)
- Higgsfield CLI: subject to plan-level queue limits (Plus: 4 images + 4 videos simultaneous)
- HeyGen: varies by plan — run avatar scenes sequentially to stay within limits
- Build sequential processing with retry logic in the Streamlit app
