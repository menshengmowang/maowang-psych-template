from pathlib import Path

import pytest
from PIL import Image

from maowang_psych_template.draft.writer import ILLUSTRATION_AREA, calculate_visual_fit


def _save_image(path: Path, size: tuple[int, int], color: tuple[int, int, int, int] = (20, 20, 20, 255)) -> Path:
    Image.new("RGBA", size, color).save(path)
    return path


def test_large_1920x1080_image_fits_illustration_bounds(tmp_path):
    path = _save_image(tmp_path / "large.png", (1920, 1080))

    fit = calculate_visual_fit(path, 850, 560, 960, 440, clamp_area=ILLUSTRATION_AREA)

    assert fit.display_width <= 850
    assert fit.display_height <= 560
    assert fit.display_width / fit.display_height == pytest.approx(1920 / 1080)


def test_vertical_image_does_not_exceed_max_height(tmp_path):
    path = _save_image(tmp_path / "vertical.png", (600, 1200))

    fit = calculate_visual_fit(path, 850, 560, 960, 440, clamp_area=ILLUSTRATION_AREA)

    assert fit.display_height <= 560
    assert fit.display_width <= 850


def test_horizontal_image_does_not_exceed_max_width(tmp_path):
    path = _save_image(tmp_path / "horizontal.png", (1600, 400))

    fit = calculate_visual_fit(path, 850, 560, 960, 440, clamp_area=ILLUSTRATION_AREA)

    assert fit.display_width <= 850
    assert fit.display_height <= 560


def test_logo_fits_80_by_80(tmp_path):
    path = _save_image(tmp_path / "logo.png", (400, 200))

    fit = calculate_visual_fit(path, 80, 80, 110, 85)

    assert fit.display_width <= 80
    assert fit.display_height <= 80
    assert fit.display_width == pytest.approx(80)
    assert fit.display_height == pytest.approx(40)


def test_transparent_padding_uses_visible_content_bbox(tmp_path):
    path = tmp_path / "padded.png"
    image = Image.new("RGBA", (1000, 1000), (255, 255, 255, 0))
    image.paste(Image.new("RGBA", (500, 250), (30, 30, 30, 255)), (250, 375))
    image.save(path)

    fit = calculate_visual_fit(path, 850, 560, 960, 440, clamp_area=ILLUSTRATION_AREA)

    assert fit.content_bbox == (250, 375, 750, 625)
    assert fit.display_width == pytest.approx(850)
    assert fit.display_height == pytest.approx(425)
