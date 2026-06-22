from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Scene:
    scene_number: int
    type: str  # "AVATAR" or "CUTAWAY"
    duration_seconds: int
    narration: str
    scene_description: str          # Abstract visual concept for this scene — NSFW-safe, narration-derived
    image_prompt: str               # Full Nano Banana formatted prompt built from scene_description
    animation_prompt: Optional[str] = None
    overlay_text: Optional[str] = None

    # Populated during generation
    audio_path: Optional[str] = None
    image_path: Optional[str] = None
    image_cdn_url: Optional[str] = None
    static_video_path: Optional[str] = None
    lipsync_video_path: Optional[str] = None
    cutaway_video_path: Optional[str] = None
    final_video_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "scene_number": self.scene_number,
            "type": self.type,
            "duration_seconds": self.duration_seconds,
            "narration": self.narration,
            "scene_description": self.scene_description,
            "image_prompt": self.image_prompt,
            "animation_prompt": self.animation_prompt,
            "overlay_text": self.overlay_text,
            "audio_path": self.audio_path,
            "image_path": self.image_path,
            "image_cdn_url": self.image_cdn_url,
            "static_video_path": self.static_video_path,
            "lipsync_video_path": self.lipsync_video_path,
            "cutaway_video_path": self.cutaway_video_path,
            "final_video_path": self.final_video_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(
            scene_number=d["scene_number"],
            type=d["type"],
            duration_seconds=d.get("duration_seconds", 10),
            narration=d["narration"],
            scene_description=d.get("scene_description", ""),
            image_prompt=d["image_prompt"],
            animation_prompt=d.get("animation_prompt"),
            overlay_text=d.get("overlay_text"),
            audio_path=d.get("audio_path"),
            image_path=d.get("image_path"),
            image_cdn_url=d.get("image_cdn_url"),
            static_video_path=d.get("static_video_path"),
            lipsync_video_path=d.get("lipsync_video_path"),
            cutaway_video_path=d.get("cutaway_video_path"),
            final_video_path=d.get("final_video_path"),
        )
