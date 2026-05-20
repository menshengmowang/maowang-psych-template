from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from .bailian_client import BailianClient
from .config import AppConfig, cache_path
from .draft import DraftGenerationResult, JianyingDraftWriter
from .excel_reader import read_storyboard_excel
from .image_matcher import MatchCache, match_images_for_scenes
from .image_processor import remove_white_background
from .models import (
    GenerationInputs,
    ILLUSTRATION_BLEND_DARKEN,
    ILLUSTRATION_BLEND_NORMAL,
    ILLUSTRATION_MODE_DARKEN,
    ILLUSTRATION_MODE_ORIGINAL,
    ILLUSTRATION_MODE_REMOVE_WHITE,
)
from .srt_reader import read_srt
from .text_matcher import match_storyboard_to_subtitles


ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class MatchCheckResult:
    report_path: Path
    scenes: list


class GenerationPipeline:
    def __init__(self, config: AppConfig, progress: ProgressCallback | None = None) -> None:
        self.config = config
        self.progress = progress or (lambda message: None)

    def emit(self, message: str) -> None:
        logger.info(message)
        self.progress(message)

    def _match_scenes(self, inputs: GenerationInputs) -> list:
        self.emit("读取 Excel 分镜...")
        rows = read_storyboard_excel(inputs.excel_path)

        self.emit("解析 SRT 字幕...")
        subtitles = read_srt(inputs.srt_path)

        self.emit("匹配分镜时间段...")
        scenes = match_storyboard_to_subtitles(rows, subtitles)

        self.emit("根据英文提示词匹配图片文件名...")
        client = BailianClient(
            api_key=self.config.api_key,
            endpoint=self.config.bailian_endpoint,
            model=self.config.bailian_model,
        )
        cache = MatchCache(cache_path())
        scenes = match_images_for_scenes(scenes, inputs.image_dir, client, cache)
        return scenes

    def check_matches(self, inputs: GenerationInputs) -> MatchCheckResult:
        scenes = self._match_scenes(inputs)
        for scene in scenes:
            image = scene.selected_image or "未匹配"
            self.emit(f"分镜 {scene.storyboard.scene_id} -> 图片: {image}")
        report_path = self._write_match_report(inputs, scenes)
        self.emit(f"匹配报告已输出: {report_path}")
        return MatchCheckResult(report_path=report_path, scenes=scenes)

    def run(self, inputs: GenerationInputs) -> DraftGenerationResult:
        scenes = self._match_scenes(inputs)
        report_path = self._write_match_report(inputs, scenes)
        self.emit(f"匹配报告已输出: {report_path}")
        mode = inputs.illustration_fusion_mode
        self.emit(f"插图融合方式: {mode}")
        processed_dir = Path.cwd() / "processed_images"
        for scene in scenes:
            if not scene.selected_image:
                scene.warnings.append("未匹配到图片")
                continue
            source_path = inputs.image_dir / scene.selected_image
            use_original = True
            did_remove = False
            blend_set_ok = True
            blend_mode = ILLUSTRATION_BLEND_NORMAL
            if mode == ILLUSTRATION_MODE_REMOVE_WHITE:
                scene.processed_image_path = remove_white_background(source_path, processed_dir)
                use_original = False
                did_remove = True
            else:
                scene.processed_image_path = source_path
            if mode == ILLUSTRATION_MODE_DARKEN:
                blend_mode = ILLUSTRATION_BLEND_DARKEN
            scene.illustration_blend_mode = blend_mode
            scene.illustration_opacity = 1.0
            self.emit(
                f"插图 {scene.storyboard.scene_id}: 融合={mode}, 原图={use_original}, 去白底={did_remove}, "
                f"blend设置成功={blend_set_ok}, blend值={blend_mode}, opacity=100%"
            )

        self.emit("生成剪映原生草稿目录...")
        writer = JianyingDraftWriter()
        result = writer.generate(inputs, scenes)
        result.match_report_path = report_path

        self.emit(f"完成: {result.output_dir}")
        return result

    def _write_match_report(self, inputs: GenerationInputs, scenes: list) -> Path:
        report_dir = Path.cwd() / "match_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"match_report_{timestamp}.json"
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "excel_path": str(inputs.excel_path),
            "srt_path": str(inputs.srt_path),
            "image_dir": str(inputs.image_dir),
            "summary": {
                "scene_count": len(scenes),
                "matched_image_count": sum(1 for scene in scenes if scene.selected_image),
                "low_text_score_count": sum(1 for scene in scenes if scene.match_score < 0.55),
            },
            "scenes": [
                {
                    "scene_id": scene.storyboard.scene_id,
                    "row_number": scene.storyboard.row_number,
                    "script": scene.storyboard.script,
                    "flow_prompt_en": scene.storyboard.flow_prompt_en,
                    "start_ms": scene.start_ms,
                    "end_ms": scene.end_ms,
                    "match_score": scene.match_score,
                    "selected_image": scene.selected_image,
                    "illustration_fusion_mode": inputs.illustration_fusion_mode,
                    "illustration_blend_mode": scene.illustration_blend_mode,
                    "subtitle_indices": [subtitle.index for subtitle in scene.subtitles],
                    "subtitle_text": "\n".join(subtitle.text for subtitle in scene.subtitles),
                    "warnings": scene.warnings,
                }
                for scene in scenes
            ],
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("匹配报告已写入: {}", report_path)
        return report_path
