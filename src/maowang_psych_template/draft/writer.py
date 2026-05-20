from __future__ import annotations

import importlib
import importlib.util
import json
import random
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
import numpy as np
from PIL import Image

from ..models import GenerationInputs, SceneMatch, SubtitleItem


VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
DEFAULT_BACKGROUND_COLOR = "#F4F4F4"
SAFE_TRANSITION_NAMES = ["叠化", "模糊", "推近", "拉远"]
CLAMP_TOLERANCE_US = 1_000_000
ILLUSTRATION_AREA = (240, 130, 1680, 760)


@dataclass(slots=True)
class DraftGenerationResult:
    output_dir: Path
    draft_content_path: Path
    draft_meta_info_path: Path
    match_report_path: Path | None = None
    manifest_path: Path | None = None
    notes_path: Path | None = None


class JianyingDraftWriter:
    """Native Jianying draft writer migrated from `jianying-auto-draft`.

    The old working project uses pyJianYingDraft's `DraftFolder.create_draft()`
    and `ScriptFile.save()` path. This writer follows the same mechanism so
    Jianying Pro can recognize the generated folder from its draft homepage.
    """

    def generate(self, inputs: GenerationInputs, scenes: list[SceneMatch]) -> DraftGenerationResult:
        logger.info("使用的是 jianying-auto-draft 迁移来的写入器: pyJianYingDraft")
        draft = _load_pyjianyingdraft()

        draft_root = inputs.draft_dir.expanduser().resolve()
        if not draft_root.exists():
            raise FileNotFoundError(f"剪映草稿目录不存在: {draft_root}")
        if not draft_root.is_dir():
            raise NotADirectoryError(f"剪映草稿路径不是文件夹: {draft_root}")

        project_name = _unique_project_name(draft_root, inputs.output_name)
        draft_folder = draft.DraftFolder(str(draft_root))
        script = draft_folder.create_draft(project_name, VIDEO_WIDTH, VIDEO_HEIGHT, allow_replace=False)
        output_dir = Path(script.save_path).parent.resolve()
        logger.info("草稿目录已写入剪映草稿路径: {}", output_dir)

        timing = _calculate_timing_plan(inputs.audio_path, scenes)
        logger.info("srt_total_duration_us: {}", timing.srt_total_duration_us)
        logger.info("audio_duration_us: {}", timing.audio_duration_us)
        logger.info("final_project_duration_us: {}", timing.final_project_duration_us)
        logger.info(
            "是否发生 clamp: {}",
            "是" if timing.clamped_to_audio or timing.clamped_segments else "否",
        )
        if timing.final_project_duration_us <= 0:
            raise ValueError("时间线时长为 0，无法生成剪映草稿")

        assets = _prepare_assets(inputs, scenes, output_dir, timing.final_project_duration_us)
        _load_reference_text_style_interface(inputs.reference_draft_dir or inputs.template_draft_dir)
        _build_tracks(draft, script, inputs, scenes, assets, timing)
        script.save()
        _patch_illustration_blend_modes(output_dir / "draft_content.json", scenes)
        _patch_meta_info(output_dir / "draft_meta_info.json", project_name, draft_root, output_dir)

        draft_content_path = output_dir / "draft_content.json"
        draft_meta_info_path = output_dir / "draft_meta_info.json"
        content_ok = draft_content_path.exists() and draft_content_path.stat().st_size > 0
        meta_ok = draft_meta_info_path.exists() and draft_meta_info_path.stat().st_size > 0
        logger.info("draft_content.json 是否生成成功: {}", "是" if content_ok else "否")
        logger.info("draft_meta_info.json 是否生成成功: {}", "是" if meta_ok else "否")
        logger.info(
            "剪映首页是否应能识别该草稿: {}",
            "是" if content_ok and meta_ok and output_dir.parent.resolve() == draft_root else "否",
        )
        if not content_ok or not meta_ok:
            raise RuntimeError("剪映草稿核心文件生成失败")

        logger.info("剪映原生草稿生成完成: {}", output_dir)
        return DraftGenerationResult(
            output_dir=output_dir,
            draft_content_path=draft_content_path,
            draft_meta_info_path=draft_meta_info_path,
        )


@dataclass(slots=True)
class PreparedAssets:
    audio: Path
    srt: Path
    background: Path
    logo: Path
    divider: Path
    scene_images: dict[str, Path]


@dataclass(slots=True)
class TimingPlan:
    srt_total_duration_us: int
    audio_duration_us: int | None
    final_project_duration_us: int
    clamped_to_audio: bool
    clamped_segments: bool


@dataclass(slots=True)
class VisualFit:
    original_width: int
    original_height: int
    content_bbox: tuple[int, int, int, int]
    display_width: float
    display_height: float
    scale: float
    content_center_x: float
    content_center_y: float
    material_center_x: float
    material_center_y: float
    transform_x: float
    transform_y: float


def _load_pyjianyingdraft() -> Any:
    if importlib.util.find_spec("pyJianYingDraft") is None:
        raise RuntimeError("缺少 pyJianYingDraft，请先执行: pip install pyJianYingDraft")
    return importlib.import_module("pyJianYingDraft")


def _build_tracks(
    draft: Any,
    script: Any,
    inputs: GenerationInputs,
    scenes: list[SceneMatch],
    assets: PreparedAssets,
    timing: TimingPlan,
) -> None:
    trange = draft.trange

    script.add_track(draft.TrackType.video, "background", absolute_index=0)
    script.add_track(draft.TrackType.video, "illustrations", absolute_index=10)
    script.add_track(draft.TrackType.video, "divider", absolute_index=20)
    script.add_track(draft.TrackType.video, "logo", absolute_index=30)
    script.add_track(draft.TrackType.audio, "voiceover")
    script.add_track(draft.TrackType.text, "title", absolute_index=15100)
    script.add_track(draft.TrackType.text, "hint", absolute_index=15110)
    script.add_track(draft.TrackType.text, "subtitle", absolute_index=15200)

    final_project_duration_us = timing.final_project_duration_us
    full_range = trange("0s", _pyjd_time(final_project_duration_us))
    script.add_segment(draft.VideoSegment(str(assets.background), full_range), "background")

    audio_material = draft.AudioMaterial(str(assets.audio))
    audio_clip_us = min(final_project_duration_us, audio_material.duration)
    logger.info(
        "配音轨道写入时长 audio_clip_us: {}，音频素材真实时长: {}",
        audio_clip_us,
        audio_material.duration,
    )
    script.add_segment(
        draft.AudioSegment(audio_material, trange("0s", _pyjd_time(audio_clip_us))),
        "voiceover",
    )

    logo_settings = _visual_clip_settings_for_box(
        assets.logo,
        inputs.logo_x,
        inputs.logo_y,
        inputs.logo_max_size,
        inputs.logo_max_size,
        "Logo",
    )
    script.add_segment(draft.VideoSegment(str(assets.logo), full_range, clip_settings=logo_settings), "logo")

    divider_settings = _divider_clip_settings(assets.divider, inputs.divider_center_x, inputs.divider_center_y)
    try:
        script.add_segment(draft.VideoSegment(str(assets.divider), full_range, clip_settings=divider_settings), "divider")
        logger.info("分割线图层是否成功写入草稿: 是")
    except Exception:
        logger.exception("分割线图层是否成功写入草稿: 否")
        raise

    title_segment = draft.TextSegment(
        inputs.title_text,
        full_range,
        font=_resolve_font_type(draft, inputs.title_font_name),
        style=_text_style(draft, inputs, "title"),
        clip_settings=_text_clip_settings(inputs.title_x, inputs.title_y, 650, 70),
        border=_text_border(draft, inputs, "title"),
        shadow=_text_shadow(draft, inputs, "title"),
    )
    hint_segment = draft.TextSegment(
        inputs.hint_text,
        full_range,
        font=_resolve_font_type(draft, inputs.hint_font_name),
        style=_text_style(draft, inputs, "hint"),
        clip_settings=_text_clip_settings(inputs.hint_x, inputs.hint_y, 620, 65),
        border=_text_border(draft, inputs, "hint"),
        shadow=_text_shadow(draft, inputs, "hint"),
    )
    script.add_segment(title_segment, "title")
    script.add_segment(hint_segment, "hint")
    _log_text_layout("标题", inputs, "title", inputs.title_x, inputs.title_y)
    _log_text_layout("提示文字", inputs, "hint", inputs.hint_x, inputs.hint_y)

    illustration_segments: list[Any] = []
    for scene in scenes:
        image_path = assets.scene_images.get(scene.storyboard.scene_id)
        if image_path is None:
            logger.warning("分镜 {} 没有可写入的插图，已跳过", scene.storyboard.scene_id)
            continue
        start_us = min(scene.start_ms * 1000, final_project_duration_us)
        end_us = min(scene.end_ms * 1000, final_project_duration_us)
        if end_us <= start_us:
            logger.warning("分镜 {} 超出最终项目时长，已跳过", scene.storyboard.scene_id)
            continue
        duration_us = end_us - start_us
        segment = draft.VideoSegment(
            str(image_path),
            trange(_pyjd_time(start_us), _pyjd_time(duration_us)),
            clip_settings=_visual_clip_settings(
                image_path,
                inputs.illustration_max_width,
                inputs.illustration_max_height,
                inputs.illustration_center_x,
                inputs.illustration_center_y,
                f"分镜 {scene.storyboard.scene_id} 插图",
                clamp_area=ILLUSTRATION_AREA,
            ),
        )
        _configure_segment_blend_mode(segment, scene.illustration_blend_mode, scene.illustration_opacity)
        illustration_segments.append(segment)

    _apply_safe_transitions(draft, illustration_segments)
    for segment in illustration_segments:
        script.add_segment(segment, "illustrations")
    _log_illustration_blend_summary(scenes)

    _add_subtitle_segments(draft, script, inputs, scenes, final_project_duration_us)


def _prepare_assets(
    inputs: GenerationInputs,
    scenes: list[SceneMatch],
    output_dir: Path,
    total_duration_us: int,
) -> PreparedAssets:
    asset_dir = output_dir / "maowang_assets"
    audio = _copy_asset(inputs.audio_path, asset_dir / "audio")
    logo = _copy_asset(inputs.logo_path, asset_dir / "logo")

    background_dir = asset_dir / "background"
    background_dir.mkdir(parents=True, exist_ok=True)
    background = background_dir / "background_1920x1080.png"
    _render_background(inputs.background_path, background)

    divider_dir = asset_dir / "divider"
    divider_dir.mkdir(parents=True, exist_ok=True)
    if inputs.divider_path is None:
        raise ValueError("请上传黑色分割线图片")
    divider = divider_dir / "divider_1920w.png"
    _render_divider(inputs.divider_path, divider)

    subtitle_dir = asset_dir / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    srt = subtitle_dir / "subtitles_utf8.srt"
    _write_normalized_srt(scenes, srt)

    image_dir = asset_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    scene_images: dict[str, Path] = {}
    for scene in scenes:
        if scene.processed_image_path is None:
            continue
        scene_images[scene.storyboard.scene_id] = _copy_asset(scene.processed_image_path, image_dir)

    logger.info("素材导入到剪映草稿目录完成: {}", asset_dir)
    return PreparedAssets(
        audio=audio,
        srt=srt,
        background=background,
        logo=logo,
        divider=divider,
        scene_images=scene_images,
    )


def _render_background(source: Path | None, target: Path) -> None:
    canvas = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), DEFAULT_BACKGROUND_COLOR)
    if source:
        with Image.open(source).convert("RGB") as image:
            image.thumbnail((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.LANCZOS)
            x = (VIDEO_WIDTH - image.width) // 2
            y = (VIDEO_HEIGHT - image.height) // 2
            canvas.paste(image, (x, y))
    canvas.save(target)
    logger.info("背景层素材生成成功: {}", target)


def _render_divider(source: Path, target: Path) -> None:
    with Image.open(source).convert("RGBA") as image:
        resized = image.resize((VIDEO_WIDTH, image.height), Image.Resampling.LANCZOS)
        resized.save(target)
    logger.info("分割线素材生成成功: path={}, width={}, height={}, source={}", target, VIDEO_WIDTH, resized.height, source)


def _write_normalized_srt(scenes: list[SceneMatch], target: Path) -> None:
    lines: list[str] = []
    index = 1
    final_ms = _current_srt_final_ms(scenes)
    for scene in scenes:
        for subtitle in scene.subtitles:
            start_ms = min(subtitle.start_ms, final_ms)
            end_ms = min(subtitle.end_ms, final_ms)
            if end_ms <= start_ms:
                continue
            lines.extend(
                [
                    str(index),
                    f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}",
                    subtitle.text.strip(),
                    "",
                ]
            )
            index += 1
    target.write_text("\n".join(lines), encoding="utf-8-sig")
    logger.info("中文字幕 SRT 已写入剪映草稿素材: {}", target)


def _apply_safe_transitions(draft: Any, segments: list[Any]) -> None:
    transition_type = getattr(draft, "TransitionType", None)
    if transition_type is None:
        logger.warning("当前 pyJianYingDraft 不支持 TransitionType，跳过插图转场")
        return

    available = [getattr(transition_type, name, None) for name in SAFE_TRANSITION_NAMES]
    available = [item for item in available if item is not None]
    if not available:
        logger.warning("未找到安全转场枚举，跳过插图转场")
        return

    for segment in segments[:-1]:
        duration_us = min(350_000, max(120_000, segment.target_timerange.duration // 5))
        transition = random.choice(available)
        try:
            segment.add_transition(transition, duration=duration_us)
            logger.info("已添加安全转场: {}", transition.name)
        except Exception as exc:
            logger.warning("添加转场失败，已跳过: {}", exc)


def _patch_meta_info(meta_path: Path, project_name: str, draft_root: Path, output_dir: Path) -> None:
    if not meta_path.exists():
        logger.warning("draft_meta_info.json 不存在，无法补充首页识别字段: {}", meta_path)
        return
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("draft_meta_info.json 读取失败，保留 pyJianYingDraft 原始输出: {}", exc)
        return

    now_ms = int(datetime.now().timestamp() * 1000)
    data["draft_name"] = project_name
    data["draft_fold_path"] = str(output_dir)
    data["draft_root_path"] = str(draft_root)
    data["draft_id"] = str(uuid.uuid4()).upper()
    data["tm_draft_modified"] = now_ms
    data["tm_draft_create"] = data.get("tm_draft_create") or now_ms
    data["draft_is_invisible"] = False
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已补充剪映首页识别字段: draft_name={}, draft_id={}", project_name, data["draft_id"])


def _load_reference_text_style_interface(reference_draft_dir: Path | None) -> None:
    if reference_draft_dir is None:
        return
    logger.info(
        "参考草稿文字样式复用接口已预留: {}。当前版本先使用 GUI 字体样式，后续可从参考草稿复制花字/描边/阴影。",
        reference_draft_dir,
    )


def _configure_segment_blend_mode(segment: Any, blend_mode: str, opacity: float) -> bool:
    ok = False
    for key, value in (("blend_mode", blend_mode), ("source_blend_mode", blend_mode), ("opacity", opacity)):
        try:
            setattr(segment, key, value)
            ok = True
        except Exception:
            continue
    return ok


def _patch_illustration_blend_modes(content_path: Path, scenes: list[SceneMatch]) -> None:
    if not content_path.exists():
        return
    try:
        data = json.loads(content_path.read_text(encoding="utf-8"))
        mode_by_name = {scene.selected_image: scene.illustration_blend_mode for scene in scenes if scene.selected_image}
        patched = 0
        for track in data.get("tracks", []):
            for seg in track.get("segments", []):
                path = str(seg.get("material", "") or seg.get("path", ""))
                filename = Path(path).name if path else ""
                mode = mode_by_name.get(filename)
                if not mode:
                    continue
                seg["blend_mode"] = mode
                seg["source_blend_mode"] = mode
                seg["opacity"] = 1.0
                patched += 1
        content_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("插图混合模式 JSON patch 完成，patched={}", patched)
    except Exception:
        logger.exception("插图混合模式 JSON patch 失败")


def _log_illustration_blend_summary(scenes: list[SceneMatch]) -> None:
    for scene in scenes:
        if not scene.selected_image:
            continue
        logger.info(
            "分镜 {} 插图融合结果: file={}, blend={}, opacity={}",
            scene.storyboard.scene_id,
            scene.selected_image,
            scene.illustration_blend_mode,
            scene.illustration_opacity,
        )


def _add_subtitle_segments(
    draft: Any,
    script: Any,
    inputs: GenerationInputs,
    scenes: list[SceneMatch],
    final_project_duration_us: int,
) -> None:
    trange = draft.trange
    style = _text_style(draft, inputs, "subtitle", auto_wrapping=True, max_line_width=0.82)
    border = _text_border(draft, inputs, "subtitle")
    shadow = _text_shadow(draft, inputs, "subtitle")
    font = _resolve_font_type(draft, inputs.subtitle_font_name)
    clip_settings = _center_clip_settings(draft, inputs.subtitle_center_x, inputs.subtitle_center_y)

    count = 0
    for scene in scenes:
        for subtitle in scene.subtitles:
            start_us = min(subtitle.start_ms * 1000, final_project_duration_us)
            end_us = min(subtitle.end_ms * 1000, final_project_duration_us)
            if end_us <= start_us:
                continue
            segment = draft.TextSegment(
                subtitle.text,
                trange(_pyjd_time(start_us), _pyjd_time(end_us - start_us)),
                font=font,
                style=style,
                clip_settings=clip_settings,
                border=border,
                shadow=shadow,
            )
            script.add_segment(segment, "subtitle")
            count += 1

    _log_text_layout("字幕", inputs, "subtitle", inputs.subtitle_center_x, inputs.subtitle_center_y)
    logger.info("中文字幕轨道写入完成: {} 条", count)


def _divider_clip_settings(path: Path, center_x: int, center_y: int) -> Any:
    draft = _load_pyjianyingdraft()
    with Image.open(path) as image:
        width, height = image.size
        sample_color = _sample_image_color(image)

    scale_x = VIDEO_WIDTH / width if width > 0 else 1.0
    scale_y = 1.0
    top_y = center_y - height * scale_y / 2
    logger.info(
        "分割线最终写入参数: path={}, width={}, height={}, color={}, center=({:.1f}, {:.1f}), top_y={:.1f}, scale_x={:.6f}, scale_y={:.6f}",
        path,
        VIDEO_WIDTH,
        height,
        sample_color,
        center_x,
        center_y,
        top_y,
        scale_x,
        scale_y,
    )
    return draft.ClipSettings(
        scale_x=scale_x,
        scale_y=scale_y,
        transform_x=_pixel_to_transform_x(center_x),
        transform_y=_pixel_to_transform_y(center_y),
    )


def _sample_image_color(image: Image.Image) -> str:
    if image.width <= 0 or image.height <= 0:
        return "未知"
    rgba = image.convert("RGBA").getpixel((image.width // 2, image.height // 2))
    return f"#{rgba[0]:02X}{rgba[1]:02X}{rgba[2]:02X} alpha={rgba[3]}"


def _center_clip_settings(draft: Any, center_x: float, center_y: float) -> Any:
    return draft.ClipSettings(
        transform_x=_pixel_to_transform_x(center_x),
        transform_y=_pixel_to_transform_y(center_y),
    )


def _text_style(
    draft: Any,
    inputs: GenerationInputs,
    prefix: str,
    *,
    auto_wrapping: bool = False,
    max_line_width: float = 0.82,
) -> Any:
    return draft.TextStyle(
        size=float(getattr(inputs, f"{prefix}_font_size")),
        bold=bool(getattr(inputs, f"{prefix}_bold")),
        italic=bool(getattr(inputs, f"{prefix}_italic")),
        color=_hex_to_rgb_tuple(str(getattr(inputs, f"{prefix}_font_color"))),
        align=_normalize_align(int(getattr(inputs, f"{prefix}_align"))),
        auto_wrapping=auto_wrapping,
        max_line_width=max_line_width,
    )


def _text_border(draft: Any, inputs: GenerationInputs, prefix: str) -> Any | None:
    if not bool(getattr(inputs, f"{prefix}_stroke_enabled")):
        return None
    return draft.TextBorder(
        color=_hex_to_rgb_tuple(str(getattr(inputs, f"{prefix}_stroke_color"))),
        width=float(getattr(inputs, f"{prefix}_stroke_width")),
    )


def _text_shadow(draft: Any, inputs: GenerationInputs, prefix: str) -> Any | None:
    if not bool(getattr(inputs, f"{prefix}_shadow_enabled")):
        return None
    return draft.TextShadow(alpha=0.65, color=(0.0, 0.0, 0.0), diffuse=18.0, distance=4.0, angle=-45.0)


def _resolve_font_type(draft: Any, font_name: str) -> Any | None:
    font_name = font_name.strip()
    if not font_name:
        return None
    normalized = _normalize_font_text(font_name)
    for font_type in getattr(draft, "FontType", []):
        enum_name = _normalize_font_text(getattr(font_type, "name", ""))
        effect_name = _normalize_font_text(getattr(getattr(font_type, "value", None), "name", ""))
        if normalized in {enum_name, effect_name}:
            return font_type
    logger.warning("未找到剪映字体资源 '{}'，将使用剪映默认字体", font_name)
    return None


def _normalize_font_text(value: str) -> str:
    return value.replace("_", "").replace("-", "").replace(" ", "").lower()


def _hex_to_rgb_tuple(value: str) -> tuple[float, float, float]:
    value = value.strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        logger.warning("颜色值无效: {}，已使用黑色", value)
        value = "#000000"
    red = int(value[1:3], 16) / 255
    green = int(value[3:5], 16) / 255
    blue = int(value[5:7], 16) / 255
    return (red, green, blue)


def _normalize_align(value: int) -> int:
    return value if value in {0, 1, 2} else 1


def _log_text_layout(label: str, inputs: GenerationInputs, prefix: str, x: int, y: int) -> None:
    font_name = str(getattr(inputs, f"{prefix}_font_name")).strip() or "剪映默认"
    font_size = float(getattr(inputs, f"{prefix}_font_size"))
    logger.info("{}最终位置: x={}, y={}, 字体={}, 字号={}", label, x, y, font_name, font_size)


def _visual_clip_settings(
    path: Path,
    max_width: int,
    max_height: int,
    center_x: float,
    center_y: float,
    label: str,
    clamp_area: tuple[int, int, int, int] | None = None,
) -> Any:
    draft = _load_pyjianyingdraft()
    fit = calculate_visual_fit(path, max_width, max_height, center_x, center_y, clamp_area=clamp_area)
    _log_visual_fit(label, fit)
    return draft.ClipSettings(
        scale_x=fit.scale,
        scale_y=fit.scale,
        transform_x=fit.transform_x,
        transform_y=fit.transform_y,
    )


def _visual_clip_settings_for_box(
    path: Path,
    x: int,
    y: int,
    max_width: int,
    max_height: int,
    label: str,
) -> Any:
    center_x = x + max_width / 2
    center_y = y + max_height / 2
    return _visual_clip_settings(path, max_width, max_height, center_x, center_y, label)


def calculate_visual_fit(
    path: Path,
    max_width: int,
    max_height: int,
    center_x: float,
    center_y: float,
    clamp_area: tuple[int, int, int, int] | None = None,
) -> VisualFit:
    """Calculate pyJianYingDraft scale/transform from visible content bounds."""
    with Image.open(path) as image:
        image = image.convert("RGBA")
        original_width, original_height = image.size
        content_bbox = _effective_content_bbox(image)

    area_width: int | None = None
    area_height: int | None = None
    if clamp_area is not None:
        x_min, y_min, x_max, y_max = clamp_area
        area_width = max(1, x_max - x_min)
        area_height = max(1, y_max - y_min)

    fit_max_width = max(1, int(max_width or 1))
    fit_max_height = max(1, int(max_height or 1))
    if area_width is not None and area_height is not None:
        fit_max_width = min(fit_max_width, area_width)
        fit_max_height = min(fit_max_height, area_height)

    left, top, right, bottom = content_bbox
    content_width = max(1, right - left)
    content_height = max(1, bottom - top)
    scale = min(fit_max_width / content_width, fit_max_height / content_height)
    display_width = content_width * scale
    display_height = content_height * scale

    content_center_x = float(center_x)
    content_center_y = float(center_y)
    if clamp_area is not None:
        content_center_x, content_center_y = _clamp_visual_center(
            content_center_x,
            content_center_y,
            display_width,
            display_height,
            clamp_area,
        )

    source_content_center_x = (left + right) / 2
    source_content_center_y = (top + bottom) / 2
    material_center_x = content_center_x - (source_content_center_x - original_width / 2) * scale
    material_center_y = content_center_y - (source_content_center_y - original_height / 2) * scale

    return VisualFit(
        original_width=original_width,
        original_height=original_height,
        content_bbox=content_bbox,
        display_width=display_width,
        display_height=display_height,
        scale=scale,
        content_center_x=content_center_x,
        content_center_y=content_center_y,
        material_center_x=material_center_x,
        material_center_y=material_center_y,
        transform_x=_pixel_to_transform_x(material_center_x),
        transform_y=_pixel_to_transform_y(material_center_y),
    )


def _effective_content_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    arr = np.asarray(image.convert("RGBA"))
    height, width = arr.shape[:2]
    alpha = arr[:, :, 3]

    if np.any(alpha < 250):
        bbox = _bbox_from_mask(alpha > 10)
        if bbox is not None:
            return bbox

    rgb = arr[:, :, :3]
    visible = alpha > 10
    non_white = visible & np.any(rgb < 245, axis=2)
    bbox = _bbox_from_mask(non_white)
    if bbox is not None:
        return bbox

    return (0, 0, width, height)


def _bbox_from_mask(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _clamp_visual_center(
    center_x: float,
    center_y: float,
    display_width: float,
    display_height: float,
    area: tuple[int, int, int, int],
) -> tuple[float, float]:
    x_min, y_min, x_max, y_max = area
    min_center_x = x_min + display_width / 2
    max_center_x = x_max - display_width / 2
    min_center_y = y_min + display_height / 2
    max_center_y = y_max - display_height / 2

    if min_center_x <= max_center_x:
        center_x = min(max(center_x, min_center_x), max_center_x)
    else:
        center_x = (x_min + x_max) / 2

    if min_center_y <= max_center_y:
        center_y = min(max(center_y, min_center_y), max_center_y)
    else:
        center_y = (y_min + y_max) / 2

    return center_x, center_y


def _log_visual_fit(label: str, fit: VisualFit) -> None:
    logger.info(
        "{}最终位置和大小: 原始尺寸={}x{}, 有效内容bbox={}, 最终显示={:.1f}x{:.1f}, 最终 scale={:.6f}, 最终位置=({:.1f}, {:.1f})",
        label,
        fit.original_width,
        fit.original_height,
        fit.content_bbox,
        fit.display_width,
        fit.display_height,
        fit.scale,
        fit.content_center_x,
        fit.content_center_y,
    )


def _text_clip_settings(x: int, y: int, width: int, height: int) -> Any:
    draft = _load_pyjianyingdraft()
    return draft.ClipSettings(
        transform_x=_pixel_to_transform_x(x + width / 2),
        transform_y=_pixel_to_transform_y(y + height / 2),
    )


def _pixel_to_transform_x(center_x: float) -> float:
    return (center_x - VIDEO_WIDTH / 2) / (VIDEO_WIDTH / 2)


def _pixel_to_transform_y(center_y: float) -> float:
    return -((center_y - VIDEO_HEIGHT / 2) / (VIDEO_HEIGHT / 2))


def _copy_asset(path: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.resolve() != path.resolve():
        shutil.copy2(path, target)
    logger.info("素材导入: {} -> {}", path, target)
    return target


def _safe_project_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value.strip())
    return cleaned or datetime.now().strftime("魔王心理学模板_%Y%m%d_%H%M%S")


def _unique_project_name(draft_root: Path, requested: str) -> str:
    base = _safe_project_name(requested)
    candidate = base
    counter = 1
    while (draft_root / candidate).exists():
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def _format_srt_time(ms: int) -> str:
    total_seconds, milli = divmod(ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milli:03d}"


def _pyjd_time(us: int) -> str:
    return f"{us / 1_000_000:.6f}s"


def _get_audio_duration_us(audio_path: Path) -> int | None:
    pyjd_duration = _get_audio_duration_us_from_pyjd(audio_path)
    if pyjd_duration is not None:
        return pyjd_duration
    if importlib.util.find_spec("mutagen") is None:
        logger.warning("未安装 mutagen，配音轨道时长将使用时间线总时长")
        return None
    try:
        mutagen = importlib.import_module("mutagen")
        audio = mutagen.File(str(audio_path))
        length = getattr(getattr(audio, "info", None), "length", None) if audio is not None else None
        if length:
            duration = int(round(float(length) * 1_000_000))
            logger.info("读取配音时长成功: {} us", duration)
            return duration
    except Exception as exc:
        logger.warning("读取配音时长失败，将使用时间线总时长: {}", exc)
    return None


def _get_audio_duration_us_from_pyjd(audio_path: Path) -> int | None:
    try:
        draft = _load_pyjianyingdraft()
        material = draft.AudioMaterial(str(audio_path))
        logger.info("pyJianYingDraft 读取配音真实时长成功: {} us", material.duration)
        return int(material.duration)
    except Exception as exc:
        logger.warning("pyJianYingDraft 读取配音时长失败，尝试 mutagen: {}", exc)
        return None


def _calculate_timing_plan(audio_path: Path, scenes: list[SceneMatch]) -> TimingPlan:
    srt_total_duration_us = max(
        [
            *(scene.end_ms * 1000 for scene in scenes),
            *(subtitle.end_ms * 1000 for scene in scenes for subtitle in scene.subtitles),
            0,
        ]
    )
    audio_duration_us = _get_audio_duration_us(audio_path)
    clamped_to_audio = False

    if audio_duration_us is None:
        final_project_duration_us = srt_total_duration_us
    elif srt_total_duration_us <= audio_duration_us:
        final_project_duration_us = audio_duration_us
    else:
        overshoot_us = srt_total_duration_us - audio_duration_us
        if overshoot_us < CLAMP_TOLERANCE_US:
            final_project_duration_us = audio_duration_us
            clamped_to_audio = True
            logger.warning(
                "SRT/分镜总时长比音频长 {} us，小于 1 秒，已自动 clamp 到音频时长",
                overshoot_us,
            )
        else:
            final_project_duration_us = srt_total_duration_us
            logger.warning(
                "SRT/分镜总时长比音频长 {} us，超过 1 秒，项目时长保留到 SRT/分镜结束，配音轨道按音频真实时长截断",
                overshoot_us,
            )

    clamped_segments = _clamp_scenes_to_duration(scenes, final_project_duration_us)
    return TimingPlan(
        srt_total_duration_us=srt_total_duration_us,
        audio_duration_us=audio_duration_us,
        final_project_duration_us=final_project_duration_us,
        clamped_to_audio=clamped_to_audio,
        clamped_segments=clamped_segments,
    )


def _clamp_scenes_to_duration(scenes: list[SceneMatch], final_project_duration_us: int) -> bool:
    final_ms = final_project_duration_us // 1000
    clamped = False
    for scene in scenes:
        if scene.start_ms > final_ms:
            scene.start_ms = final_ms
            clamped = True
        if scene.end_ms > final_ms:
            scene.end_ms = final_ms
            clamped = True

        new_subtitles: list[SubtitleItem] = []
        for subtitle in scene.subtitles:
            start_ms = min(subtitle.start_ms, final_ms)
            end_ms = min(subtitle.end_ms, final_ms)
            if start_ms != subtitle.start_ms or end_ms != subtitle.end_ms:
                clamped = True
            if end_ms > start_ms:
                new_subtitles.append(
                    SubtitleItem(
                        index=subtitle.index,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=subtitle.text,
                    )
                )
        scene.subtitles = new_subtitles
    return clamped


def _current_srt_final_ms(scenes: list[SceneMatch]) -> int:
    return max(
        [
            *(scene.end_ms for scene in scenes),
            *(subtitle.end_ms for scene in scenes for subtitle in scene.subtitles),
            0,
        ]
    )
