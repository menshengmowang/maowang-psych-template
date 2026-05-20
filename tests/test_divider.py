from PIL import Image

from maowang_psych_template.draft import writer


def test_default_divider_is_opaque_black_1920_by_16(tmp_path):
    target = tmp_path / "divider_1920x16.png"

    writer._render_divider(None, target, 16)

    with Image.open(target).convert("RGBA") as image:
        assert image.size == (1920, 16)
        assert image.getpixel((960, 8)) == (0, 0, 0, 255)


def test_custom_divider_is_forced_to_1920_width_and_selected_height(tmp_path):
    source = tmp_path / "custom.png"
    target = tmp_path / "divider_1920x20.png"
    Image.new("RGBA", (320, 10), (10, 20, 30, 255)).save(source)

    writer._render_divider(source, target, 20)

    with Image.open(target).convert("RGBA") as image:
        assert image.size == (1920, 20)
        assert image.getpixel((960, 10)) == (10, 20, 30, 255)
