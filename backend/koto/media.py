from __future__ import annotations

import json
import re
import subprocess
import uuid
from pathlib import Path

from .runtime import executable


def binary(name):
    return executable(name)


def probe(path: Path):
    result = subprocess.run([binary("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError("This file could not be read as media: " + result.stderr[-500:])
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    streams = []
    for s in data.get("streams", []):
        if s.get("codec_type") not in ("video", "audio", "subtitle"):
            continue
        streams.append({"index": s["index"], "type": s["codec_type"], "codec": s.get("codec_name"), "language": s.get("tags", {}).get("language", "und"), "title": s.get("tags", {}).get("title", ""), "width": s.get("width"), "height": s.get("height"), "channels": s.get("channels"), "fps": s.get("avg_frame_rate", "0/0")})
    if not streams:
        raise ValueError("No video or audio tracks found")
    return {"duration": duration, "streams": streams}


def parse_subtitles(text: str):
    """Parse SRT/WebVTT after FFmpeg converts ASS; preserve subtitle text independently."""
    text = text.replace("\r\n", "\n").lstrip("\ufeff")
    pattern = re.compile(r"(?m)^(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)", re.S)
    lines = []
    for m in pattern.finditer(text):
        g = m.groups()
        start = int(g[0] or 0)*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000
        end = int(g[4] or 0)*3600 + int(g[5])*60 + int(g[6]) + int(g[7])/1000
        body = re.sub(r"<[^>]*>|\{[^}]*\}", "", g[8]).strip()
        if body and end > start:
            lines.append({"id": str(uuid.uuid4()), "start": start, "end": end, "speaker": "speaker-1", "source": "", "translation": "", "subtitle": body, "audio": None})
    return lines


def srt_time(seconds):
    ms = round(max(0, seconds)*1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(lines, path):
    blocks = []
    for i, line in enumerate(sorted(lines, key=lambda x:x["start"]), 1):
        text = line.get("translation") or line.get("subtitle") or line.get("source") or ""
        blocks.append(f"{i}\n{srt_time(line['start'])} --> {srt_time(line['end'])}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def atempo_factor(factor):
    filters = []
    while factor > 2:
        filters.append("atempo=2")
        factor /= 2
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append(f"atempo={factor:.8f}")
    return ",".join(filters)
