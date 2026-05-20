from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from loguru import logger

from .models import SubtitleItem


SRT_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)


def _timedelta_to_ms(value: dt.timedelta) -> int:
    return int(round(value.total_seconds() * 1000))


def _parse_time_to_ms(value: str) -> int:
    value = value.replace(",", ".")
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(".")
    return (
        int(hours) * 3600 * 1000
        + int(minutes) * 60 * 1000
        + int(seconds) * 1000
        + int(millis)
    )


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def read_srt(path: Path) -> list[SubtitleItem]:
    logger.info("解析 SRT 字幕: {}", path)
    if not path.exists():
        raise FileNotFoundError(f"SRT 文件不存在: {path}")
    content = _read_text(path)

    items = _parse_with_srt_package(content)
    if items:
        logger.info("SRT 解析完成: {} 条", len(items))
        return items

    items = _parse_with_pysrt(path)
    if items:
        logger.info("SRT 解析完成: {} 条", len(items))
        return items

    items = _parse_srt_fallback(content)
    logger.info("SRT 解析完成: {} 条", len(items))
    if not items:
        raise ValueError("SRT 文件没有可用字幕")
    return items


def _parse_with_srt_package(content: str) -> list[SubtitleItem]:
    try:
        import srt
    except Exception:
        return []

    try:
        subtitles = list(srt.parse(content))
    except Exception as exc:
        logger.warning("srt 包解析失败，使用备用解析器: {}", exc)
        return []

    return [
        SubtitleItem(
            index=subtitle.index or offset + 1,
            start_ms=_timedelta_to_ms(subtitle.start),
            end_ms=_timedelta_to_ms(subtitle.end),
            text=subtitle.content.strip(),
        )
        for offset, subtitle in enumerate(subtitles)
        if subtitle.content.strip()
    ]


def _parse_with_pysrt(path: Path) -> list[SubtitleItem]:
    try:
        import pysrt
    except Exception:
        return []

    try:
        subtitles = pysrt.open(str(path), encoding="utf-8")
    except Exception:
        try:
            subtitles = pysrt.open(str(path), encoding="gb18030")
        except Exception as exc:
            logger.warning("pysrt 解析失败，使用备用解析器: {}", exc)
            return []

    return [
        SubtitleItem(
            index=subtitle.index,
            start_ms=subtitle.start.ordinal,
            end_ms=subtitle.end.ordinal,
            text=subtitle.text.strip(),
        )
        for subtitle in subtitles
        if subtitle.text.strip()
    ]


def _parse_srt_fallback(content: str) -> list[SubtitleItem]:
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").replace("\r", "\n").strip())
    items: list[SubtitleItem] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        time_line_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if time_line_index < 0:
            continue
        match = SRT_TIME_RE.search(lines[time_line_index])
        if not match:
            continue
        text = "\n".join(lines[time_line_index + 1 :]).strip()
        if not text:
            continue
        index_text = lines[0] if time_line_index > 0 else str(len(items) + 1)
        try:
            index = int(index_text)
        except ValueError:
            index = len(items) + 1
        items.append(
            SubtitleItem(
                index=index,
                start_ms=_parse_time_to_ms(match.group("start")),
                end_ms=_parse_time_to_ms(match.group("end")),
                text=text,
            )
        )
    return items

