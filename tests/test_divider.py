from PIL import Image

from maowang_psych_template.draft import writer


def test_custom_divider_is_forced_to_1920_width_and_keep_source_height(tmp_path):
    source = tmp_path / "custom.png"
    target = tmp_path / "divider_1920w.png"
    Image.new("RGBA", (320, 10), (10, 20, 30, 255)).save(source)

    writer._render_divider(source, target)

    with Image.open(target).convert("RGBA") as image:
        assert image.size == (1920, 10)
        assert image.getpixel((960, 5)) == (10, 20, 30, 255)
