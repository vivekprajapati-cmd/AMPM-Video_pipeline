"""
Claude API — scene-by-scene script generation.

Returns a structured dict matching the pipeline's 6-scene schema.
"""
import json
import logging
import re
from datetime import datetime
from typing import Optional

import anthropic

import config
import prompts

logger = logging.getLogger(__name__)

from models.persona import PERSONA_BANK, BEAT_TO_PERSONA
from models.scene import Scene
from models.templates import BEAT_TO_TEMPLATE


def _build_user_message(
    topic: str,
    beat: str,
    language: str,
    tone: str,
    persona_id: Optional[str],
    news_content: Optional[str] = None,
) -> str:
    resolved_persona = persona_id or BEAT_TO_PERSONA.get(beat, "BIZ-M-01")
    persona = PERSONA_BANK.get(resolved_persona)
    persona_desc = (
        f"{persona.description} ({persona.language}, {persona.setting})"
        if persona
        else resolved_persona
    )
    voice_prompt = persona.voice_prompt if persona else ""

    template_id = BEAT_TO_TEMPLATE.get(beat, "TEMPLATE_A")
    date_str = datetime.now().strftime("%Y%m%d-%H%M")

    # Mandatory source block — injected when news_content is provided
    source_block = ""
    if news_content and news_content.strip():
        source_block = f"""
Source material (factual backbone — pull data, quotes, and key claims directly from this, do not invent facts not present here):
---
{news_content.strip()[:4000]}
---
"""

    image_style = prompts.BEAT_IMAGE_STYLE.get(beat, "")
    animation_style = prompts.BEAT_ANIMATION_STYLE.get(beat, "")
    narration_tone = prompts.BEAT_NARRATION_TONE.get(beat, "")

    return f"""[FULL]
Topic: {topic}
Beat: {beat}
Language: {language}
Tone: {tone}
Persona: {resolved_persona} — {persona_desc}
Voice delivery style: {voice_prompt}
Narration tone for this beat: {narration_tone}
Template hint: {template_id}
Date: {date_str}

Visual style guide for {beat} beat:
{image_style}

Animation style guide for {beat} beat:
{animation_style}
{source_block}
Generate a 5-scene production script WITH text_cards. Total video = exactly 60 seconds.
Budget breakdown: 5 scenes × 10s = 50s + 2 text cards × 4s = 8s + 2s padding = 60s total. DO NOT exceed this.
Scenes 1 and 3 = AVATAR. Scenes 2, 4, 5 = CUTAWAY.
text_cards: MANDATORY — exactly 2 cards. Injected after scene 2 and after scene 4 in the timeline. Each card has 2 text_lines (MAX 4 WORDS each), overlay_text, and image_prompt.

{prompts.SCRIPT_JSON_SCHEMA}"""


def _call_claude(system_prompt: str, user_message: str) -> str:
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    logger.info(f"Calling Claude ({config.CLAUDE_MODEL})...")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=6000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()


def _call_groq(system_prompt: str, user_message: str) -> str:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")
    from groq import Groq, RateLimitError, BadRequestError
    client = Groq(api_key=config.GROQ_API_KEY)

    for model in (config.GROQ_MODEL, config.GROQ_FALLBACK_MODEL):
        try:
            logger.info(f"Calling Groq ({model})...")
            response = client.chat.completions.create(
                model=model,
                max_tokens=6000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content.strip()
        except (RateLimitError, BadRequestError) as e:
            # Catches 429 (TPD/TPM rate limit) and 413 (request too large for model tier)
            if model == config.GROQ_FALLBACK_MODEL:
                raise RuntimeError(f"Groq limit hit on both primary and fallback: {e}")
            logger.warning(f"Groq limit on {model} ({type(e).__name__}) — switching to fallback ({config.GROQ_FALLBACK_MODEL})...")
        except Exception:
            raise


def _call_openrouter(system_prompt: str, user_message: str, model: str = None) -> str:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")
    import httpx

    primary = model or config.OPENROUTER_QWEN_MODEL
    # Auto-fallback chain: if primary is rate-limited, try next in sequence
    fallback_chain = [primary, config.OPENROUTER_DEEPSEEK_MODEL, config.OPENROUTER_NEMOTRON_MODEL]
    seen, models_to_try = set(), []
    for m in fallback_chain:
        if m not in seen:
            seen.add(m)
            models_to_try.append(m)

    last_error = None
    for m in models_to_try:
        logger.info(f"Calling OpenRouter ({m})...")
        response = httpx.post(
            f"{config.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": m,
                "max_tokens": 6000,
                "include_reasoning": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=300,
        )
        if response.status_code in (429, 524, 503):
            logger.warning(f"OpenRouter {m} unavailable ({response.status_code}) — trying next model...")
            last_error = f"{m} returned {response.status_code}"
            continue
        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter error {response.status_code}: {response.text[:300]}")

        data = response.json()
        logger.debug(f"OpenRouter response keys: {list(data.keys())}")
        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"].get("content") or ""
            if not content.strip():
                content = data["choices"][0]["message"].get("reasoning_content", "")
            if content.strip():
                return content.strip()
            last_error = f"{m} returned empty content"
            logger.warning(f"{last_error} — trying next model...")
            continue
        if "content" in data and data["content"]:
            return data["content"].strip()
        last_error = f"{m} returned unexpected structure: {str(data)[:150]}"
        logger.warning(f"{last_error} — trying next model...")

    raise RuntimeError(f"All OpenRouter models failed. Last: {last_error}")


def summarize_article(text: str, provider: str = "groq") -> str:
    """
    Passes full article text to Groq/Claude for a structured fact-pack summary.
    Preserves all key numbers, quotes, entities, and claims.
    Returns a condensed summary (~400-500 words) for use as script source material.
    Falls back to the original text if the API call fails.
    """
    if provider != "groq":
        logger.info(f"Summarizing article ({len(text)} chars) via {provider} ({config.CLAUDE_MODEL})...")

    system = (
        "You are a news analyst preparing source material for a video scriptwriter. "
        "Your job is to extract and structure all the important information from a news article "
        "so a scriptwriter can write an accurate 60-second video without reading the full piece."
    )

    user = f"""Summarize the following news article into a structured fact pack.

Include ALL of these, in this order:
1. Core story: what happened and why it matters (2-3 sentences, specific)
2. Key data: every specific number, percentage, figure, date mentioned
3. Key quotes: verbatim quotes from named sources (include who said it)
4. Named entities: people with roles, organizations, places, timelines
5. Background context: relevant history, comparisons, prior events
6. What's next: upcoming decisions, deadlines, implications

Rules:
- Preserve exact numbers and claims — do not round or paraphrase figures
- Do not editorialize or add analysis not present in the article
- Plain prose, no markdown, no bullet symbols
- Max 500 words

Article:
---
{text[:6000]}
---"""

    try:
        if provider == "groq":
            if not config.GROQ_API_KEY:
                logger.warning("GROQ_API_KEY not set — skipping summarization, using raw text.")
                return text
            from groq import Groq, RateLimitError, BadRequestError
            client = Groq(api_key=config.GROQ_API_KEY)
            summary = None
            for model in (config.GROQ_SUMMARIZE_MODEL, config.GROQ_FALLBACK_MODEL):
                try:
                    logger.info(f"Summarizing article ({len(text)} chars) via groq ({model})...")
                    response = client.chat.completions.create(
                        model=model,
                        max_tokens=900,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    )
                    summary = response.choices[0].message.content.strip()
                    break
                except (RateLimitError, BadRequestError):
                    if model == config.GROQ_FALLBACK_MODEL:
                        logger.warning("Limit hit on both summarization models — falling back to raw text.")
                        return text
                    logger.warning(f"Limit on {model} — switching to fallback ({config.GROQ_FALLBACK_MODEL})...")
            if summary is None:
                return text
        elif config.GROQ_API_KEY:
            # OpenRouter or Claude selected — use Groq for summarization (fast, cheap, same quality)
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            logger.info(f"Summarizing article ({len(text)} chars) via groq ({config.GROQ_SUMMARIZE_MODEL})...")
            response = client.chat.completions.create(
                model=config.GROQ_SUMMARIZE_MODEL,
                max_tokens=900,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            summary = response.choices[0].message.content.strip()
        elif config.ANTHROPIC_API_KEY:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=900,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            summary = response.content[0].text.strip()
        else:
            logger.warning("No API key available for summarization — using raw text.")
            return text

        logger.info(f"Summary generated — {len(summary)} chars.")
        return summary

    except Exception as e:
        logger.warning(f"Summarization failed: {e} — falling back to raw text.")
        return text


def detect_beat_and_tone(text: str, provider: str = "groq") -> dict:
    """
    Given article text or summary, returns {"beat": "...", "tone": "..."}.
    Falls back to {"beat": "Politics", "tone": "Serious"} on failure.
    """
    BEATS = ["Finance", "Business", "Politics", "Culture", "Global Affairs", "Crime/Tragedy", "Science/Tech", "Health"]
    TONES = ["Calm", "Energetic", "Serious", "Casual"]

    beat_definitions = (
        "Finance = stock markets, RBI, interest rates, economy, GDP, inflation, budgets, taxes.\n"
        "Business = startups, funding rounds, IPOs, companies, entrepreneurship, corporate strategy.\n"
        "Politics = government policy, elections, political parties, parliament, governance, civic failures, law enforcement failures.\n"
        "Culture = social media, internet trends, entertainment, celebrities, Gen Z lifestyle, sports.\n"
        "Global Affairs = international diplomacy, geopolitics, cross-border conflict, foreign policy, trade wars.\n"
        "Crime/Tragedy = fires, accidents, deaths, natural disasters, crimes, civic safety failures, emergency response failures.\n"
        "Science/Tech = AI, technology products, space, scientific research, medical discoveries, environment.\n"
        "Health = public health, disease outbreaks, mental health, healthcare systems, nutrition, fitness."
    )

    system = "You are a news categorization engine. Return only valid JSON, no markdown, no commentary."
    user = f"""Classify this news article into exactly one beat and one tone.

Beat definitions:
{beat_definitions}

Tone options: Calm | Energetic | Serious | Casual
Tone = the emotional register most appropriate for a short-form video about this story.

Return exactly this JSON:
{{"beat": "<one of the 8 beat options>", "tone": "<one of the 4 tone options>"}}

Article:
---
{text[:2000]}
---"""

    try:
        import json as _json
        raw = ""
        _use_groq = provider != "claude" and config.GROQ_API_KEY
        if _use_groq:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            response = client.chat.completions.create(
                model=config.GROQ_FALLBACK_MODEL,  # 17B — beat detection, fast + cheap
                max_tokens=60,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            raw = response.choices[0].message.content.strip()
        elif config.ANTHROPIC_API_KEY:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=60,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = response.content[0].text.strip()

        result = _json.loads(raw)
        beat = result.get("beat", "Politics")
        tone = result.get("tone", "Serious")
        if beat not in BEATS:
            beat = "Politics"
        if tone not in TONES:
            tone = "Serious"
        logger.info(f"Auto-detected beat={beat}, tone={tone}")
        return {"beat": beat, "tone": tone}

    except Exception as e:
        logger.warning(f"Beat/tone detection failed: {e} — using defaults.")
        return {"beat": "Politics", "tone": "Serious"}


def generate_script(
    topic: str,
    beat: str,
    language: str = "Hinglish",
    tone: str = "Calm",
    persona_id: Optional[str] = None,
    news_content: Optional[str] = None,
    provider: str = "groq",
    video_type: str = "type1",
) -> dict:
    """
    Generates a production script via Claude or Groq.
    video_type: "type1" (6-scene standard) | "type2" (14-scene split-screen) | "drama" (two-character micro-drama)
    provider: "claude" | "groq"
    news_content: article text injected as factual source.
    """
    logger.info(f"Generating script — topic='{topic}' beat={beat} provider={provider} type={video_type}")

    if video_type == "type2":
        system_prompt = prompts.SYSTEM_PROMPT_TYPE2
        user_message = _build_user_message_type2(topic, beat, language, tone, persona_id, news_content)
    elif video_type == "drama":
        system_prompt = prompts.SYSTEM_PROMPT_DRAMA
        user_message = _build_user_message_drama(topic, beat, language, tone, news_content)
    else:
        system_prompt = config.load_system_prompt()
        user_message = _build_user_message(topic, beat, language, tone, persona_id, news_content)

    if provider == "claude":
        raw = _call_claude(system_prompt, user_message)
    elif provider == "openrouter_deepseek":
        raw = _call_openrouter(system_prompt, user_message, model=config.OPENROUTER_DEEPSEEK_MODEL)
    elif provider == "openrouter_nemotron":
        raw = _call_openrouter(system_prompt, user_message, model=config.OPENROUTER_NEMOTRON_MODEL)
    elif provider == "openrouter_llama70b":
        raw = _call_openrouter(system_prompt, user_message, model="meta-llama/llama-3.3-70b-instruct")
    else:
        raw = _call_groq(system_prompt, user_message)

    # Strip markdown fences either model might add
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Reasoning models (e.g. Nemotron) may output chain-of-thought before the JSON.
    # Find the first { or [ and trim everything before it.
    first_brace = min(
        (raw.find("{") if raw.find("{") != -1 else len(raw)),
        (raw.find("[") if raw.find("[") != -1 else len(raw)),
    )
    if first_brace > 0:
        raw = raw[first_brace:]

    # Replace literal control characters inside JSON string values.
    # LLMs sometimes emit real newlines/tabs inside strings instead of \n/\t,
    # which json.loads rejects as invalid control characters.
    def _escape_string_contents(s: str) -> str:
        result = []
        in_string = False
        escape_next = False
        for ch in s:
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == "\\" and in_string:
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = not in_string
            elif in_string and ch == "\n":
                result.append("\\n")
            elif in_string and ch == "\r":
                result.append("\\r")
            elif in_string and ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        return "".join(result)

    raw = _escape_string_contents(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"{provider} returned invalid JSON. Raw output:\n{raw}\n\nError: {e}"
        )

    # Strip reasoning artifacts that leak into string fields (e.g. "Wait, let me count...")
    _REASONING_RE = re.compile(
        r'\s*(Wait[,.]|Let me count[^.]*\.|[A-Z]-[a-z]-[a-z]-|Count:|Counting:|'
        r'Let me re|Actually,\s+let|Hmm,|Let me verify|Re-counting|Step \d+:|'
        r'[A-Za-z]-[A-Za-z]-[A-Za-z]-[A-Za-z]).*',
        re.DOTALL
    )
    def _clean_reasoning(obj):
        if isinstance(obj, str):
            return _REASONING_RE.sub("", obj).strip()
        if isinstance(obj, dict):
            return {k: _clean_reasoning(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean_reasoning(i) for i in obj]
        return obj
    data = _clean_reasoning(data)

    if video_type == "type2":
        _validate_script_type2(data)
        data = _expand_type2_avatar_narrations(data, provider)
        data["video_type"] = "type2"
    elif video_type == "drama":
        _validate_script_drama(data)
        data["video_type"] = "drama"
        if not data.get("beat"):
            data["beat"] = beat  # guarantee beat is always present
    else:
        _validate_script(data)
        data = _expand_short_narrations(data, provider)

    if video_type == "drama":
        logger.info(f"Script OK — video_id={data['video_id']} type=drama")
    else:
        logger.info(f"Script OK — video_id={data['video_id']} persona={data['persona']} template={data['template']}")
    return data


def _build_user_message_type2(
    topic: str,
    beat: str,
    language: str,
    tone: str,
    persona_id: Optional[str],
    news_content: Optional[str] = None,
) -> str:
    resolved_persona = persona_id or BEAT_TO_PERSONA.get(beat, "BIZ-M-01")
    persona = PERSONA_BANK.get(resolved_persona)
    persona_desc = (
        f"{persona.description} ({persona.language}, {persona.setting})"
        if persona else resolved_persona
    )
    date_str = datetime.now().strftime("%Y%m%d-%H%M")

    source_block = ""
    if news_content and news_content.strip():
        source_block = f"""
Source material (pull all data and claims directly from this):
---
{news_content.strip()[:4000]}
---
"""

    return f"""[TYPE2]
Topic: {topic}
Beat: {beat}
Language: {language}
Tone: {tone}
Persona: {resolved_persona} — {persona_desc}
Date: {date_str}
{source_block}
Generate a 14-scene split-screen video script:
- Scenes 1–2: AVATAR (30 seconds each, EXACTLY 450 characters narration)
- Scenes 3–7: CUTAWAY (5 seconds each, silent) — reinforce avatar scene 1
- Scene 8: TEXT_CARD (4 seconds) — mid-video fact drop with 2 text_lines
- Scenes 9–13: CUTAWAY (5 seconds each, silent) — reinforce avatar scene 2
- Scene 14: TEXT_CARD (4 seconds) — closing implication card with 2 text_lines
Total: 10 cutaways + 2 text cards = 12 non-avatar scenes.

{prompts.SCRIPT_JSON_SCHEMA_TYPE2}"""


def _validate_script(data: dict) -> None:
    required_keys = {"video_id", "persona", "template", "angle", "scenes"}
    missing = required_keys - data.keys()
    if missing:
        raise RuntimeError(f"Claude script missing keys: {missing}")

    scenes = data["scenes"]
    if len(scenes) != 5:
        raise RuntimeError(f"Expected 5 scenes, got {len(scenes)}")

    for i, s in enumerate(scenes):
        expected_type = "AVATAR" if i in (0, 2) else "CUTAWAY"
        if s.get("type") != expected_type:
            raise RuntimeError(
                f"Scene {i+1} should be {expected_type} but got {s.get('type')}"
            )

        narration = s.get("narration", "")
        char_count = len(narration)
        if char_count < 130:
            logger.warning(
                f"Scene {i+1} ({s.get('type')}) narration is {char_count} chars — "
                f"will auto-expand to ~150."
            )
        elif char_count > 165:
            logger.warning(
                f"Scene {i+1} ({s.get('type')}) narration is {char_count} chars — "
                f"exceeds 150-char target, audio may be cut."
            )

    text_cards = data.get("text_cards", [])
    if not text_cards:
        logger.warning("Type1 script missing text_cards — LLM did not generate them.")
    elif not (1 <= len(text_cards) <= 2):
        logger.warning(f"Type1 script has {len(text_cards)} text_cards — expected 1-2.")


def _validate_script_type2(data: dict) -> None:
    required_keys = {"video_id", "persona", "template", "angle", "scenes"}
    missing = required_keys - data.keys()
    if missing:
        raise RuntimeError(f"Type2 script missing keys: {missing}")

    scenes = data["scenes"]
    if len(scenes) != 14:
        raise RuntimeError(f"Type2 expected 14 scenes, got {len(scenes)}")

    # Expected layout: AVATAR(1,2) CUTAWAY(3-7) TEXT_CARD(8) CUTAWAY(9-13) TEXT_CARD(14)
    for i, s in enumerate(scenes):
        snum = i + 1
        if snum in (1, 2):
            expected = "AVATAR"
        elif snum == 8 or snum == 14:
            expected = "TEXT_CARD"
        else:
            expected = "CUTAWAY"

        actual = s.get("type")
        if actual != expected:
            logger.warning(f"Type2 scene {snum} expected {expected}, got {actual} — correcting.")
            s["type"] = expected

        if expected == "AVATAR":
            narration = s.get("narration", "")
            cc = len(narration)
            if cc < 400:
                logger.warning(f"Type2 avatar scene {snum} narration is {cc} chars — target 450.")
            elif cc > 500:
                logger.warning(f"Type2 avatar scene {snum} narration is {cc} chars — may run long.")
        elif expected == "CUTAWAY":
            if not s.get("image_prompt"):
                logger.warning(f"Type2 cutaway scene {snum} missing image_prompt.")
            if not s.get("animation_prompt"):
                logger.warning(f"Type2 cutaway scene {snum} missing animation_prompt.")
        elif expected == "TEXT_CARD":
            if not s.get("text_lines"):
                logger.warning(f"Type2 text card scene {snum} missing text_lines.")
            if not s.get("image_prompt"):
                logger.warning(f"Type2 text card scene {snum} missing image_prompt.")

    # Extract TEXT_CARD scenes into data["text_cards"] for backwards-compatible pipeline processing
    tc_scenes = [s for s in scenes if s.get("type") == "TEXT_CARD"]
    data["text_cards"] = [
        {
            "card_id": i + 1,
            "purpose": "mid-video fact drop" if i == 0 else "closing implication",
            "text_lines": s.get("text_lines", []),
            "overlay_text": s.get("overlay_text", ""),
            "duration_seconds": s.get("duration_seconds", 4),
            "image_prompt": s.get("image_prompt", ""),
        }
        for i, s in enumerate(tc_scenes)
    ]
    if not data["text_cards"]:
        logger.warning("Type2 script has no TEXT_CARD scenes — text cards will be skipped.")


def _build_user_message_drama(
    topic: str,
    beat: str,
    language: str,
    tone: str,
    news_content: Optional[str] = None,
) -> str:
    date_str = datetime.now().strftime("%Y%m%d-%H%M")

    source_block = ""
    if news_content and news_content.strip():
        source_block = f"""
Source material (pull all data, names, and claims directly from this — do not invent):
---
{news_content.strip()[:4000]}
---
"""

    return f"""[DRAMA]
Topic: {topic}
Beat: {beat}
Language: {language}
Tone: {tone}
Date: {date_str}
{source_block}
Generate a two-character micro-drama script for this news story.
- Character 1: the human cost — the person directly affected by the incident.
- Character 2: the systemic layer — the person who holds institutional responsibility.
- Both must arrive at the same convergence line from opposite directions.
- The convergence line is the thesis — one verifiable truth, not an opinion.
- All dialogue must be written for voice: short sentences, natural pauses, [beat] markers.
- Text card lines must be pulled directly from the source — exact numbers, names, dates.

CASTING — READ BEFORE WRITING THE SCHEMA:
Step 1: From the source article, identify who was harmed (occupation, age, gender if stated).
Step 2: From the source article, identify who held responsibility (role, institution).
Step 3: Assign char1 and char2 from those facts only.
BANNED: young woman char1 + middle-aged man char2. This combination is not allowed.
BANNED: generic "affected woman" or "concerned resident" as char1 if the article doesn't name a woman.
DEFAULT when gender is unspecified: use two men, two women, or an elderly char1 — not a young woman.
If you are about to write a young woman as char1 and an older man as char2 without article evidence: STOP. Recast.

{prompts.SCRIPT_JSON_SCHEMA_DRAMA}"""


def _validate_script_drama(data: dict) -> None:
    required_keys = {"video_id", "video_type", "characters", "takes", "text_cards", "split_screen", "storyboard"}
    missing = required_keys - data.keys()
    if missing:
        raise RuntimeError(f"Drama script missing keys: {missing}")

    chars = data.get("characters", {})
    if set(chars.keys()) != {"char1", "char2"}:
        raise RuntimeError(f"Drama script must have exactly char1 and char2, got: {list(chars.keys())}")

    takes = data.get("takes", {})
    if len(takes.get("char1", [])) != 3:
        raise RuntimeError(f"Drama char1 must have 3 takes, got {len(takes.get('char1', []))}")
    if len(takes.get("char2", [])) != 3:
        raise RuntimeError(f"Drama char2 must have 3 takes, got {len(takes.get('char2', []))}")

    # Verify convergence line matches in both characters' final takes and split_screen block
    conv_char1 = takes["char1"][2].get("script", "").strip().split("\n")[-1].strip()
    conv_char2 = takes["char2"][2].get("script", "").strip().split("\n")[-1].strip()
    conv_split  = data.get("split_screen", {}).get("convergence_line", "").strip()
    if conv_char1 != conv_char2:
        logger.warning(f"Drama convergence line mismatch — char1: '{conv_char1}' / char2: '{conv_char2}'")
    if conv_split and conv_split not in (conv_char1, conv_char2):
        logger.warning(f"Drama split_screen.convergence_line doesn't match take scripts.")

    text_cards = data.get("text_cards", [])
    if not (1 <= len(text_cards) <= 2):
        raise RuntimeError(f"Drama script must have 1 or 2 text_cards, got {len(text_cards)}")

    for char_id, char_data in chars.items():
        for field in ("avatar_image_prompt", "voice_prompt", "higgsfield_prompt"):
            if not char_data.get(field):
                logger.warning(f"Drama {char_id} missing field: {field}")

    logger.info("Drama script validation passed.")


def _expand_type2_avatar_narrations(data: dict, provider: str) -> dict:
    """Auto-expands Type 2 AVATAR narrations that are under 430 chars to hit the 430-450 target."""
    scenes = data.get("scenes", [])
    avatar_scenes = [s for s in scenes if s.get("type") == "AVATAR" and len(s.get("narration", "")) < 430]
    if not avatar_scenes:
        return data

    logger.info(f"Auto-expanding {len(avatar_scenes)} Type 2 AVATAR narration(s) to 430-450 chars...")
    for s in scenes:
        if s.get("type") != "AVATAR":
            continue
        cc = len(s.get("narration", ""))
        if cc >= 430:
            continue
        original = s["narration"]
        system = (
            "You are a video script editor. Rewrite the narration to be between 430 and 450 characters "
            "including spaces. Preserve all facts, names, and numbers. Add context, consequence, or "
            "detail to reach the target length — no filler. Return only the rewritten narration. "
            "No quotes, no labels, no explanation."
        )
        user = (
            f"Rewrite this 30-second AVATAR narration to be between 430 and 450 characters including spaces.\n"
            f"Keep all facts intact. Expand with relevant detail to hit the target.\n\n"
            f"Current narration ({cc} chars):\n{original}\n\n"
            f"Return only the rewritten narration."
        )
        try:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=config.GROQ_MODEL,
                max_tokens=200,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            expanded = resp.choices[0].message.content.strip()
            new_cc = len(expanded)
            logger.info(f"  Scene {s['scene_number']} AVATAR: {cc} → {new_cc} chars")
            s["narration"] = expanded
        except Exception as e:
            logger.warning(f"Type 2 narration expansion failed for scene {s['scene_number']}: {e} — keeping original.")

    return data


def _expand_narration(narration: str, scene_type: str, provider: str) -> str:
    """
    Adjusts a narration to exactly ~150 characters via a targeted LLM call.
    Preserves the opening hook/punchline — only adjusts length.
    Returns the adjusted narration string, or the original if the call fails.
    """
    current_chars = len(narration)
    system = (
        "You are a video script editor. Your only job is to rewrite a narration "
        "to be EXACTLY 150 characters including spaces. "
        "Preserve the opening hook word-for-word. "
        "Add or remove words to hit exactly 150 characters — no filler, no repetition. "
        "Return only the rewritten narration. No quotes, no labels, no explanation."
    )
    scene_label = "hook (Scene 1 or 4 — AVATAR, talking head)" if scene_type == "AVATAR" else "cutaway narration"
    user = (
        f"Rewrite this {scene_label} to be EXACTLY 150 characters including spaces.\n"
        f"Keep the opening exactly as written. Adjust the rest to hit 150 chars.\n\n"
        f"Current narration ({current_chars} chars):\n{narration}\n\n"
        f"Return only the rewritten narration. Count characters before responding."
    )
    try:
        if provider == "groq":
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=config.GROQ_MODEL,
                max_tokens=120,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content.strip()
        else:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=120,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Narration expansion failed: {e} — keeping original.")
        return narration


def _expand_short_narrations(data: dict, provider: str) -> dict:
    """
    Checks every scene narration. If under 28 words, expands it via a targeted LLM call.
    Runs only for scenes that need it — not a full regeneration.
    """
    scenes = data.get("scenes", [])
    needs_expansion = [
        s for s in scenes if len(s.get("narration", "")) < 130 or len(s.get("narration", "")) > 165
    ]
    if not needs_expansion:
        return data

    logger.info(f"Auto-adjusting {len(needs_expansion)} narration(s) to 150 chars...")
    for s in scenes:
        cc = len(s.get("narration", ""))
        if cc < 130 or cc > 165:
            original = s["narration"]
            adjusted = _expand_narration(original, s.get("type", "CUTAWAY"), provider)
            new_cc = len(adjusted)
            logger.info(
                f"  Scene {s['scene_number']} ({s['type']}): {cc} → {new_cc} chars"
            )
            s["narration"] = adjusted

    return data


def scenes_from_script(script_data: dict) -> list[Scene]:
    """Converts the raw Claude JSON dict to a list of Scene objects."""
    return [Scene.from_dict(s) for s in script_data["scenes"]]
