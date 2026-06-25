from dataclasses import dataclass
from typing import Dict


@dataclass
class Persona:
    id: str
    label: str
    description: str
    gender: str
    age_range: str
    tone: str
    language: str
    setting: str
    beats: list[str]
    avatar_prompt_base: str
    voice_prompt: str


PERSONA_BANK: Dict[str, Persona] = {
    "FIN-F-01": Persona(
        id="FIN-F-01",
        label="Finance Female",
        description="Indian female finance creator, mid-20s, calm analytical Gen Z tone",
        gender="female",
        age_range="mid-20s",
        tone="calm, analytical",
        language="Hinglish/English",
        setting="modern household/podcast desk",
        beats=["finance", "economy", "investing", "credit", "markets"],
        avatar_prompt_base=(
            "A realistic young Indian woman in her mid-20s, calm expression, "
            "looking directly at camera, modern podcast desk background with soft warm lighting, "
            "wearing a casual smart top, 9:16 vertical, chest-up medium close-up, "
            "natural skin texture, slight imperfections, shallow depth of field. "
            "No captions, no subtitles, no text overlay, no logos, no watermark, no UI."
        ),
        voice_prompt=(
            "Young Indian female voice, urban Gen Z Hinglish delivery, calm and confident, "
            "slightly analytical, conversational, not formal anchor style, "
            "moderate pace, short pauses, clean articulation."
        ),
    ),
    "POL-F-01": Persona(
        id="POL-F-01",
        label="Politics Female",
        description="Indian female political explainer, late-20s, calm serious tone",
        gender="female",
        age_range="late-20s",
        tone="calm, serious",
        language="Hindi/Hinglish",
        setting="clean indoor commentary setup",
        beats=["politics", "policy", "elections", "government", "law"],
        avatar_prompt_base=(
            "A realistic young Indian woman in her late-20s, serious composed expression, "
            "looking directly at camera, clean minimal indoor commentary setup, soft neutral lighting, "
            "wearing a professional kurta or formal top, 9:16 vertical, chest-up medium close-up, "
            "natural skin texture, shallow depth of field. "
            "No captions, no subtitles, no text overlay, no logos, no watermark, no UI."
        ),
        voice_prompt=(
            "Young Indian female voice, serious analytical delivery, Hindi/Hinglish, "
            "authoritative but accessible, moderate-slow pace, clear diction, "
            "measured pauses, not anchored formal style."
        ),
    ),
    "BIZ-M-01": Persona(
        id="BIZ-M-01",
        label="Business Male",
        description="Indian male business/startup explainer, late-20s, smart casual",
        gender="male",
        age_range="late-20s",
        tone="confident, smart casual",
        language="English/Hinglish",
        setting="modern workspace",
        beats=["business", "startups", "entrepreneurship", "tech", "funding"],
        avatar_prompt_base=(
            "A realistic young Indian man in his late-20s, confident expression, "
            "looking directly at camera, modern minimal workspace background with soft lighting, "
            "wearing a smart casual shirt, 9:16 vertical, chest-up medium close-up, "
            "natural skin texture, shallow depth of field. "
            "No captions, no subtitles, no text overlay, no logos, no watermark, no UI."
        ),
        voice_prompt=(
            "Young Indian male voice, confident English/Hinglish delivery, "
            "smart casual tone, energetic but measured, slightly fast pace, "
            "conversational, knowledgeable, not scripted-sounding."
        ),
    ),
    "POP-F-01": Persona(
        id="POP-F-01",
        label="Culture Female",
        description="Indian female internet/culture creator, early-20s, casual Gen Z tone",
        gender="female",
        age_range="early-20s",
        tone="casual, Gen Z",
        language="Hinglish",
        setting="cozy bedroom/creator setup",
        beats=["culture", "internet", "social media", "influencers", "trends", "entertainment"],
        avatar_prompt_base=(
            "A realistic young Indian woman in her early-20s, casual friendly expression, "
            "looking directly at camera, cozy creator bedroom setup with ring light glow, "
            "wearing casual trendy clothes, 9:16 vertical, chest-up medium close-up, "
            "natural skin texture, warm lighting, shallow depth of field. "
            "No captions, no subtitles, no text overlay, no logos, no watermark, no UI."
        ),
        voice_prompt=(
            "Young Indian female voice, casual Gen Z Hinglish delivery, "
            "energetic and relatable, quick pace with natural rhythm, "
            "conversational, not formal, sounds like a friend explaining something."
        ),
    ),
    "GLO-F-01": Persona(
        id="GLO-F-01",
        label="Global Affairs Female",
        description="Indian female global affairs explainer, late-20s, serious analytical tone",
        gender="female",
        age_range="late-20s",
        tone="serious, analytical",
        language="English/Hinglish",
        setting="darker podcast/news setup",
        beats=["global affairs", "geopolitics", "war", "oil", "international", "diplomacy"],
        avatar_prompt_base=(
            "A realistic young Indian woman in her late-20s, serious analytical expression, "
            "looking directly at camera, darker moody podcast/news studio background, "
            "subtle rim lighting, wearing a professional dark top, 9:16 vertical, chest-up medium close-up, "
            "natural skin texture, shallow depth of field. "
            "No captions, no subtitles, no text overlay, no logos, no watermark, no UI."
        ),
        voice_prompt=(
            "Young Indian female voice, serious English/Hinglish delivery, "
            "analytical and authoritative, measured pace, precise articulation, "
            "global affairs anchor tone but conversational, not overly formal."
        ),
    ),
}

BEAT_TO_PERSONA = {
    "Finance":        "FIN-F-01",
    "Politics":       "POL-F-01",
    "Business":       "BIZ-M-01",
    "Culture":        "POP-F-01",
    "Global Affairs": "GLO-F-01",
    "Crime/Tragedy":  "POL-F-01",  # serious, measured tone
    "Science/Tech":   "BIZ-M-01",  # informed, curious energy
    "Health":         "FIN-F-01",  # analytical, data-accessible
}
