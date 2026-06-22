"""
AM:PM — AI News Video Production Pipeline
Streamlit UI: 4 screens — Input, Script Review, Generation Progress, Output
"""
import io
import json
import logging
import zipfile
from pathlib import Path

import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

import config
from core.ffmpeg_utils import merge_cutaway_audio, set_lipsync_as_final
from core.higgsfield_cli import animate_cutaway_scenes, generate_all_images
from core.lipsync_generator import generate_lipsync_for_avatar_scenes
from core.script_generator import generate_script, scenes_from_script, summarize_article
from core.voice_generator import generate_audio_for_scenes
from models.persona import PERSONA_BANK, BEAT_TO_PERSONA
from models.scene import Scene
from models.templates import STORY_TEMPLATES

st.set_page_config(
    page_title="AM:PM Video Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Brand CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  .ampm-header {
    background: #0D0D0B;
    color: #AAFF47;
    padding: 1.2rem 1.5rem;
    border-radius: 8px;
    margin-bottom: 1.5rem;
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.5px;
  }
  .scene-card {
    background: #F0EDE5;
    border-left: 4px solid #AAFF47;
    padding: 1rem 1.2rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  .scene-card.avatar { border-left-color: #AAFF47; }
  .scene-card.cutaway { border-left-color: #0D0D0B; }
  .tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .tag-avatar { background: #AAFF47; color: #0D0D0B; }
  .tag-cutaway { background: #0D0D0B; color: #AAFF47; }
  .status-ok { color: #22c55e; font-weight: 600; }
  .status-warn { color: #f59e0b; font-weight: 600; }
  .status-err { color: #ef4444; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Session state initialisation ───────────────────────────────────────────────
def _init_state():
    defaults = {
        "screen": "input",
        "script_data": None,
        "scenes": None,
        "video_id": None,
        "output_dir": None,
        "generation_log": [],
        "final_scenes": None,
        # news source state
        "news_content_edit": "",
        "fetch_status": None,   # None | "ok" | "empty" | "error"
        "fetch_error_msg": "",
        # heygen toggle
        "use_heygen": False,
        "avatar_image_path": None,
        "animation_model": "grok_video",
        "video_type": "type1",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="ampm-header">AM:PM — AI Video Pipeline</div>', unsafe_allow_html=True)


# ── Sidebar: env check ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### LLM Provider")
    provider = st.selectbox(
        "Script generation model",
        ["groq", "claude"],
        index=0,
        format_func=lambda x: "Groq — Llama 3.3 70B (free)" if x == "groq" else "Claude Sonnet (paid)",
        label_visibility="collapsed",
    )
    st.session_state["llm_provider"] = provider

    st.markdown("### Animation Model")
    animation_model = st.selectbox(
        "Animation model",
        ["grok_video", "kling2_6"],
        index=["grok_video", "kling2_6"].index(st.session_state.get("animation_model", "grok_video")),
        format_func=lambda x: "grok-imagine — 14 credits / 9s" if x == "grok_video" else "Kling 2.6 — 10 credits / 10s",
        label_visibility="collapsed",
    )
    st.session_state["animation_model"] = animation_model

    env = config.check_env()
    for key, label in {"groq": "Groq API", "claude": "Claude API"}.items():
        ok = env[key]
        active = (key == provider)
        if ok:
            icon = "status-ok"
            dot = "Connected" + (" — active" if active else "")
        else:
            icon = "status-warn"
            dot = "Not configured"
        st.markdown(f'<span class="{icon}">{label}: {dot}</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Service Status")
    for key, label in {"elevenlabs": "ElevenLabs"}.items():
        ok = env[key]
        icon = "status-ok" if ok else "status-warn"
        dot = "Connected" if ok else "Not configured"
        st.markdown(f'<span class="{icon}">{label}: {dot}</span>', unsafe_allow_html=True)

    if st.session_state.get("use_heygen"):
        for key, label in {"heygen": "HeyGen API", "heygen_avatar": "Avatar image"}.items():
            ok = env[key]
            icon = "status-ok" if ok else "status-warn"
            dot = "Configured" if ok else "Not configured"
            st.markdown(f'<span class="{icon}">{label}: {dot}</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Higgsfield CLI**")
    import subprocess, shutil
    _HIGGSFIELD_FALLBACK = (
        r"C:\Users\HR 1\AppData\Roaming\fnm\node-versions\v20.20.2\installation\higgsfield.cmd"
    )
    _hf_path = shutil.which("higgsfield") or (
        _HIGGSFIELD_FALLBACK if Path(_HIGGSFIELD_FALLBACK).exists() else None
    )
    if _hf_path:
        st.markdown('<span class="status-ok">Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-err">Not found</span>', unsafe_allow_html=True)

    # ── Re-animate from saved images ──────────────────────────────────────────
    if st.session_state.get("output_dir") and st.session_state.get("scenes"):
        output_dir_check = Path(st.session_state["output_dir"])
        images_exist = any((output_dir_check / "images").glob("scene*_cutaway.jpg"))
        if images_exist:
            st.markdown("---")
            st.markdown("**Resume**")
            anim_model_resume = st.selectbox(
                "Model for re-animation",
                ["grok_video", "kling2_6"],
                index=["grok_video", "kling2_6"].index(st.session_state.get("animation_model", "grok_video")),
                format_func=lambda x: "grok-imagine — 14cr" if x == "grok_video" else "Kling 2.6 — 10cr",
                key="resume_model_select",
                label_visibility="collapsed",
            )
            if st.button("Re-animate from saved images", use_container_width=True):
                st.session_state["animation_model"] = anim_model_resume
                st.session_state["screen"] = "reanimate"
                st.rerun()

    st.markdown("---")
    if st.button("Reset / New Video"):
        for key in ["script_data", "scenes", "video_id", "output_dir", "generation_log", "final_scenes", "avatar_image_path"]:
            st.session_state[key] = None
        st.session_state["generation_log"] = []
        st.session_state["news_content_edit"] = ""
        st.session_state["fetch_status"] = None
        st.session_state["fetch_error_msg"] = ""
        st.session_state["use_heygen"] = False
        st.session_state["screen"] = "input"
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — INPUT
# ═══════════════════════════════════════════════════════════════════════════════
def screen_input():
    st.markdown("## New Video")

    # ── Video format selector ──────────────────────────────────────────────────
    _vt_options = ["type1", "type2", "drama"]
    _vt_current = st.session_state.get("video_type", "type1")
    _vt_index = _vt_options.index(_vt_current) if _vt_current in _vt_options else 0
    video_type = st.radio(
        "Video format",
        _vt_options,
        format_func=lambda x: {
            "type1":  "Type 1 — Standard (2 avatar + 4 cutaway, 60s)",
            "type2":  "Type 2 — Split-screen (2 avatar 30s + 12 cutaway 5s, 4:3 infographics)",
            "drama":  "Type 3 — Micro-Drama (2 characters, dialogue, split screen, 60s)",
        }[x],
        horizontal=True,
        index=_vt_index,
    )
    st.session_state["video_type"] = video_type
    if video_type == "type2":
        st.caption("Split-screen: avatar speaks top 2/3, 12 silent infographic clips (5s each, 4:3) run bottom 1/3 simultaneously.")
    elif video_type == "drama":
        st.caption("Two-character micro-drama: Character 1 (human cost) + Character 2 (systemic failure) converge at a shared truth. 60s, 9:16.")

    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        topic = st.text_area(
            "Topic / editorial angle",
            placeholder="RBI data shows services sector credit growth outpacing manufacturing for 3rd consecutive quarter",
            height=100,
        )

    with col2:
        beat = st.selectbox(
            "Beat",
            ["Finance", "Business", "Politics", "Culture", "Global Affairs"],
        )
        language = st.selectbox("Language", ["Hinglish", "English", "Hindi"])
        tone = st.selectbox("Tone", ["Calm", "Energetic", "Serious", "Casual"])

    col3, col4 = st.columns([1, 1])
    with col3:
        default_persona = BEAT_TO_PERSONA.get(beat, "BIZ-M-01")
        persona_options = ["Auto (beat-based)"] + list(PERSONA_BANK.keys())
        persona_choice = st.selectbox(
            "Persona override",
            persona_options,
            index=0,
            help=f"Auto selects {default_persona} for {beat}",
        )
        persona_id = None if persona_choice == "Auto (beat-based)" else persona_choice

        p = PERSONA_BANK.get(persona_id or default_persona)
        if p:
            st.caption(f"**{p.label}** — {p.description}")

        resolved_persona = persona_id or default_persona

        # ── Voice (ElevenLabs) ────────────────────────────────────────────────
        env_voice = config.resolve_voice_id(resolved_persona)
        voice_input = st.text_input(
            "ElevenLabs Voice ID",
            value=env_voice,
            placeholder="e.g. 21m00Tcm4TlvDq8ikWAM",
            help="Voice ID from elevenlabs.io/voice-library. Overrides .env setting.",
        )
        if voice_input.strip():
            st.session_state["voice_id"] = voice_input.strip()
            if voice_input.strip() != env_voice:
                st.caption("Voice: custom override")
            else:
                st.caption(f"Voice from .env: {voice_input.strip()[:20]}...")
        else:
            st.session_state["voice_id"] = env_voice
            if not env_voice:
                st.warning("No voice ID set. Add ELEVENLABS_VOICE_DEFAULT to .env or enter above.")

    with col4:
        prompts_only = st.checkbox(
            "Prompts only (no video generation)",
            value=False,
            help="Export a JSON prompt pack after script review. No ElevenLabs / Higgsfield calls.",
        )
        mode = "[PACK]" if prompts_only else "[FULL]"

        st.markdown("---")
        use_heygen = st.toggle(
            "Generate HeyGen avatar videos",
            value=st.session_state.get("use_heygen", False),
            help="ON: generates lipsync talking-head clips for avatar scenes (1 & 4) via HeyGen. OFF: cutaway clips only.",
        )
        st.session_state["use_heygen"] = use_heygen

        if use_heygen:
            st.caption("Avatar scenes 1 & 4 will be generated via HeyGen.")
            env_img = config.resolve_avatar_image(
                st.session_state.get("script_data", {}).get("persona") if st.session_state.get("script_data") else None
            )
            avatar_file = st.file_uploader(
                "Avatar photo (JPG/PNG)",
                type=["jpg", "jpeg", "png"],
                help="Real face photo for HeyGen lipsync. Overrides .env setting.",
            )
            if avatar_file:
                tmp_dir = config.OUTPUT_DIR / "_avatars"
                tmp_dir.mkdir(exist_ok=True)
                avatar_save_path = str(tmp_dir / avatar_file.name)
                with open(avatar_save_path, "wb") as f:
                    f.write(avatar_file.read())
                st.session_state["avatar_image_path"] = avatar_save_path
                st.caption(f"Avatar: {avatar_file.name}")
            elif env_img:
                st.session_state["avatar_image_path"] = env_img
                st.caption(f"Avatar from .env: {Path(env_img).name}")
            else:
                st.warning("No avatar image set. Add HEYGEN_AVATAR_IMG_DEFAULT to .env or upload above.")
        else:
            st.caption("Cutaway clips only (4 clips).")

    # ── News source (mandatory) ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### News source (required)")
    st.caption("Claude generates the script grounded in this article. Paste or fetch.")

    col_url, col_btn = st.columns([5, 1])
    with col_url:
        url_input = st.text_input(
            "Article URL",
            placeholder="https://economictimes.indiatimes.com/...",
            label_visibility="collapsed",
        )
    with col_btn:
        fetch_clicked = st.button("Fetch", use_container_width=True)

    if fetch_clicked:
        if not url_input.strip():
            st.warning("Enter a URL first.")
        else:
            with st.spinner("Fetching article via Jina Reader..."):
                try:
                    import re as _re
                    import requests as _requests

                    article_url = url_input.strip()
                    st.session_state["article_url"] = article_url

                    jina_url = f"https://r.jina.ai/{article_url}"
                    headers = {"Accept": "text/plain"}
                    if config.JINA_API_KEY:
                        headers["Authorization"] = f"Bearer {config.JINA_API_KEY}"
                    resp = _requests.get(jina_url, headers=headers, timeout=30)
                    resp.raise_for_status()
                    raw = resp.text.strip()

                    if raw:
                        clean = raw

                        # ── Step 1: Skip Jina's metadata header block ─────────────────────
                        # Jina always emits: Title / URL Source / Published Time / Markdown Content:
                        # Find "Markdown Content:" and take everything after it — most reliable.
                        mc_match = _re.search(r"^Markdown Content:\s*$", clean, _re.MULTILINE | _re.IGNORECASE)
                        if mc_match:
                            clean = clean[mc_match.end():]
                        else:
                            # Fallback: strip any line that looks like a key: value metadata line
                            # (short lines ending with something after a colon, before the article)
                            clean = _re.sub(
                                r"^.{0,40}:\s*.{0,120}$\n?", "", clean,
                                count=15, flags=_re.MULTILINE
                            )

                        # Strip lone section-header words (Summary, Contents, Overview)
                        clean = _re.sub(
                            r"^\s*(Summary|Contents?|Overview|Introduction)\s*$",
                            "", clean, flags=_re.MULTILINE | _re.IGNORECASE
                        )

                        # ── Step 2: Strip markdown image tags ────────────────────────────
                        clean = _re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", clean)

                        # ── Step 3: Unwrap links → keep text only ─────────────────────────
                        clean = _re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)

                        # ── Step 4: Strip bare URLs ───────────────────────────────────────
                        clean = _re.sub(r"https?://\S+", "", clean)

                        # ── Step 5: Remove markdown headers ──────────────────────────────
                        clean = _re.sub(r"^\s*#{1,6}\s+", "", clean, flags=_re.MULTILINE)

                        # ── Step 6: Remove bullet/list markers ────────────────────────────
                        clean = _re.sub(r"^\s*[*\-•]\s+", "", clean, flags=_re.MULTILINE)

                        # ── Step 7: Remove horizontal rules ──────────────────────────────
                        clean = _re.sub(r"^\s*[-=_]{3,}\s*$", "", clean, flags=_re.MULTILINE)

                        # ── Step 8: Strip known boilerplate lines (full-line match) ───────
                        noise_patterns = [
                            # Paywall / nav
                            r"subscribe\s*(now|today|to|for)?",
                            r"sign\s*up\s*(for|to)?",
                            r"log\s*in\s*(to|for)?",
                            r"already\s+a\s+subscriber",
                            r"read\s+more\s*:?",
                            r"also\s+read\s*:?",
                            r"advertisement",
                            r"sponsored\s+content",
                            r"share\s+this\s+article",
                            r"follow\s+us\s+on",
                            r"get\s+the\s+latest",
                            r"related\s+stories?",
                            r"copyright\s+\d{4}",
                            r"all\s+rights\s+reserved",
                            # Reuters-specific
                            r"reporting\s+by\b",
                            r"editing\s+by\b",
                            r"our\s+standards\s*:",
                            r"thomson\s+reuters",
                            r"trust\s+principles",
                            r"purchase\s+licens",
                            r"opens?\s+new\s+tab",
                            # Image captions (lines starting with "Chart showing", "Graph", "Table")
                            r"^(chart|graph|table|figure|image|photo)\s+(showing|of|depicting)",
                        ]
                        for pat in noise_patterns:
                            clean = _re.sub(
                                rf"^.*{pat}.*$", "", clean,
                                flags=_re.MULTILINE | _re.IGNORECASE
                            )

                        # ── Step 9: Final whitespace cleanup ─────────────────────────────
                        clean = _re.sub(r"[ \t]+", " ", clean)
                        clean = _re.sub(r"\n{3,}", "\n\n", clean)
                        clean = clean.strip()

                        # Pass to Groq for structured fact-pack summary
                        st.session_state["fetch_status"] = "summarizing"
                        st.session_state["fetch_error_msg"] = ""
                        st.session_state["news_content_edit"] = clean[:4000]  # temp store
                        st.session_state["_raw_article"] = clean[:6000]       # full for summarizer
                    else:
                        st.session_state["news_content_edit"] = ""
                        st.session_state["fetch_status"] = "empty"
                except Exception as e:
                    st.session_state["news_content_edit"] = ""
                    st.session_state["fetch_status"] = "error"
                    st.session_state["fetch_error_msg"] = str(e)

        # Run summarization outside the Jina spinner (separate step)
        if st.session_state.get("fetch_status") == "summarizing":
            raw_article = st.session_state.get("_raw_article", "")
            if raw_article:
                with st.spinner("Summarizing article with Groq — extracting key facts..."):
                    try:
                        _provider = st.session_state.get("llm_provider", "groq")
                        summary = summarize_article(raw_article, provider=_provider)
                        st.session_state["news_content_edit"] = summary
                        st.session_state["fetch_status"] = "ok"
                    except Exception as e:
                        # Summarization failed — fall back to raw cleaned text, still usable
                        st.session_state["fetch_status"] = "ok"
                        st.session_state["fetch_error_msg"] = f"Summarization failed ({e}), using raw text."
            else:
                st.session_state["fetch_status"] = "empty"
            st.rerun()

    fetch_status = st.session_state.get("fetch_status")
    if fetch_status == "ok":
        char_count = len(st.session_state.get("news_content_edit", ""))
        fallback_warn = st.session_state.get("fetch_error_msg", "")
        if fallback_warn:
            st.warning(f"Summarization skipped: {fallback_warn}")
        st.success(f"Fetched + summarized — {char_count} chars ready as source material.")
    elif fetch_status == "empty":
        st.error("Could not extract article text from this URL. Paste manually below.")
    elif fetch_status == "error":
        err = st.session_state.get("fetch_error_msg", "")
        st.error(f"Fetch failed: {err}. Paste the article text manually below.")

    news_text = st.text_area(
        "Article text",
        key="news_content_edit",
        height=200,
        placeholder="Paste article text here, or use Fetch above...",
    )

    st.markdown("---")

    # Provider-aware API key check
    _active_provider = st.session_state.get("llm_provider", "groq")
    if _active_provider == "claude" and not config.ANTHROPIC_API_KEY:
        st.error("Claude selected but ANTHROPIC_API_KEY not set — add it to .env or switch to Groq.")
    elif _active_provider == "groq" and not config.GROQ_API_KEY:
        st.error("Groq selected but GROQ_API_KEY not set — add it to .env.")

    _api_key_ok = (
        (config.GROQ_API_KEY if _active_provider == "groq" else config.ANTHROPIC_API_KEY)
    )
    can_generate = bool(topic.strip()) and bool(news_text.strip()) and bool(_api_key_ok)
    if bool(topic.strip()) and bool(news_text.strip()) and not _api_key_ok:
        pass  # error already shown above
    elif not can_generate and topic.strip():
        st.warning("Add a news source before generating — paste text or fetch from URL.")

    if st.button("Generate Script", type="primary", disabled=not can_generate):
        _vt = st.session_state.get("video_type", "type1")
        _scene_label = {"type1": "6-scene", "type2": "14-scene", "drama": "micro-drama"}.get(_vt, "6-scene")
        with st.spinner(f"Generating {_scene_label} script..."):
            try:
                script_data = generate_script(
                    topic=topic.strip(),
                    beat=beat,
                    language=language,
                    tone=tone,
                    persona_id=persona_id,
                    news_content=news_text.strip(),
                    provider=st.session_state.get("llm_provider", "groq"),
                    video_type=st.session_state.get("video_type", "type1"),
                )
                # Drama has no flat scenes array — skip scenes_from_script
                if script_data.get("video_type") == "drama":
                    scenes = []
                else:
                    scenes = scenes_from_script(script_data)

                script_data["beat"] = beat  # store beat for animation fallback

                # Save source + script to output folder immediately
                video_dir = config.OUTPUT_DIR / script_data["video_id"]
                video_dir.mkdir(parents=True, exist_ok=True)

                article_url = st.session_state.get("article_url", "")
                source_header = f"Source URL: {article_url}\n\n" if article_url else ""
                (video_dir / "source.txt").write_text(
                    source_header + news_text.strip(), encoding="utf-8"
                )
                (video_dir / "script.json").write_text(
                    json.dumps(script_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                st.session_state["script_data"] = script_data
                st.session_state["scenes"] = scenes
                st.session_state["video_id"] = script_data["video_id"]
                st.session_state["output_dir"] = str(video_dir)
                st.session_state["mode"] = mode
                st.session_state["screen"] = "review"
                st.rerun()

            except Exception as e:
                st.error(f"Script generation failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — SCRIPT REVIEW
# ═══════════════════════════════════════════════════════════════════════════════
def screen_review():
    script = st.session_state["script_data"]
    video_type = st.session_state.get("video_type", "type1")

    # Drama has its own dedicated review screen
    if video_type == "drama" or script.get("video_type") == "drama":
        screen_review_drama()
        return

    scenes: list[Scene] = st.session_state["scenes"]
    is_type2 = (video_type == "type2")

    st.markdown(f"## Script Review — `{script['video_id']}`")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Persona:** {script['persona']}")
        p = PERSONA_BANK.get(script["persona"])
        if p:
            st.caption(p.description)
    with col2:
        tmpl = STORY_TEMPLATES.get(script["template"])
        st.markdown(f"**Template:** {script['template']}")
        if tmpl:
            st.caption(tmpl.name)
    with col3:
        st.markdown(f"**Angle:** {script['angle']}")
        if is_type2:
            st.caption("Type 2 — 2 avatar (30s) + 12 cutaway (5s, 4:3, silent)")

    st.markdown("---")
    if is_type2:
        st.markdown("### Scenes — 2 avatar narrations + 12 infographic prompts")
        st.caption("Avatar scenes: edit narration (target 450 chars). Cutaway scenes: edit image + animation prompts only.")
    else:
        st.markdown("### Scenes — edit narration or prompts before generating")

    updated_scenes = []
    for scene in scenes:
        tag_class = "avatar" if scene.type == "AVATAR" else "cutaway"
        tag_label = "AVATAR" if scene.type == "AVATAR" else "CUTAWAY"

        with st.expander(
            f"Scene {scene.scene_number} — {tag_label}  |  ~{scene.duration_seconds}s",
            expanded=True,
        ):
            st.markdown(
                f'<span class="tag tag-{tag_class}">{tag_label}</span>',
                unsafe_allow_html=True,
            )

            if is_type2:
                if scene.type == "AVATAR":
                    # Type 2 AVATAR — narration only. No image, no animation (HeyGen handles it).
                    char_count = len(scene.narration)
                    new_narration = st.text_area(
                        f"Narration ({char_count} chars — target 450)",
                        value=scene.narration,
                        key=f"narr_{scene.scene_number}",
                        height=120,
                    )
                    if char_count < 400:
                        st.warning(f"{char_count} chars — under target. May run short on 30s clip.")
                    elif char_count > 500:
                        st.warning(f"{char_count} chars — over 500. Audio may get cut.")
                    scene.narration = new_narration
                else:
                    # Type 2 CUTAWAY — scene description + image + animation. No narration (silent).
                    new_scene_desc = st.text_area(
                        "Scene description (visual concept)",
                        value=scene.scene_description or "",
                        key=f"desc_{scene.scene_number}",
                        height=70,
                    )
                    new_image_prompt = st.text_area(
                        "Image prompt",
                        value=scene.image_prompt or "",
                        key=f"img_{scene.scene_number}",
                        height=100,
                    )
                    new_anim_prompt = st.text_area(
                        "Animation prompt",
                        value=scene.animation_prompt or "",
                        key=f"anim_{scene.scene_number}",
                        height=70,
                    )
                    scene.scene_description = new_scene_desc or scene.scene_description
                    scene.image_prompt = new_image_prompt
                    scene.animation_prompt = new_anim_prompt or scene.animation_prompt
            else:
                # Type 1 — full field set for all scenes
                new_narration = st.text_area(
                    "Narration",
                    value=scene.narration,
                    key=f"narr_{scene.scene_number}",
                    height=80,
                )
                new_scene_desc = st.text_area(
                    "Scene description (visual concept — used as image prompt)",
                    value=scene.scene_description or "",
                    key=f"desc_{scene.scene_number}",
                    height=70,
                )
                new_image_prompt = st.text_area(
                    "Image prompt (Nano Banana format — derived from scene description)",
                    value=scene.image_prompt,
                    key=f"img_{scene.scene_number}",
                    height=100,
                )

                if scene.type == "CUTAWAY":
                    new_anim_prompt = st.text_area(
                        "Animation prompt",
                        value=scene.animation_prompt or "",
                        key=f"anim_{scene.scene_number}",
                        height=70,
                    )
                    new_overlay = st.text_input(
                        "Overlay text",
                        value=scene.overlay_text or "",
                        key=f"overlay_{scene.scene_number}",
                    )
                    scene.animation_prompt = new_anim_prompt or scene.animation_prompt
                    scene.overlay_text = new_overlay or scene.overlay_text

                scene.narration = new_narration
                scene.scene_description = new_scene_desc or scene.scene_description
                scene.image_prompt = new_image_prompt

            updated_scenes.append(scene)

    st.session_state["scenes"] = updated_scenes

    st.markdown("---")
    col_back, col_fwd = st.columns([1, 3])
    with col_back:
        if st.button("Back to input"):
            st.session_state["screen"] = "input"
            st.rerun()
    with col_fwd:
        mode = st.session_state.get("mode", "[FULL]")
        if mode == "[PACK]":
            if st.button("Export prompt pack JSON", type="primary"):
                _export_prompt_pack(script, updated_scenes)
        else:
            if st.button("Generate video", type="primary"):
                st.session_state["screen"] = "progress"
                st.rerun()


def _export_prompt_pack(script: dict, scenes: list[Scene]):
    """Downloads a JSON prompt pack — no API calls beyond Claude."""
    pack = {
        "video_id": script["video_id"],
        "persona": script["persona"],
        "template": script["template"],
        "angle": script["angle"],
        "scenes": [s.to_dict() for s in scenes],
    }
    st.download_button(
        "Download prompt pack JSON",
        data=json.dumps(pack, indent=2, ensure_ascii=False),
        file_name=f"{script['video_id']}_prompt_pack.json",
        mime="application/json",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 3b — TYPE 2 GENERATION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
def _screen_progress_type2(video_id: str, all_scenes: list[Scene]):
    """
    Type 2 split-screen pipeline:
    - Step 1: Audio for 2 AVATAR scenes only (30s each)
    - Step 2: HeyGen lipsync for 2 AVATAR scenes
    - Step 3: Generate 12 CUTAWAY images (4:3)
    - Step 4: Animate 12 CUTAWAY scenes (5s, kling2_6)
    - No audio merge — cutaways are silent
    """
    st.caption("Split-screen pipeline — 2 avatar clips (30s) + 12 silent infographic clips (5s, 4:3).")

    output_dir = Path(st.session_state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    log = st.session_state.get("generation_log", [])
    _anim_model = st.session_state.get("animation_model", "kling2_6")

    def log_step(msg, ok=True):
        log.append(f"[{'OK' if ok else 'FAIL'}] {msg}")
        st.session_state["generation_log"] = log

    avatar_scenes  = [s for s in all_scenes if s.type == "AVATAR"]
    cutaway_scenes = [s for s in all_scenes if s.type == "CUTAWAY"]

    # ── Step 1: Audio for avatar scenes (30s cap) ─────────────────────────────
    with st.status(f"Step 1 — Generating {len(avatar_scenes)} avatar narrations (ElevenLabs)...", expanded=True) as s1:
        prog = st.progress(0)
        try:
            def cb(done, total): prog.progress(done / total, text=f"Audio {done}/{total}")
            avatar_scenes = generate_audio_for_scenes(
                avatar_scenes, output_dir,
                voice_id=st.session_state.get("voice_id"),
                persona_id=st.session_state.get("script_data", {}).get("persona"),
                audio_cap_seconds=config.TYPE2_AVATAR_DURATION_S,
                progress_callback=cb,
            )
            audio_by_num = {s.scene_number: s for s in avatar_scenes}
            for s in all_scenes:
                if s.scene_number in audio_by_num:
                    s.audio_path = audio_by_num[s.scene_number].audio_path
            log_step("Avatar audio complete")
            s1.update(label="Step 1 — Avatar audio done", state="complete")
        except Exception as e:
            log_step(f"Avatar audio failed: {e}", ok=False)
            s1.update(label=f"Step 1 — FAILED: {e}", state="error")
            st.error(str(e)); _show_log(log); return

    # ── Step 2: HeyGen lipsync for avatar scenes ──────────────────────────────
    with st.status("Step 2 — Generating avatar lipsync (HeyGen)...", expanded=True) as s2:
        prog = st.progress(0)
        try:
            def cb(done, total): prog.progress(done / total, text=f"Lipsync {done}/{total}")
            avatar_scenes = generate_lipsync_for_avatar_scenes(
                avatar_scenes, output_dir,
                avatar_image_path=st.session_state.get("avatar_image_path"),
                persona_id=st.session_state.get("script_data", {}).get("persona"),
                progress_callback=cb,
            )
            avatar_scenes = set_lipsync_as_final(avatar_scenes)
            log_step("Lipsync complete")
            s2.update(label="Step 2 — Lipsync done", state="complete")
        except Exception as e:
            log_step(f"Lipsync failed: {e}", ok=False)
            s2.update(label=f"Step 2 — Lipsync FAILED: {e}", state="error")
            st.warning(f"HeyGen lipsync failed: {e}")

    # ── Step 3: Generate 12 cutaway images (4:3) ──────────────────────────────
    with st.status(f"Step 3 — Generating {len(cutaway_scenes)} infographic images (4:3)...", expanded=True) as s3:
        prog = st.progress(0)
        try:
            def cb(done, total): prog.progress(done / total, text=f"Image {done}/{total}")
            cutaway_scenes = generate_all_images(
                cutaway_scenes, output_dir,
                beat=st.session_state.get("script_data", {}).get("beat", "Finance"),
                aspect_ratio=config.TYPE2_IMAGE_ASPECT,
                progress_callback=cb,
            )
            log_step(f"Images complete — {len(cutaway_scenes)} at 4:3")
            s3.update(label="Step 3 — Images done", state="complete")
        except Exception as e:
            log_step(f"Image gen failed: {e}", ok=False)
            s3.update(label=f"Step 3 — FAILED: {e}", state="error")
            st.error(str(e)); _show_log(log); return

    # ── Step 4: Animate 12 cutaway scenes (5s, kling2_6) ──────────────────────
    _anim_label = "Kling 2.6" if _anim_model == "kling2_6" else "grok-imagine"
    with st.status(f"Step 4 — Animating {len(cutaway_scenes)} infographic clips ({_anim_label}, 5s)...", expanded=True) as s4:
        prog = st.progress(0)
        try:
            def cb(done, total): prog.progress(done / total, text=f"Clip {done}/{total}")
            cutaway_scenes = animate_cutaway_scenes(
                cutaway_scenes, output_dir,
                beat=st.session_state.get("script_data", {}).get("beat", "Finance"),
                video_model=_anim_model,
                aspect_ratio=config.TYPE2_IMAGE_ASPECT,
                clip_duration=config.TYPE2_CLIP_DURATION,
                progress_callback=cb,
            )
            # Mark cutaway clips as final (no audio merge needed — silent)
            for s in cutaway_scenes:
                if s.cutaway_video_path:
                    s.final_video_path = s.cutaway_video_path
            log_step(f"Animation complete — {len(cutaway_scenes)} clips")
            s4.update(label=f"Step 4 — Animation done ({_anim_label})", state="complete")
        except Exception as e:
            log_step(f"Animation failed: {e}", ok=False)
            s4.update(label=f"Step 4 — FAILED: {e}", state="error")
            st.error(str(e)); _show_log(log); return

    final_scenes = sorted(avatar_scenes + cutaway_scenes, key=lambda s: s.scene_number)
    _save_edit_timeline(final_scenes, output_dir, st.session_state["script_data"])
    st.session_state["final_scenes"] = final_scenes
    st.session_state["screen"] = "output"
    st.success("All steps complete.")
    st.rerun()


def _generate_single_char_image(script: dict, char_id: str):
    """Generate avatar image for one character and show result inline."""
    from core.higgsfield_cli import generate_image, _extract_url
    from utils.downloader import download_file

    output_dir  = Path(st.session_state.get("output_dir", "output"))
    images_dir  = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    dest        = images_dir / f"{char_id}_avatar.jpg"
    img_prompt  = script.get("characters", {}).get(char_id, {}).get("avatar_image_prompt", "")

    if not img_prompt:
        st.error(f"{char_id}: avatar_image_prompt is empty — fill it in first.")
        return

    with st.spinner(f"Generating {char_id} avatar image..."):
        try:
            response = generate_image(img_prompt, aspect_ratio="9:16")
            cdn_url  = _extract_url(response)
            download_file(cdn_url, dest)
            st.success(f"{char_id} avatar saved")
            st.image(str(dest), width=200)
        except Exception as e:
            st.error(f"{char_id} image failed: {e}")


def _generate_single_drama_clip(script: dict, char_id: str, take: dict, t_num: int):
    """Generate a single Seedance clip for one take and show result inline."""
    import re as _re
    from core.higgsfield_cli import _extract_url
    from utils.cli_runner import run_higgsfield
    from utils.downloader import download_file

    output_dir = Path(st.session_state.get("output_dir", "output"))
    clips_dir  = output_dir / "clips"
    images_dir = output_dir / "images"
    clips_dir.mkdir(parents=True, exist_ok=True)

    label = f"{char_id}_take{t_num}"
    dest  = clips_dir / f"{label}.mp4"

    chars      = script.get("characters", {})
    char_data  = chars.get(char_id, {})
    base_prompt  = char_data.get("higgsfield_prompt", "")
    # Strip any fixed shot framing from the character-level prompt so per-take camera_angle wins
    base_prompt  = _re.sub(r"Locked [^.]+\.", "", base_prompt).strip()
    clean_script = _re.sub(r"\[.*?\]", "", take.get("script", "")).strip()
    camera_angle = take.get("camera_angle", "").strip()
    # camera_angle goes FIRST — Seedance reads shot framing from the top of the prompt
    full_prompt  = " ".join(filter(None, [camera_angle + "," if camera_angle else "", base_prompt, f"Dialogue: {clean_script}" if clean_script else ""]))
    duration     = min(int(take.get("duration_seconds", 8)), 8)

    avatar_img = str(images_dir / f"{char_id}_avatar.jpg")

    cmd = [
        "generate", "create", "seedance_2_0",
        "--prompt", full_prompt,
        "--aspect_ratio", "9:16",
        "--duration", str(duration),
        "--mode", config.HIGGSFIELD_VIDEO_MODE,
        "--generate_audio", "true",
        "--resolution", config.HIGGSFIELD_VIDEO_RESOLUTION,
    ]
    if Path(avatar_img).exists():
        cmd += ["--image", avatar_img]

    with st.spinner(f"Generating {label}..."):
        try:
            response = run_higgsfield(cmd)
            cdn_url  = _extract_url(response)
            download_file(cdn_url, dest)
            st.success(f"{label} done")
            st.video(str(dest))
        except Exception as e:
            st.error(f"{label} failed: {e}")


def _render_text_card(card: dict, dest: Path) -> None:
    """
    Renders a text card MP4 using PIL (frame composition) + ffmpeg (animation + duration).

    card_id 1  — typewriter: each line appears 0.4s apart, hold 3s, cut in/out
    card_id 2  — fade in 0.3s, hold 5s, fade out 0.3s
    card_id 3  — final brand card: fade in 0.3s, hold to end
    """
    import subprocess
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920  # 9:16
    card_id = card.get("card_id", 1)
    lines = card.get("lines", [])
    duration = card.get("duration_seconds", 6)
    animation = card.get("animation", "")

    # ── Font setup ────────────────────────────────────────────────────────────
    font_dir = Path(__file__).parent / "assets" / "fonts"

    def _load_font(size: int, bold: bool = True, italic: bool = False) -> ImageFont.FreeTypeFont:
        candidates = []
        if italic and bold:
            candidates += ["GeistMono-Bold.ttf", "Geist-Bold.ttf"]
        elif bold:
            candidates += ["Geist-Bold.ttf", "GeistMono-Bold.ttf"]
        else:
            candidates += ["Geist-Regular.ttf", "GeistMono-Regular.ttf"]
        # System fallbacks
        candidates += ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
        for name in candidates:
            for search in [font_dir, Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]:
                p = search / name
                if p.exists():
                    return ImageFont.truetype(str(p), size)
        return ImageFont.load_default()

    # ── Render a single frame with all lines visible ──────────────────────────
    def _make_frame(visible_lines: list[tuple[str, bool, bool]]) -> Image.Image:
        """visible_lines: list of (text, is_bold, is_italic)"""
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        line_spacing = 90
        total_h = len(visible_lines) * line_spacing
        y = (H - total_h) // 2

        for text, bold, italic in visible_lines:
            if card_id == 3:
                # Brand card: smaller sizes, centered bottom half
                font = _load_font(52 if text.startswith("AM:PM") else 38 if bold else 28, bold=bold, italic=italic)
            else:
                font = _load_font(64 if bold else 48, bold=bold, italic=italic)

            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y), text, font=font, fill=(255, 255, 255))
            y += line_spacing

        return img

    # ── Determine line styles ─────────────────────────────────────────────────
    styled_lines: list[tuple[str, bool, bool]] = []
    for i, line in enumerate(lines):
        is_italic = (card_id == 2 and i == len(lines) - 1)  # card 2 line 3 is italic
        is_bold = not is_italic
        styled_lines.append((line, is_bold, is_italic))

    tmp = dest.parent / f"_tmp_{dest.stem}"
    tmp.mkdir(exist_ok=True)

    try:
        if card_id == 1 or "typewriter" in animation.lower():
            # Typewriter: generate one PNG per line-reveal state, concat via ffmpeg concat demuxer
            frame_paths = []
            fps = 30
            stagger_frames = int(0.4 * fps)  # 12 frames between lines
            hold_frames = int(3 * fps)        # 90 frames hold at full

            # Blank opening frame (1 frame — cuts in immediately)
            blank = Image.new("RGB", (W, H), (0, 0, 0))
            blank_path = tmp / "blank.png"
            blank.save(blank_path)

            for n in range(1, len(styled_lines) + 1):
                frame = _make_frame(styled_lines[:n])
                p = tmp / f"state_{n:02d}.png"
                frame.save(p)
                frame_paths.append((p, stagger_frames if n < len(styled_lines) else hold_frames))

            # Write concat file
            concat_txt = tmp / "concat.txt"
            with open(concat_txt, "w") as f:
                f.write(f"file '{blank_path.as_posix()}'\nduration {1/fps:.4f}\n")
                for img_path, n_frames in frame_paths:
                    f.write(f"file '{img_path.as_posix()}'\nduration {n_frames/fps:.4f}\n")
                # ffmpeg concat needs a final file entry with no duration
                f.write(f"file '{frame_paths[-1][0].as_posix()}'\n")

            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_txt),
                "-vf", f"scale={W}:{H},format=yuv420p",
                "-r", str(fps),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-t", str(duration),
                str(dest),
            ], check=True, capture_output=True, timeout=60)

        else:
            # Fade in / fade out — render single full frame, apply ffmpeg fade filters
            frame = _make_frame(styled_lines)
            frame_path = tmp / "frame.png"
            frame.save(frame_path)

            fade_in_d = 0.3
            fade_out_d = 0.3 if "fade out" in animation.lower() else 0.0
            fade_out_start = duration - fade_out_d if fade_out_d else duration

            vf_parts = [f"fade=in:st=0:d={fade_in_d}"]
            if fade_out_d:
                vf_parts.append(f"fade=out:st={fade_out_start}:d={fade_out_d}")
            vf_parts.append(f"scale={W}:{H},format=yuv420p")

            subprocess.run([
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(frame_path),
                "-vf", ",".join(vf_parts),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-t", str(duration),
                "-r", "30",
                str(dest),
            ], check=True, capture_output=True, timeout=60)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — GENERATION PROGRESS
# ═══════════════════════════════════════════════════════════════════════════════
def _screen_progress_drama(video_id: str, script: dict):
    """
    Drama pipeline:
    Step 1 — Generate 2 character avatar images (Higgsfield nano_banana_2)
    Step 2 — Generate 5 character clips (Seedance 2.0 — video + voice in one call)
    Step 3 — Generate 3 text card MP4s (PIL + ffmpeg)
    No ElevenLabs. No HeyGen. No cutaways.
    """
    st.caption("Micro-drama pipeline — 2 avatar images + 5 character clips + 3 text cards.")

    output_dir = Path(st.session_state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    log = st.session_state.get("generation_log", [])

    def log_step(msg, ok=True):
        log.append(f"[{'OK' if ok else 'FAIL'}] {msg}")
        st.session_state["generation_log"] = log

    chars   = script.get("characters", {})
    takes   = script.get("takes", {})
    beat    = script.get("beat", "Politics")

    # Build a flat ordered list of all takes for voice + lipsync steps
    # Format: (char_id, take_dict, label)
    all_takes = []
    for t in takes.get("char1", []):
        all_takes.append(("char1", t, f"char1_take{t['take_number']}"))
    for t in takes.get("char2", []):
        all_takes.append(("char2", t, f"char2_take{t['take_number']}"))

    images_dir = output_dir / "images"
    clips_dir  = output_dir / "clips"
    images_dir.mkdir(exist_ok=True)
    clips_dir.mkdir(exist_ok=True)

    char_image_paths = {}
    take_lipsync_paths = {}

    # ── Step 1: Generate 2 character avatar images ────────────────────────────
    with st.status("Step 1 — Generating character avatar images (Higgsfield)...", expanded=True) as s1:
        prog = st.progress(0)
        failed_images = []
        for i, (char_id, char_data) in enumerate(chars.items()):
            dest = images_dir / f"{char_id}_avatar.jpg"
            if dest.exists():
                char_image_paths[char_id] = str(dest)
                log_step(f"{char_id} image already exists — skipping")
                prog.progress((i + 1) / 2)
                continue

            img_prompt = char_data.get("avatar_image_prompt", "")
            if not img_prompt:
                log_step(f"{char_id} missing avatar_image_prompt — skipping", ok=False)
                failed_images.append(char_id)
                prog.progress((i + 1) / 2)
                continue

            try:
                from core.higgsfield_cli import generate_image, _extract_url
                from utils.downloader import download_file
                response = generate_image(img_prompt, aspect_ratio="9:16")
                cdn_url = _extract_url(response)
                download_file(cdn_url, dest)
                char_image_paths[char_id] = str(dest)
                log_step(f"{char_id} avatar image saved -> {dest.name}")
            except Exception as e:
                log_step(f"{char_id} image failed: {e}", ok=False)
                failed_images.append(char_id)

            prog.progress((i + 1) / 2)

        if failed_images:
            s1.update(label=f"Step 1 — Images done (failed: {failed_images})", state="complete")
        else:
            s1.update(label="Step 1 — Both avatar images done", state="complete")

    # ── Step 2: Generate 5 character clips (Seedance 2.0 — video + voice in one) ──
    with st.status(f"Step 2 — Generating {len(all_takes)} character clips (Seedance 2.0)...", expanded=True) as s3:
        prog = st.progress(0)
        try:
            import re as _re
            from core.higgsfield_cli import _extract_url
            from utils.cli_runner import run_higgsfield
            from utils.downloader import download_file

            for i, (char_id, take, label) in enumerate(all_takes):
                dest = clips_dir / f"{label}.mp4"
                if dest.exists():
                    take_lipsync_paths[label] = str(dest)
                    log_step(f"{label} already exists — skipping")
                    prog.progress((i + 1) / len(all_takes))
                    continue

                char_data = chars.get(char_id, {})
                base_prompt  = char_data.get("higgsfield_prompt", "")
                # Strip fixed shot framing so per-take camera_angle is the dominant instruction
                base_prompt  = _re.sub(r"Locked [^.]+\.", "", base_prompt).strip()
                clean_script = _re.sub(r"\[.*?\]", "", take.get("script", "")).strip()
                camera_angle = take.get("camera_angle", "").strip()
                # camera_angle goes FIRST — Seedance reads shot framing from the top of the prompt
                full_prompt  = " ".join(filter(None, [camera_angle + "," if camera_angle else "", base_prompt, f"Dialogue: {clean_script}" if clean_script else ""]))

                duration = min(int(take.get("duration_seconds", 8)), 8)

                # Avatar image from Step 1 — gives Seedance face/appearance reference
                avatar_img = char_image_paths.get(char_id, "")

                cmd = [
                    "generate", "create", "seedance_2_0",
                    "--prompt", full_prompt,
                    "--aspect_ratio", "9:16",
                    "--duration", str(duration),
                    "--mode", config.HIGGSFIELD_VIDEO_MODE,
                    "--generate_audio", "true",
                    "--resolution", config.HIGGSFIELD_VIDEO_RESOLUTION,
                ]
                if avatar_img and Path(avatar_img).exists():
                    cmd += ["--image", avatar_img]

                try:
                    response = run_higgsfield(cmd)
                    cdn_url = _extract_url(response)
                    download_file(cdn_url, dest)
                    take_lipsync_paths[label] = str(dest)
                    log_step(f"{label} OK -> {dest.name}")
                except Exception as e:
                    log_step(f"{label} failed: {e}", ok=False)
                    st.warning(f"{label} failed: {e}")

                prog.progress((i + 1) / len(all_takes))

            s3.update(label=f"Step 2 — Character clips done ({len(take_lipsync_paths)}/{len(all_takes)})", state="complete")
        except Exception as e:
            log_step(f"Character clip generation failed: {e}", ok=False)
            s3.update(label=f"Step 2 — FAILED: {e}", state="error")
            st.error(str(e)); _show_log(log); return

    # ── Step 3: Generate text card MP4s ──────────────────────────────────────
    text_card_paths = {}
    text_cards = script.get("text_cards", [])
    cards_dir = output_dir / "cards"
    cards_dir.mkdir(exist_ok=True)

    with st.status(f"Step 3 — Generating {len(text_cards)} text card MP4s...", expanded=True) as s4:
        prog = st.progress(0)
        try:
            for i, card in enumerate(text_cards):
                card_id = card.get("card_id", i + 1)
                dest = cards_dir / f"textcard_{card_id}.mp4"

                if dest.exists():
                    text_card_paths[f"card_{card_id}"] = str(dest)
                    log_step(f"textcard_{card_id} already exists — skipping")
                    prog.progress((i + 1) / len(text_cards))
                    continue

                try:
                    _render_text_card(card, dest)
                    text_card_paths[f"card_{card_id}"] = str(dest)
                    log_step(f"textcard_{card_id} rendered -> {dest.name}")
                except Exception as e:
                    log_step(f"textcard_{card_id} failed: {e}", ok=False)
                    st.warning(f"Text card {card_id} failed: {e}")

                prog.progress((i + 1) / len(text_cards))

            s4.update(label=f"Step 3 — Text cards done ({len(text_card_paths)}/{len(text_cards)})", state="complete")
        except Exception as e:
            log_step(f"Text card generation failed: {e}", ok=False)
            s4.update(label=f"Step 3 — FAILED: {e}", state="error")
            st.error(str(e))
            # Non-fatal — continue to save output

    # ── Save drama output pack ────────────────────────────────────────────────
    drama_output = {
        **script,
        "generated": {
            "char_image_paths": char_image_paths,
            "take_clip_paths": take_lipsync_paths,
            "text_card_paths": text_card_paths,
        },
    }
    (output_dir / "drama_output.json").write_text(
        json.dumps(drama_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    st.session_state["drama_output"] = drama_output
    st.session_state["generation_log"] = log
    st.session_state["screen"] = "output"
    st.success("All steps complete.")
    st.rerun()


def screen_progress():
    video_id = st.session_state["video_id"]
    all_scenes: list[Scene] = st.session_state["scenes"]
    use_heygen = st.session_state.get("use_heygen", False)
    video_type = st.session_state.get("video_type", "type1")

    st.markdown(f"## Generating — `{video_id}`")

    if video_type == "type2":
        _screen_progress_type2(video_id, all_scenes)
        return

    if video_type == "drama":
        script = st.session_state.get("script_data", {})
        _screen_progress_drama(video_id, script)
        return

    if use_heygen:
        st.caption("Full pipeline — 4 cutaway clips + 2 HeyGen avatar clips.")
    else:
        st.caption("Cutaway only — 4 clips. Avatar scenes skipped.")

    output_dir = Path(st.session_state["output_dir"]) if st.session_state.get("output_dir") else config.OUTPUT_DIR / video_id
    output_dir.mkdir(parents=True, exist_ok=True)
    st.session_state["output_dir"] = str(output_dir)

    log = st.session_state.get("generation_log", [])

    def log_step(msg: str, ok: bool = True):
        icon = "OK" if ok else "FAIL"
        log.append(f"[{icon}] {msg}")
        st.session_state["generation_log"] = log

    cutaway_scenes = [s for s in all_scenes if s.type == "CUTAWAY"]
    avatar_scenes  = [s for s in all_scenes if s.type == "AVATAR"]

    # Determine which scenes need audio
    audio_scenes = all_scenes if use_heygen else cutaway_scenes
    audio_count  = len(audio_scenes)

    # ── Step 1: Audio ─────────────────────────────────────────────────────────
    with st.status(f"Step 1 — Generating {audio_count} narration clips (ElevenLabs)...", expanded=True) as s1:
        audio_progress = st.progress(0)
        try:
            def audio_cb(done, total):
                audio_progress.progress(done / total, text=f"Audio {done}/{total}")

            audio_scenes = generate_audio_for_scenes(
                audio_scenes, output_dir,
                voice_id=st.session_state.get("voice_id"),
                persona_id=st.session_state.get("script_data", {}).get("persona"),
                progress_callback=audio_cb,
            )
            # Sync audio paths back into both scene lists
            audio_by_num = {s.scene_number: s for s in audio_scenes}
            for s in all_scenes:
                if s.scene_number in audio_by_num:
                    s.audio_path = audio_by_num[s.scene_number].audio_path
            cutaway_scenes = [s for s in all_scenes if s.type == "CUTAWAY"]
            avatar_scenes  = [s for s in all_scenes if s.type == "AVATAR"]

            log_step(f"Audio generation complete — {audio_count} clips")
            s1.update(label="Step 1 — Audio done", state="complete")
        except Exception as e:
            log_step(f"Audio failed: {e}", ok=False)
            s1.update(label=f"Step 1 — Audio FAILED: {e}", state="error")
            st.error(f"Audio generation failed: {e}")
            _show_log(log)
            return

    # ── Step 2: Base images (Higgsfield nano_banana_2) ────────────────────────
    with st.status("Step 2 — Generating 4 base images (Higgsfield)...", expanded=True) as s2:
        img_progress = st.progress(0)
        try:
            def img_cb(done, total):
                img_progress.progress(done / total, text=f"Image {done}/{total}")

            cutaway_scenes = generate_all_images(
                cutaway_scenes, output_dir,
                beat=st.session_state.get("script_data", {}).get("beat", "Finance"),
                progress_callback=img_cb,
            )
            log_step("Image generation complete — 4 images")
            s2.update(label="Step 2 — Images done", state="complete")
        except Exception as e:
            log_step(f"Image gen failed: {e}", ok=False)
            s2.update(label=f"Step 2 — Images FAILED: {e}", state="error")
            st.error(f"Image generation failed: {e}")
            _show_log(log)
            return

    # ── Step 3: Animate cutaways ──────────────────────────────────────────────
    _anim_model = st.session_state.get("animation_model", "grok_video")
    _anim_label = "Kling 2.6" if _anim_model == "kling2_6" else "grok-imagine"
    with st.status(f"Step 3 — Animating cutaway scenes ({_anim_label})...", expanded=True) as s3:
        cutaway_progress = st.progress(0)
        try:
            def cutaway_cb(done, total):
                cutaway_progress.progress(done / total, text=f"Cutaway {done}/{total}")

            cutaway_scenes = animate_cutaway_scenes(
                cutaway_scenes, output_dir,
                beat=st.session_state.get("script_data", {}).get("beat", "Finance"),
                video_model=_anim_model,
                progress_callback=cutaway_cb,
            )
            log_step(f"Cutaway animation complete — 4 clips ({_anim_label})")
            s3.update(label=f"Step 3 — Animations done ({_anim_label})", state="complete")
        except Exception as e:
            log_step(f"Cutaway animation failed: {e}", ok=False)
            s3.update(label=f"Step 3 — Animation FAILED: {e}", state="error")
            st.error(f"Cutaway animation failed: {e}")
            _show_log(log)
            return

    # ── Step 4: Merge audio onto cutaway clips (ffmpeg) ───────────────────────
    with st.status("Step 4 — Merging audio onto cutaway videos (ffmpeg)...", expanded=False) as s4:
        try:
            cutaway_scenes = merge_cutaway_audio(cutaway_scenes, output_dir)
            log_step("Audio merge complete — 4 cutaway clips ready.")
            s4.update(label="Step 4 — Audio merged", state="complete")
        except Exception as e:
            log_step(f"Audio merge failed: {e}", ok=False)
            s4.update(label=f"Step 4 — Merge FAILED: {e}", state="error")
            st.error(f"Audio merge failed: {e}")
            _show_log(log)
            return

    # ── Step 5 (optional): HeyGen lipsync for avatar scenes ───────────────────
    if use_heygen:
        with st.status("Step 5 — Generating avatar lipsync (HeyGen)...", expanded=True) as s5:
            lipsync_progress = st.progress(0)
            try:
                def lip_cb(done, total):
                    lipsync_progress.progress(done / total, text=f"Lipsync {done}/{total}")

                avatar_scenes = generate_lipsync_for_avatar_scenes(
                    avatar_scenes, output_dir,
                    avatar_image_path=st.session_state.get("avatar_image_path"),
                    persona_id=st.session_state.get("script_data", {}).get("persona"),
                    progress_callback=lip_cb,
                )
                avatar_scenes = set_lipsync_as_final(avatar_scenes)
                log_step("Lipsync complete — 2 avatar clips ready.")
                s5.update(label="Step 5 — Lipsync done", state="complete")
            except Exception as e:
                log_step(f"Lipsync failed: {e}", ok=False)
                s5.update(label=f"Step 5 — Lipsync FAILED: {e}", state="error")
                st.warning(f"HeyGen lipsync failed: {e}. Avatar scenes will have no video.")

    # Merge all scenes for output display
    final_scenes = sorted(avatar_scenes + cutaway_scenes, key=lambda s: s.scene_number)

    _save_edit_timeline(final_scenes, output_dir, st.session_state["script_data"])

    st.session_state["final_scenes"] = final_scenes
    st.session_state["screen"] = "output"
    st.success("All steps complete. Loading output...")
    st.rerun()


def _show_log(log: list[str]):
    with st.expander("Generation log"):
        st.code("\n".join(log))


def _save_edit_timeline(scenes: list[Scene], output_dir: Path, script: dict):
    is_type2 = script.get("video_type") == "type2"

    timeline = {
        "video_id": script["video_id"],
        "persona": script["persona"],
        "template": script["template"],
        "angle": script["angle"],
        "video_type": script.get("video_type", "type1"),
        "total_scenes": len(scenes),
        "scenes": [],
    }

    cursor = 0
    for scene in scenes:
        duration = scene.duration_seconds

        if is_type2 and scene.type == "CUTAWAY":
            visual_label = "Silent infographic (4:3) — bottom third"
            narration_display = ""
        elif scene.type == "AVATAR":
            visual_label = "Avatar lipsync (top 2/3)" if is_type2 else "Avatar lipsync"
            narration_display = scene.narration
        else:
            visual_label = "Animated cutaway"
            narration_display = scene.narration

        entry = {
            "scene": scene.scene_number,
            "type": scene.type,
            "time_start": f"0:{cursor:02d}",
            "time_end": f"0:{cursor + duration:02d}",
            "duration_s": duration,
            "narration": narration_display,
            "visual": visual_label,
            "scene_description": scene.scene_description if is_type2 and scene.type == "CUTAWAY" else None,
            "overlay_text": scene.overlay_text,
            "overlay_timing": f"0:{cursor + 1:02d} – 0:{cursor + duration - 1:02d}" if scene.overlay_text else None,
            "overlay_position": "center lower third" if scene.overlay_text else None,
            "overlay_style": "bold white, subtle shadow, fade in/out" if scene.overlay_text else None,
            "asset": scene.final_video_path or scene.lipsync_video_path or scene.cutaway_video_path,
        }
        timeline["scenes"].append(entry)
        cursor += duration

    (output_dir / "edit_timeline.json").write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 4 — OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════
def screen_output():
    scenes: list[Scene] = st.session_state.get("final_scenes") or st.session_state.get("scenes", [])
    video_id = st.session_state["video_id"]
    script = st.session_state["script_data"]
    output_dir = Path(st.session_state["output_dir"])
    video_type = st.session_state.get("video_type", "type1")

    st.markdown(f"## Output — `{video_id}`")

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        if video_type == "drama":
            st.markdown(f"**Story:** {script.get('story_topic', '')}")
        else:
            st.markdown(f"**Persona:** {script['persona']}")
            st.markdown(f"**Template:** {script['template']}")
    with col_meta2:
        st.markdown(f"**Angle:** {script.get('angle', '')}")

    st.markdown("---")
    st.markdown("### Final Clips")

    _is_type2_output = st.session_state.get("video_type") == "type2"

    for scene in scenes:
        tag_class = "avatar" if scene.type == "AVATAR" else "cutaway"
        tag_label = scene.type

        # For Type 2 silent cutaways, show scene_description as the label text
        display_text = scene.narration
        if _is_type2_output and scene.type == "CUTAWAY":
            display_text = scene.scene_description or scene.image_prompt or "(silent cutaway)"

        col_info, col_video = st.columns([1, 1])
        with col_info:
            st.markdown(
                f'<div class="scene-card {tag_class}">'
                f'<span class="tag tag-{tag_class}">{tag_label}</span><br>'
                f'<strong>Scene {scene.scene_number}</strong><br>'
                f'<em>{display_text}</em>',
                unsafe_allow_html=True,
            )
            if scene.overlay_text:
                st.markdown(f"**Overlay:** {scene.overlay_text}")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_video:
            clip_path = scene.final_video_path or scene.lipsync_video_path or scene.cutaway_video_path
            if clip_path and Path(clip_path).exists():
                st.video(clip_path)
            else:
                st.caption("No video generated for this scene.")

    # ── Edit timeline ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Edit Timeline JSON")
    timeline_path = output_dir / "edit_timeline.json"
    if timeline_path.exists():
        timeline_data = timeline_path.read_text(encoding="utf-8")
        with st.expander("View timeline JSON", expanded=False):
            st.json(json.loads(timeline_data))

        st.download_button(
            "Download edit_timeline.json",
            data=timeline_data,
            file_name=f"{video_id}_edit_timeline.json",
            mime="application/json",
        )

    # ── Edit notes ────────────────────────────────────────────────────────────
    st.markdown("---")
    if _is_type2_output:
        st.markdown("### Editor Notes — Type 2 Split-screen")
        st.caption("Stack avatar clips (top 2/3, 9:16) with infographic clips (bottom 1/3, 4:3) simultaneously. Cutaways are silent. Avatar audio drives the timeline.")
        avatar_scenes_out = [s for s in scenes if s.type == "AVATAR"]
        cutaway_scenes_out = [s for s in scenes if s.type == "CUTAWAY"]
        st.markdown(f"**Avatar clips:** {len(avatar_scenes_out)} × 30s")
        st.markdown(f"**Infographic clips:** {len(cutaway_scenes_out)} × 5s — distribute {len(cutaway_scenes_out)//2} per avatar clip")
    else:
        st.markdown("### Manual Overlays for Editor")
        for scene in scenes:
            if scene.overlay_text:
                st.markdown(
                    f"**Scene {scene.scene_number}:** `{scene.overlay_text}` — "
                    f"center lower third, bold white, fade in/out"
                )

    # ── ZIP download ───────────────────────────────────────────────────────────
    st.markdown("---")
    zip_buf = _build_zip(scenes, output_dir, video_id)
    st.download_button(
        "Download all clips + timeline (ZIP)",
        data=zip_buf,
        file_name=f"{video_id}_output.zip",
        mime="application/zip",
    )

    if st.button("New video"):
        for key in ["script_data", "scenes", "video_id", "output_dir", "generation_log", "final_scenes", "avatar_image_path"]:
            st.session_state[key] = None
        st.session_state["generation_log"] = []
        st.session_state["news_content_edit"] = ""
        st.session_state["fetch_status"] = None
        st.session_state["fetch_error_msg"] = ""
        st.session_state["use_heygen"] = False
        st.session_state["screen"] = "input"
        st.rerun()


def _build_zip(scenes: list[Scene], output_dir: Path, video_id: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for scene in scenes:
            for attr in ("final_video_path", "lipsync_video_path", "cutaway_video_path", "audio_path"):
                p = getattr(scene, attr, None)
                if p and Path(p).exists():
                    zf.write(p, arcname=Path(p).name)
                    break  # only include the best available clip per scene

        timeline_path = output_dir / "edit_timeline.json"
        if timeline_path.exists():
            zf.write(str(timeline_path), arcname="edit_timeline.json")

    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 5 — RE-ANIMATE FROM SAVED IMAGES
# ═══════════════════════════════════════════════════════════════════════════════
def screen_reanimate():
    """
    Skips audio + image generation. Restores paths from disk and re-runs
    animation (Step 3) + audio merge (Step 4) only.
    Use when images are generated but animation crashed.
    """
    video_id = st.session_state["video_id"]
    all_scenes: list[Scene] = st.session_state["scenes"]
    output_dir = Path(st.session_state["output_dir"])
    _anim_model = st.session_state.get("animation_model", "grok_video")
    _anim_label = "Kling 2.6" if _anim_model == "kling2_6" else "grok-imagine"

    st.markdown(f"## Re-animating — `{video_id}`")
    st.caption(f"Restoring saved images and re-running animation via {_anim_label}. Skipping audio + image generation.")

    cutaway_scenes = [s for s in all_scenes if s.type == "CUTAWAY"]
    avatar_scenes  = [s for s in all_scenes if s.type == "AVATAR"]

    images_dir = output_dir / "images"
    audio_dir  = output_dir / "audio"

    # ── Restore image + audio paths from disk ─────────────────────────────────
    missing_images = []
    for scene in cutaway_scenes:
        img = images_dir / f"scene{scene.scene_number}_cutaway.jpg"
        if img.exists():
            scene.image_path = str(img)
        else:
            missing_images.append(scene.scene_number)

        for ext in ("mp3", "wav"):
            aud = audio_dir / f"seg{scene.scene_number}.{ext}"
            if aud.exists():
                scene.audio_path = str(aud)
                break

    if missing_images:
        st.warning(f"Missing images for scenes: {missing_images}. Those scenes will be skipped.")
    else:
        st.success(f"Found all {len(cutaway_scenes)} images. Starting animation...")

    log = []
    def log_step(msg: str, ok: bool = True):
        log.append(f"[{'OK' if ok else 'FAIL'}] {msg}")

    # ── Step 3: Animate ───────────────────────────────────────────────────────
    with st.status(f"Animating cutaway scenes ({_anim_label})...", expanded=True) as s3:
        cutaway_progress = st.progress(0)
        try:
            def cutaway_cb(done, total):
                cutaway_progress.progress(done / total, text=f"Cutaway {done}/{total}")

            cutaway_scenes = animate_cutaway_scenes(
                cutaway_scenes, output_dir,
                beat=st.session_state.get("script_data", {}).get("beat", "Finance"),
                video_model=_anim_model,
                progress_callback=cutaway_cb,
            )
            log_step(f"Animation complete — {_anim_label}")
            s3.update(label=f"Animations done ({_anim_label})", state="complete")
        except Exception as e:
            log_step(f"Animation failed: {e}", ok=False)
            s3.update(label=f"Animation FAILED: {e}", state="error")
            st.error(f"Animation failed: {e}")
            _show_log(log)
            return

    # ── Step 4: Merge audio ───────────────────────────────────────────────────
    with st.status("Merging audio onto cutaway clips...", expanded=False) as s4:
        try:
            cutaway_scenes = merge_cutaway_audio(cutaway_scenes, output_dir)
            log_step("Audio merge complete")
            s4.update(label="Audio merged", state="complete")
        except Exception as e:
            log_step(f"Audio merge failed: {e}", ok=False)
            s4.update(label=f"Merge FAILED: {e}", state="error")
            st.error(f"Audio merge failed: {e}")
            _show_log(log)
            return

    final_scenes = sorted(avatar_scenes + cutaway_scenes, key=lambda s: s.scene_number)
    _save_edit_timeline(final_scenes, output_dir, st.session_state["script_data"])

    st.session_state["final_scenes"] = final_scenes
    st.session_state["generation_log"] = log
    st.session_state["screen"] = "output"
    st.success("Re-animation complete. Loading output...")
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN 2b — DRAMA SCRIPT REVIEW
# ═══════════════════════════════════════════════════════════════════════════════
def screen_review_drama():
    script = st.session_state["script_data"]

    st.markdown(f"## Micro-Drama Script Review — `{script['video_id']}`")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Story:** {script.get('story_topic', '')}")
        st.markdown(f"**Angle:** {script.get('angle', '')}")
    with col2:
        st.markdown(f"**Beat:** {script.get('beat', '')}")
        st.markdown(f"**Template:** {script.get('template', '')}")
        st.caption("9:16 vertical — 60s — two-character dialogue")

    st.markdown("---")

    # ── CHARACTERS ────────────────────────────────────────────────────────────
    st.markdown("### Characters")
    chars = script.get("characters", {})
    col_c1, col_c2 = st.columns(2)

    for col, char_id, label in [(col_c1, "char1", "Character 1 — Human Cost"), (col_c2, "char2", "Character 2 — Systemic Layer")]:
        with col:
            char = chars.get(char_id, {})
            st.markdown(
                f'<div class="scene-card avatar">'
                f'<span class="tag tag-avatar">{label}</span><br>'
                f'<strong>Role:</strong> {char.get("role", "")}<br>'
                f'<strong>Appearance:</strong> {char.get("appearance", "")}<br>'
                f'<strong>Setting:</strong> {char.get("setting", "")}<br>'
                f'<strong>Lighting:</strong> {char.get("lighting", "")}<br>'
                f'<strong>Register:</strong> {char.get("emotional_register", "")}'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.expander(f"{char_id} — Avatar image prompt"):
                new_img = st.text_area(
                    "Avatar image prompt",
                    value=char.get("avatar_image_prompt", ""),
                    key=f"{char_id}_img",
                    height=120,
                    label_visibility="collapsed",
                )
                script["characters"][char_id]["avatar_image_prompt"] = new_img
                # Show existing image if already generated
                existing = Path(st.session_state.get("output_dir", "output")) / "images" / f"{char_id}_avatar.jpg"
                if existing.exists():
                    st.image(str(existing), width=180, caption=f"{char_id} — current")
                if st.button("Generate image", key=f"gen_img_{char_id}"):
                    _generate_single_char_image(script, char_id)

            with st.expander(f"{char_id} — Voice prompt"):
                new_voice = st.text_area(
                    "Voice prompt",
                    value=char.get("voice_prompt", ""),
                    key=f"{char_id}_voice",
                    height=80,
                    label_visibility="collapsed",
                )
                script["characters"][char_id]["voice_prompt"] = new_voice

            with st.expander(f"{char_id} — Higgsfield lipsync prompt"):
                new_hf = st.text_area(
                    "Higgsfield prompt",
                    value=char.get("higgsfield_prompt", ""),
                    key=f"{char_id}_hf",
                    height=120,
                    label_visibility="collapsed",
                )
                script["characters"][char_id]["higgsfield_prompt"] = new_hf

    st.markdown("---")

    # ── TAKES ─────────────────────────────────────────────────────────────────
    st.markdown("### Dialogue Takes")
    takes = script.get("takes", {})

    st.markdown("#### Character 1 — 3 Takes")
    for i, take in enumerate(takes.get("char1", [])):
        t_num = int(take.get("take_number", i + 1))
        t_start = take.get("timecode_start", "")
        t_end = take.get("timecode_end", "")
        t_dur = take.get("duration_seconds", "")
        t_purpose = take.get("purpose", "")
        with st.expander(f"Take {t_num}  |  {t_start}–{t_end}  ({t_dur}s)  —  {t_purpose}", expanded=True):
            new_script = st.text_area(
                "Script",
                value=take.get("script", ""),
                key=f"char1_take{t_num}",
                height=100,
            )
            script["takes"]["char1"][i]["script"] = new_script
            if st.button(f"Generate this clip", key=f"gen_char1_take{t_num}"):
                _generate_single_drama_clip(script, "char1", take, t_num)

    st.markdown("#### Character 2 — 3 Takes")
    for i, take in enumerate(takes.get("char2", [])):
        t_num = int(take.get("take_number", i + 1))
        t_start = take.get("timecode_start", "")
        t_end = take.get("timecode_end", "")
        t_dur = take.get("duration_seconds", "")
        t_purpose = take.get("purpose", "")
        with st.expander(f"Take {t_num}  |  {t_start}–{t_end}  ({t_dur}s)  —  {t_purpose}", expanded=True):
            new_script = st.text_area(
                "Script",
                value=take.get("script", ""),
                key=f"char2_take{t_num}",
                height=100,
            )
            script["takes"]["char2"][i]["script"] = new_script
            if st.button(f"Generate this clip", key=f"gen_char2_take{t_num}"):
                _generate_single_drama_clip(script, "char2", take, t_num)

    st.markdown("---")

    # ── SPLIT SCREEN ──────────────────────────────────────────────────────────
    st.markdown("### Split Screen Brief (0:42–0:52)")
    split = script.get("split_screen", {})
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(f"**Layout:** {split.get('layout', '')}")
        st.markdown(f"**Stagger:** {split.get('stagger_seconds', '')}s")
        st.markdown(f"**Audio:** {split.get('audio_mix', '')}")
        st.markdown(f"**Exit:** {split.get('exit', '')}")
    with col_s2:
        new_conv = st.text_input(
            "Convergence line (both characters say this simultaneously)",
            value=split.get("convergence_line", ""),
            key="convergence_line",
        )
        script["split_screen"]["convergence_line"] = new_conv

    st.markdown("---")

    # ── TEXT CARDS ────────────────────────────────────────────────────────────
    st.markdown("### Text Cards")
    text_cards = script.get("text_cards", [])
    for ci, card in enumerate(text_cards):
        card_id = int(card.get("card_id", ci + 1))
        t_start = card.get("timecode_start", "")
        t_end = card.get("timecode_end", "")
        is_final = (card_id == 3)
        label = f"Card {card_id}  |  {t_start}–{t_end}" + (" — FINAL CARD (logo + CTA)" if is_final else "")
        with st.expander(label, expanded=(not is_final)):
            st.caption(f"Animation: {card.get('animation', '')} | Style: {card.get('style', '')}")
            lines = card.get("lines", [])
            new_lines = []
            for i, line in enumerate(lines):
                new_line = st.text_input(
                    f"Line {i + 1}",
                    value=line,
                    key=f"card{card_id}_line{i}",
                    disabled=is_final,
                )
                new_lines.append(new_line if not is_final else line)
            script["text_cards"][ci]["lines"] = new_lines

    st.markdown("---")

    # ── STORYBOARD ────────────────────────────────────────────────────────────
    st.markdown("### Storyboard")
    storyboard = script.get("storyboard", [])
    if storyboard:
        import pandas as pd
        sb_df = pd.DataFrame(storyboard)
        st.dataframe(sb_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── TOOL EXECUTION ORDER ──────────────────────────────────────────────────
    st.markdown("### Production Order")
    exec_order = script.get("tool_execution_order", [])
    for step in exec_order:
        st.markdown(f"- {step}")

    st.markdown("---")

    # ── NEGATIVE PROMPT ───────────────────────────────────────────────────────
    with st.expander("Negative prompt (apply to all lipsync generations)"):
        st.code(script.get("negative_prompt", ""), language=None)

    st.markdown("---")
    col_back, col_fwd = st.columns([1, 3])
    with col_back:
        if st.button("Back to input"):
            st.session_state["screen"] = "input"
            st.rerun()
    with col_fwd:
        mode = st.session_state.get("mode", "[FULL]")
        if mode == "[PACK]":
            drama_json = json.dumps(script, indent=2, ensure_ascii=False)
            st.download_button(
                "Download drama production pack JSON",
                data=drama_json,
                file_name=f"{script['video_id']}_drama_pack.json",
                mime="application/json",
                type="primary",
            )
        else:
            if st.button("Generate video", type="primary"):
                st.session_state["screen"] = "progress"
                st.rerun()

    # Save any edits back to script_data
    st.session_state["script_data"] = script


# ═══════════════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════════════
screen = st.session_state["screen"]

if screen == "input":
    screen_input()
elif screen == "review":
    screen_review()
elif screen == "progress":
    screen_progress()
elif screen == "reanimate":
    screen_reanimate()
elif screen == "output":
    screen_output()
