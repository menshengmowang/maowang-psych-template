from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


APP_DISPLAY_NAME = "魔王心理学模板"
APP_DIR_NAME = "MaowangPsychTemplate"

DEFAULT_BAILIAN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_BAILIAN_MODEL = "qwen-plus"


def default_draft_dir() -> Path:
    return (
        Path.home()
        / "AppData"
        / "Local"
        / "JianyingPro"
        / "User Data"
        / "Projects"
        / "com.lveditor.draft"
    )


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / ".maowang_psych_template"


def log_dir() -> Path:
    return Path.cwd() / "logs"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def layout_settings_path() -> Path:
    return app_data_dir() / "config" / "layout_settings.json"


def cache_path() -> Path:
    return app_data_dir() / "match_cache.json"


@dataclass(slots=True)
class AppConfig:
    api_key: str = ""
    bailian_endpoint: str = DEFAULT_BAILIAN_ENDPOINT
    bailian_model: str = DEFAULT_BAILIAN_MODEL
    draft_dir: str = str(default_draft_dir())
    last_logo_path: str = ""
    last_background_path: str = ""
    last_divider_path: str = ""
    window_width: int = 1280
    window_height: int = 900
    title_text: str = "魔王心理学"
    hint_text: str = "看懂关系，也看懂自己"
    reference_draft_dir: str = ""
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
    illustration_fusion_mode: str = "original_darken"


LAYOUT_FIELD_NAMES = {
    "divider_center_x",
    "divider_center_y",
    "logo_x",
    "logo_y",
    "illustration_max_width",
    "illustration_max_height",
    "illustration_center_x",
    "illustration_center_y",
    "logo_max_size",
    "title_x",
    "title_y",
    "hint_x",
    "hint_y",
    "subtitle_center_x",
    "subtitle_center_y",
    "title_font_name",
    "title_font_size",
    "title_font_color",
    "title_bold",
    "title_italic",
    "title_align",
    "title_stroke_enabled",
    "title_stroke_color",
    "title_stroke_width",
    "title_shadow_enabled",
    "hint_font_name",
    "hint_font_size",
    "hint_font_color",
    "hint_bold",
    "hint_italic",
    "hint_align",
    "hint_stroke_enabled",
    "hint_stroke_color",
    "hint_stroke_width",
    "hint_shadow_enabled",
    "subtitle_font_name",
    "subtitle_font_size",
    "subtitle_font_color",
    "subtitle_bold",
    "subtitle_italic",
    "subtitle_align",
    "subtitle_stroke_enabled",
    "subtitle_stroke_color",
    "subtitle_stroke_width",
    "subtitle_shadow_enabled",
    "illustration_fusion_mode",
}


def load_config() -> AppConfig:
    path = config_path()
    data = {}
    try:
        if path.exists():
            data.update(json.loads(path.read_text(encoding="utf-8")))
        layout_path = layout_settings_path()
        if layout_path.exists():
            data.update(json.loads(layout_path.read_text(encoding="utf-8")))
        allowed = {field.name for field in AppConfig.__dataclass_fields__.values()}
        return AppConfig(**{key: value for key, value in data.items() if key in allowed})
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")

    layout_path = layout_settings_path()
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    config_data = asdict(config)
    layout_data = {key: config_data[key] for key in LAYOUT_FIELD_NAMES}
    layout_path.write_text(json.dumps(layout_data, ensure_ascii=False, indent=2), encoding="utf-8")
