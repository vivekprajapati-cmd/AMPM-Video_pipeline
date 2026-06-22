from dataclasses import dataclass
from typing import Dict, List


@dataclass
class StoryTemplate:
    id: str
    name: str
    description: str
    best_for: List[str]
    structure: Dict[str, str]


STORY_TEMPLATES: Dict[str, StoryTemplate] = {
    "TEMPLATE_A": StoryTemplate(
        id="TEMPLATE_A",
        name="EXPLAINER",
        description="Best for finance, economy, policy, business",
        best_for=["finance", "economy", "policy", "business"],
        structure={
            "0-10s (Scene 1 — AVATAR)":  "Hook — grab attention with the core claim",
            "10-20s (Scene 2 — CUTAWAY)": "What happened — the factual setup",
            "20-30s (Scene 3 — CUTAWAY)": "Why it matters — impact and relevance",
            "30-40s (Scene 4 — AVATAR)":  "Bigger pattern — zoom out, connect to larger story",
            "40-50s (Scene 5 — CUTAWAY)": "Data / evidence — support the pattern",
            "50-60s (Scene 6 — CUTAWAY)": "Final takeaway — one clear actionable insight",
        },
    ),
    "TEMPLATE_B": StoryTemplate(
        id="TEMPLATE_B",
        name="CONTRAST",
        description="Best for X vs Y stories, contradictions, comparison",
        best_for=["comparison", "contradiction", "versus", "debate"],
        structure={
            "0-10s (Scene 1 — AVATAR)":  "Contradiction hook — state the paradox",
            "10-20s (Scene 2 — CUTAWAY)": "Side A — first position with evidence",
            "20-30s (Scene 3 — CUTAWAY)": "Side B — opposing position",
            "30-40s (Scene 4 — AVATAR)":  "What changed — the pivot or shift",
            "40-50s (Scene 5 — CUTAWAY)": "Impact — real-world consequences",
            "50-60s (Scene 6 — CUTAWAY)": "Punchline — one sharp closing line",
        },
    ),
    "TEMPLATE_C": StoryTemplate(
        id="TEMPLATE_C",
        name="TIMELINE",
        description="Best for war, oil crisis, policy changes, market events",
        best_for=["war", "oil", "crisis", "markets", "policy changes", "timeline"],
        structure={
            "0-10s (Scene 1 — AVATAR)":  "Hook — the dramatic present moment",
            "10-20s (Scene 2 — CUTAWAY)": "Before — the starting state",
            "20-30s (Scene 3 — CUTAWAY)": "Trigger — what caused the shift",
            "30-40s (Scene 4 — AVATAR)":  "Now — current situation",
            "40-50s (Scene 5 — CUTAWAY)": "Scale of impact — numbers, map, chart",
            "50-60s (Scene 6 — CUTAWAY)": "What happens next — forward-looking close",
        },
    ),
    "TEMPLATE_D": StoryTemplate(
        id="TEMPLATE_D",
        name="MYTH VS REALITY",
        description="Best for Gen Z money, career, social media, internet trends",
        best_for=["myth", "reality", "misconception", "Gen Z", "social media", "career"],
        structure={
            "0-10s (Scene 1 — AVATAR)":  "Viral belief — state the popular misconception",
            "10-20s (Scene 2 — CUTAWAY)": "Reality — the actual truth with evidence",
            "20-30s (Scene 3 — CUTAWAY)": "Data that proves it — visual proof",
            "30-40s (Scene 4 — AVATAR)":  "Why people believe it — root cause of the myth",
            "40-50s (Scene 5 — CUTAWAY)": "What actually matters — reframe the conversation",
            "50-60s (Scene 6 — CUTAWAY)": "Final line — sharp memorable closer",
        },
    ),
    "TEMPLATE_E": StoryTemplate(
        id="TEMPLATE_E",
        name="STRATEGY BREAKDOWN",
        description="Best for elections, companies, campaigns, geopolitics",
        best_for=["elections", "strategy", "campaigns", "companies", "geopolitics"],
        structure={
            "0-10s (Scene 1 — AVATAR)":  "Result — start with the outcome",
            "10-20s (Scene 2 — CUTAWAY)": "Strategy used — break down the approach",
            "20-30s (Scene 3 — CUTAWAY)": "Why it worked — mechanics of success",
            "30-40s (Scene 4 — AVATAR)":  "Who it affected — players and stakes",
            "40-50s (Scene 5 — CUTAWAY)": "Impact — downstream effects",
            "50-60s (Scene 6 — CUTAWAY)": "Larger lesson — what this means beyond the event",
        },
    ),
}

BEAT_TO_TEMPLATE = {
    "Finance": "TEMPLATE_A",
    "Politics": "TEMPLATE_E",
    "Business": "TEMPLATE_A",
    "Culture": "TEMPLATE_D",
    "Global Affairs": "TEMPLATE_C",
}
