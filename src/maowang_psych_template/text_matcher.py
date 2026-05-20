from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from loguru import logger

from .models import SceneMatch, StoryboardRow, SubtitleItem


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value)


def _score(accumulated: str, target: str) -> float:
    if not target and not accumulated:
        return 1.0
    if not target or not accumulated:
        return 0.0
    ratio = SequenceMatcher(None, accumulated, target).ratio()
    if target in accumulated or accumulated in target:
        ratio = max(ratio, 0.95)
    length_penalty = abs(len(accumulated) - len(target)) / max(len(accumulated), len(target), 1)
    return max(0.0, ratio - length_penalty * 0.18)


def match_storyboard_to_subtitles(
    storyboard_rows: list[StoryboardRow],
    subtitles: list[SubtitleItem],
) -> list[SceneMatch]:
    logger.info("开始按顺序匹配 Excel 文案和 SRT 字幕")
    if not subtitles:
        raise ValueError("没有可匹配的字幕")

    scenes: list[SceneMatch] = []
    cursor = 0
    for row_index, row in enumerate(storyboard_rows):
        if cursor >= len(subtitles):
            logger.warning("分镜 {} 没有剩余字幕可匹配", row.scene_id)
            scenes.append(
                SceneMatch(
                    storyboard=row,
                    subtitles=[],
                    start_ms=0,
                    end_ms=0,
                    match_score=0,
                    warnings=["没有剩余字幕可匹配"],
                )
            )
            continue

        target = normalize_text(row.script)
        if not target:
            subtitle = subtitles[cursor]
            scenes.append(
                SceneMatch(
                    storyboard=row,
                    subtitles=[subtitle],
                    start_ms=subtitle.start_ms,
                    end_ms=subtitle.end_ms,
                    match_score=0,
                    warnings=["分镜对应文案为空，默认匹配一条字幕"],
                )
            )
            cursor += 1
            continue

        remaining_scenes = len(storyboard_rows) - row_index
        max_end = len(subtitles) - max(0, remaining_scenes - 1)
        best_end = cursor
        best_score = -1.0
        accumulated = ""

        for end in range(cursor, max_end):
            accumulated += normalize_text(subtitles[end].text)
            score = _score(accumulated, target)
            if score > best_score:
                best_score = score
                best_end = end

            if len(accumulated) >= len(target) * 0.92 and score >= 0.86:
                break
            if len(accumulated) > len(target) * 1.45 and best_score >= 0.62:
                break

        matched = subtitles[cursor : best_end + 1]
        scene = SceneMatch(
            storyboard=row,
            subtitles=matched,
            start_ms=matched[0].start_ms,
            end_ms=matched[-1].end_ms,
            match_score=round(best_score, 3),
        )
        if best_score < 0.55:
            warning = f"字幕匹配相似度偏低: {best_score:.2f}"
            scene.warnings.append(warning)
            logger.warning("分镜 {} {}", row.scene_id, warning)
        scenes.append(scene)
        cursor = best_end + 1

    logger.info("字幕匹配完成: {} 个分镜", len(scenes))
    return scenes

