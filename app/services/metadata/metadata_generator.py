"""Metadata generator for clip titles, captions, and hashtags."""
from typing import Optional, List
from app.config import get_settings
from app.utils.logger import get_logger
from app.utils.validators import sanitize_title

logger = get_logger("metadata")

# Campaign-specific metadata
CAMPAIGN_INFO = {
    "campaign_id": "ForgeGUI Clipping [Roblox]",
    "brand": "BloxClips",
    "platform": "Instagram",
    "account": "OGGamingClips",
}

# Hashtag pool for Roblox/gaming content
DEFAULT_HASHTAGS = [
    "#Roblox", "#Gaming", "#RobloxClips", "#GamingClip", "#Shorts",
    "#Reels", "#IG", "#GamingCommunity", "#Clip", "#Funny",
    "#RobloxGameplay", "#OGGamingClips", "#BloxClips", "#ForgeGUI",
]


class MetadataGenerator:
    def __init__(self):
        self.settings = get_settings()

    def generate_title(self, candidate: dict) -> str:
        """Generate a short, catchy title from the candidate."""
        hook = candidate.get("hook", "")
        suggested = candidate.get("suggested_title", "")

        if suggested and len(suggested) > 5:
            return sanitize_title(suggested[:50])
        if hook:
            return sanitize_title(hook[:50])
        return "Roblox Clip"

    def generate_caption(self, candidate: dict, title: str) -> str:
        """Generate Instagram caption."""
        hook = candidate.get("hook", "")
        reason = candidate.get("reason", "")

        caption_parts = [title]
        if hook:
            caption_parts.append(f"\n\n{hook}")
        if reason:
            caption_parts.append(f"\n\n{reason[:100]}")

        caption_parts.append(f"\n\n{CAMPAIGN_INFO['campaign_id']}")

        return sanitize_title(" ".join(caption_parts))

    def generate_hashtags(self, candidate: dict, max_count: int = 15) -> List[str]:
        """Generate relevant hashtags."""
        reason = candidate.get("reason", "").lower()
        hashtags = list(DEFAULT_HASHTAGS)

        if "funny" in reason or "reaction" in reason:
            hashtags.append("#FunnyRoblox")
        if "gameplay" in reason or "exciting" in reason:
            hashtags.append("#GameplayHighlights")
        if "surprising" in reason:
            hashtags.append("#MindBlown")
        if "educational" in reason or "useful" in reason:
            hashtags.append("#GamingTips")

        return hashtags[:max_count]

    def generate_metadata(self, candidate: dict, clip_info: dict = None) -> dict:
        """Generate full metadata package for a clip."""
        title = self.generate_title(candidate)
        caption = self.generate_caption(candidate, title)
        hashtags = self.generate_hashtags(candidate)

        metadata = {
            "title": title,
            "caption": caption,
            "hashtags": hashtags,
            "source_id": candidate.get("source_id"),
            "campaign_id": CAMPAIGN_INFO["campaign_id"],
            "brand": CAMPAIGN_INFO["brand"],
            "platform": CAMPAIGN_INFO["platform"],
            "account": CAMPAIGN_INFO["account"],
            "clip_start": candidate.get("start_time"),
            "clip_end": candidate.get("end_time"),
            "ai_score": candidate.get("score"),
            "hook": candidate.get("hook"),
            "suggested_title": candidate.get("suggested_title"),
            "generated_at": None,
            "clip_info": clip_info or {},
        }

        return metadata

    def save_metadata(self, metadata: dict, clip_id: str):
        """Save metadata to JSON file."""
        import json
        from datetime import datetime

        metadata["generated_at"] = datetime.utcnow().isoformat()

        output_dir = self.settings.metadata_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / f"{clip_id}_metadata.json"
        with open(path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info("Metadata saved", clip_id=clip_id, path=str(path))
        return str(path)
