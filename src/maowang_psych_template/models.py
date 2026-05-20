from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class StoryboardRow:
    scene_id: str
    script: str
    summary: str
    flow_prompt_en: str
    flow_prompt_zh: str
    reference_suggestion: str
    retry_prompt: str
    note: str
    row_number: int


@dataclass(slots=True)
class SubtitleItem:
    index: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True)
class SceneMatch:
    storyboard: StoryboardRow
    subtitles: list[SubtitleItem]
    start_ms: int
    end_ms: int
    match_score: float
    selected_image: str | None = None
    processed_image_path: Path | None = None
    transition: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerationInputs:
    excel_path: Path
    srt_path: Path
    audio_path: Path
    image_dir: Path
    logo_path: Path
    draft_dir: Path
    background_path: Path | None = None
    divider_path: Path | None = None
    template_draft_dir: Path | None = None
    output_name: str = ""
    title_text: str = "魔王心理学"
    hint_text: str = "看懂关系，也看懂自己"
    reference_draft_dir: Path | None = None
    divider_center_x: int = 960
    divider_center_y: int = 810
    logo_x: int = 70
    logo_y: int = 45
    illustration_max_width: int = 850
    illustration_max_height: int = 560
    illustration_center_x: int = 960
    illustration_center_y: int = 440
    logo_max_size: int = 80
    title_x: int = 320
    title_y: int = 60
    hint_x: int = 1250
    hint_y: int = 65
    subtitle_center_x: int = 960
    subtitle_center_y: int = 940
    title_font_name: str = ""
    title_font_size: float = 8.5
    title_font_color: str = "#050505"
    title_bold: bool = True
    title_italic: bool = False
    title_align: int = 0
    title_stroke_enabled: bool = False
    title_stroke_color: str = "#000000"
    title_stroke_width: float = 40.0
    title_shadow_enabled: bool = False
    hint_font_name: str = ""
    hint_font_size: float = 5.5
    hint_font_color: str = "#1A1A1A"
    hint_bold: bool = False
    hint_italic: bool = False
    hint_align: int = 2
    hint_stroke_enabled: bool = False
    hint_stroke_color: str = "#000000"
    hint_stroke_width: float = 40.0
    hint_shadow_enabled: bool = False
    subtitle_font_name: str = ""
    subtitle_font_size: float = 5.8
    subtitle_font_color: str = "#000000"
    subtitle_bold: bool = False
    subtitle_italic: bool = False
    subtitle_align: int = 1
    subtitle_stroke_enabled: bool = False
    subtitle_stroke_color: str = "#FFFFFF"
    subtitle_stroke_width: float = 40.0
    subtitle_shadow_enabled: bool = False


def ms_to_seconds(ms: int) -> float:
    return round(ms / 1000, 3)


def format_ms(ms: int) -> str:
    total_seconds, milli = divmod(ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milli:03d}"
