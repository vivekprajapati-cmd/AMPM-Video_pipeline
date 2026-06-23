import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── ElevenLabs voice IDs — one per persona ────────────────────────────────────
# Get voice IDs from elevenlabs.io/voice-library
# Filter: Indian accent, Female/Male, Young, Conversational
ELEVENLABS_VOICE_DEFAULT = os.getenv("ELEVENLABS_VOICE_DEFAULT", "")
ELEVENLABS_VOICE_FIN_F_01 = os.getenv("ELEVENLABS_VOICE_FIN_F_01", "")
ELEVENLABS_VOICE_POL_F_01 = os.getenv("ELEVENLABS_VOICE_POL_F_01", "")
ELEVENLABS_VOICE_BIZ_M_01 = os.getenv("ELEVENLABS_VOICE_BIZ_M_01", "")
ELEVENLABS_VOICE_POP_F_01 = os.getenv("ELEVENLABS_VOICE_POP_F_01", "")
ELEVENLABS_VOICE_GLO_F_01 = os.getenv("ELEVENLABS_VOICE_GLO_F_01", "")

ELEVENLABS_VOICE_MAP = {
    "FIN-F-01": ELEVENLABS_VOICE_FIN_F_01,
    "POL-F-01": ELEVENLABS_VOICE_POL_F_01,
    "BIZ-M-01": ELEVENLABS_VOICE_BIZ_M_01,
    "POP-F-01": ELEVENLABS_VOICE_POP_F_01,
    "GLO-F-01": ELEVENLABS_VOICE_GLO_F_01,
}

def resolve_voice_id(persona_id: str | None) -> str:
    """Returns the ElevenLabs voice_id for a persona, falling back to default."""
    return (ELEVENLABS_VOICE_MAP.get(persona_id or "", "") or ELEVENLABS_VOICE_DEFAULT).strip()

# ── HeyGen avatar image paths — one per persona ───────────────────────────────
# Real face photos (JPG/PNG), NOT Higgsfield-generated.
# Higgsfield is used only for CUTAWAY infographic images.
HEYGEN_AVATAR_IMG_DEFAULT = os.getenv("HEYGEN_AVATAR_IMG_DEFAULT", "")
HEYGEN_AVATAR_IMG_FIN_F_01 = os.getenv("HEYGEN_AVATAR_IMG_FIN_F_01", "")
HEYGEN_AVATAR_IMG_POL_F_01 = os.getenv("HEYGEN_AVATAR_IMG_POL_F_01", "")
HEYGEN_AVATAR_IMG_BIZ_M_01 = os.getenv("HEYGEN_AVATAR_IMG_BIZ_M_01", "")
HEYGEN_AVATAR_IMG_POP_F_01 = os.getenv("HEYGEN_AVATAR_IMG_POP_F_01", "")
HEYGEN_AVATAR_IMG_GLO_F_01 = os.getenv("HEYGEN_AVATAR_IMG_GLO_F_01", "")

HEYGEN_AVATAR_IMG_MAP = {
    "FIN-F-01": HEYGEN_AVATAR_IMG_FIN_F_01,
    "POL-F-01": HEYGEN_AVATAR_IMG_POL_F_01,
    "BIZ-M-01": HEYGEN_AVATAR_IMG_BIZ_M_01,
    "POP-F-01": HEYGEN_AVATAR_IMG_POP_F_01,
    "GLO-F-01": HEYGEN_AVATAR_IMG_GLO_F_01,
}

def resolve_avatar_image(persona_id: str | None) -> str:
    """Returns the avatar image path for a persona, falling back to default."""
    return (HEYGEN_AVATAR_IMG_MAP.get(persona_id or "", "") or HEYGEN_AVATAR_IMG_DEFAULT).strip()

# ── Model IDs ─────────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"
GROQ_MODEL = "llama-3.3-70b-versatile"          # script generation — primary
GROQ_SUMMARIZE_MODEL = "llama-3.1-8b-instant"   # article summarization — pure extraction, separate TPD quota
GROQ_FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # fallback when primary hits TPD limit
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# ── ElevenLabs voice settings ─────────────────────────────────────────────────
ELEVENLABS_VOICE_SETTINGS = {
    "stability": 0.6,
    "similarity_boost": 0.8,
    "style": 0.0,
    "use_speaker_boost": True,
}
ELEVENLABS_SEED = 42

# ── Higgsfield CLI defaults ───────────────────────────────────────────────────
HIGGSFIELD_IMAGE_MODEL = "nano_banana_2"
HIGGSFIELD_VIDEO_MODEL = "seedance_2_0"
HIGGSFIELD_VIDEO_MODE  = "fast"          # std | fast
HIGGSFIELD_VIDEO_RESOLUTION = "480p"     # 480p = 12 credits/clip, 1080p = significantly more
HIGGSFIELD_IMAGE_RESOLUTION = "1k"
HIGGSFIELD_CLI_TIMEOUT = 900

# Type 1 (standard) — 4 cutaway + 2 avatar, 10s clips
HIGGSFIELD_IMAGE_ASPECT   = "9:16"
HIGGSFIELD_VIDEO_DURATION = 8    # seedance_2_0 fast max = 8s
VIDEO_CLIP_DURATION       = 8
AUDIO_CLIP_DURATION       = 9    # ElevenLabs cap — trim anything over 9s

# Type 2 (split-screen) — 12 cutaway + 2 avatar, 5s clips, 4:3 aspect
TYPE2_IMAGE_ASPECT        = "4:3"
TYPE2_VIDEO_DURATION      = 5    # kling2_6 duration for Type 2 clips
TYPE2_CLIP_DURATION       = 5
TYPE2_AVATAR_DURATION_S   = 30   # each avatar scene is 30 seconds
TYPE2_AVATAR_NARRATION_CHARS = 450  # ~30s of speech at 150 chars/10s
TYPE2_CUTAWAY_COUNT       = 12
TYPE2_AVATAR_COUNT        = 2

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
SYSTEM_PROMPT_PATH = BASE_DIR / "system_prompt.txt"
AMPM_FINAL_CARD = BASE_DIR / "AMPM-FINAL_CARD.mp4"

OUTPUT_DIR.mkdir(exist_ok=True)

# ── System prompt ─────────────────────────────────────────────────────────────
def load_system_prompt() -> str:
    from prompts import SYSTEM_PROMPT
    return SYSTEM_PROMPT

# ── Env check ─────────────────────────────────────────────────────────────────
def check_env() -> dict[str, bool]:
    return {
        "claude": bool(ANTHROPIC_API_KEY.strip()),
        "groq": bool(GROQ_API_KEY.strip()),
        "elevenlabs": bool(ELEVENLABS_API_KEY.strip() and (ELEVENLABS_VOICE_DEFAULT.strip() or any(v.strip() for v in ELEVENLABS_VOICE_MAP.values()))),
        "heygen": bool(HEYGEN_API_KEY.strip()),
        "heygen_avatar": bool(HEYGEN_AVATAR_IMG_DEFAULT.strip() or any(v.strip() for v in HEYGEN_AVATAR_IMG_MAP.values())),
    }
