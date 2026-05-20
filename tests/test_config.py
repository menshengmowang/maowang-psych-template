import json

from maowang_psych_template.config import AppConfig, layout_settings_path, load_config, save_config


def test_layout_settings_are_saved_and_reloaded(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = AppConfig(
        logo_x=123,
        logo_y=45,
        title_font_size=12.5,
        subtitle_shadow_enabled=True,
    )

    save_config(config)

    layout_path = layout_settings_path()
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    assert data["logo_x"] == 123
    assert data["title_font_size"] == 12.5
    assert data["subtitle_shadow_enabled"] is True

    loaded = load_config()
    assert loaded.logo_x == 123
    assert loaded.title_font_size == 12.5
    assert loaded.subtitle_shadow_enabled is True
