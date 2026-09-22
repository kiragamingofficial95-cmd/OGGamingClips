"""FFmpeg video editing service for clip extraction and processing."""
import subprocess
import json
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict
from app.config import get_settings
from app.utils.logger import get_logger
from app.utils.validators import validate_clip_timestamps, sanitize_title

logger = get_logger("ffmpeg")


class FFmpegService:
    def __init__(self):
        self.settings = get_settings()

    def extract_clip(
        self,
        source_path: str,
        start_time: float,
        end_time: float,
        output_path: str,
        title: Optional[str] = None,
    ) -> Dict[str, any]:
        """Extract a clip from source video using FFmpeg."""
        duration = end_time - start_time

        if not validate_clip_timestamps(start_time, end_time):
            raise ValueError(f"Invalid timestamps: {start_time}-{end_time}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = self._build_cut_cmd(source_path, start_time, duration, output_path)
        logger.info("Extracting clip", source=source_path, start=start_time, end=end_time, output=output_path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg cut failed: {result.stderr[-500:]}")

        # Post-process
        self._post_process(output_path)

        # Verify output
        info = self._get_video_info(output_path)
        logger.info("Clip extracted", output=output_path, info=info)
        return info

    def process_clip(
        self,
        source_path: str,
        start_time: float,
        end_time: float,
        output_path: str,
        title: Optional[str] = None,
        subtitles: Optional[List[Dict]] = None,
    ) -> Dict[str, any]:
        """
        Full clip processing pipeline:
        1. Cut the timestamp range
        2. Convert to 9:16 vertical
        3. Add subtitles
        4. Normalize audio
        5. Export H.264 MP4
        """
        duration = end_time - start_time
        if not validate_clip_timestamps(start_time, end_time, min_dur=5, max_dur=300):
            raise ValueError(f"Invalid timestamps: {start_time}-{end_time}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Step 1: Cut the clip
        temp_cut = output_path.replace(".mp4", "_cut.mp4")
        cmd = self._build_cut_cmd(source_path, start_time, duration, temp_cut)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg cut failed: {result.stderr[-500:]}")

        # Step 2: Scale to 9:16 and add subtitles + audio normalization
        final_cmd = self._build_final_cmd(temp_cut, output_path, subtitles, title)
        result = subprocess.run(final_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg final process failed: {result.stderr[-500:]}")

        # Clean up temp file
        if os.path.exists(temp_cut):
            os.remove(temp_cut)

        # Verify
        info = self._get_video_info(output_path)

        # Add subtitles if provided
        if subtitles:
            self._burn_subtitles(output_path, subtitles)

        # Final verify
        final_info = self._get_video_info(output_path)
        logger.info("Clip processed", output=output_path, final_info=final_info)
        return final_info

    def _build_cut_cmd(self, source: str, start: float, duration: float, output: str):
        """Build FFmpeg cut command."""
        return [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", source,
            "-t", str(duration),
            "-c:v", "copy",
            "-c:a", "copy",
            "-avoid_negative_ts", "make_zero",
            output,
        ]

    def _build_final_cmd(self, input_path: str, output_path: str, subtitles, title: str):
        """Build final FFmpeg command for vertical conversion + subtitles + audio."""
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
        ]

        # Subtitles filter
        subtitle_filter = ""
        if subtitles and len(subtitles) > 0:
            subtitle_filter = self._build_subtitle_filter(subtitles)

        # Build complex filter: scale to 9:16, normalize audio
        filter_parts = []
        # Scale: crop to fill vertical, or pad to vertical
        filter_parts.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1")
        # Audio normalization
        filter_parts.append("loudnorm=I=-16:LRA=11:TP=-1.5")

        if subtitle_filter:
            filter_parts.append(subtitle_filter)

        filter_str = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_str])

        # Output settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-maxrate", "4M",
            "-bufsize", "8M",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_path,
        ])

        return cmd

    def _build_subtitle_filter(self, subtitles: List[Dict]) -> str:
        """Build FFmpeg subtitle draw filter."""
        if not subtitles:
            return ""

        # Create subtitle text
        sub_text = ""
        for i, sub in enumerate(subtitles):
            text = sub.get("text", "").replace(":", "\\:").replace("'", "\\'")
            start = sub.get("start", 0)
            end = sub.get("end", 5)
            if i == 0:
                sub_text += f"drawtext=text='{text}':fontcolor=white:fontsize=24:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:x=(w-text_w)/2:y=(h-40):enable='between(t,{start},{end})'"
            else:
                sub_text += f",drawtext=text='{text}':fontcolor=white:fontsize=24:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:x=(w-text_w)/2:y=(h-40):enable='between(t,{start},{end})'"

        return sub_text

    def _burn_subtitles(self, video_path: str, subtitles: List[Dict]):
        """Burn subtitles into video."""
        logger.info("Burning subtitles into video", path=video_path, count=len(subtitles))
        # This would use a subtitle filter; for simplicity, rely on drawtext above

    def _post_process(self, path: str):
        """Post-processing: remove silence, normalize."""
        # Use FFmpeg silence removal if practical
        pass

    def _get_video_info(self, path: str) -> Dict:
        """Get video metadata using FFprobe."""
        if not shutil.which("ffprobe"):
            return {"exists": False, "error": "ffprobe not found"}
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            return {"exists": False, "error": "ffprobe not found"}
        if result.returncode != 0:
            return {"exists": False}

        info = json.loads(result.stdout)
        video_stream = None
        audio_stream = None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
            elif s.get("codec_type") == "audio":
                audio_stream = s

        duration = float(info.get("format", {}).get("duration", 0))
        width = video_stream.get("width") if video_stream else None
        height = video_stream.get("height") if video_stream else None
        has_audio = audio_stream is not None
        file_size = os.path.getsize(path) if os.path.exists(path) else 0

        return {
            "exists": True,
            "duration": duration,
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}" if width and height else None,
            "has_audio": has_audio,
            "file_size_bytes": file_size,
        }

    def verify_clip(self, path: str, min_duration: float = 5, expected_resolution: str = "1080x1920") -> Dict:
        """Verify a clip meets quality standards."""
        info = self._get_video_info(path)

        if not info.get("exists"):
            return {"valid": False, "error": "File does not exist"}

        if info["duration"] < min_duration:
            return {"valid": False, "error": f"Duration too short: {info['duration']}s"}

        if info.get("resolution") != expected_resolution:
            return {"valid": False, "error": f"Wrong resolution: {info.get('resolution')}"}

        if not info.get("has_audio"):
            return {"valid": False, "error": "No audio stream"}

        return {"valid": True, "info": info}
