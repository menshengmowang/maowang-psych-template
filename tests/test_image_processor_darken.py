from pathlib import Path

from PIL import Image

from maowang_psych_template.image_processor import precompose_darken


def _save_rgb(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (1, 1), color).save(path)
    return path


def _read_rgb(path: Path) -> tuple[int, int, int]:
    return Image.open(path).convert("RGB").getpixel((0, 0))


def test_precompose_white_pixel_becomes_background(tmp_path):
    src = _save_rgb(tmp_path / "white.png", (255, 255, 255))
    out = precompose_darken(src, tmp_path, "#F4F4F4")
    assert _read_rgb(out) == (244, 244, 244)


def test_precompose_black_pixel_stays_black(tmp_path):
    src = _save_rgb(tmp_path / "black.png", (0, 0, 0))
    out = precompose_darken(src, tmp_path, "#F4F4F4")
    assert _read_rgb(out) == (0, 0, 0)


def test_precompose_red_pixel_uses_channel_wise_min(tmp_path):
    src = _save_rgb(tmp_path / "red.png", (255, 10, 20))
    out = precompose_darken(src, tmp_path, "#F4F4F4")
    assert _read_rgb(out) == (244, 10, 20)
