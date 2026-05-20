from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from maowang_psych_template.config import AppConfig
from maowang_psych_template.models import ILLUSTRATION_MODE_PRECOMPOSE_DARKEN
from maowang_psych_template.pipeline import GenerationPipeline


def test_precompose_mode_does_not_call_remove_white_background(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(image_dir / "a.png")

    scene = SimpleNamespace(
        storyboard=SimpleNamespace(scene_id="1", row_number=1, script="", flow_prompt_en=""),
        subtitles=[],
        start_ms=0,
        end_ms=1000,
        match_score=1.0,
        selected_image="a.png",
        processed_image_path=None,
        illustration_blend_mode="normal",
        illustration_opacity=1.0,
        warnings=[],
    )

    pipeline = GenerationPipeline(AppConfig(api_key=""), progress=lambda _: None)

    monkeypatch.setattr(pipeline, "_match_scenes", lambda inputs: [scene])

    called_remove = False

    def _raise_if_called(*args, **kwargs):
        nonlocal called_remove
        called_remove = True
        raise AssertionError("remove_white_background should not be called")

    monkeypatch.setattr("maowang_psych_template.pipeline.remove_white_background", _raise_if_called)

    monkeypatch.setattr(
        "maowang_psych_template.pipeline.JianyingDraftWriter.generate",
        lambda self, inputs, scenes: SimpleNamespace(output_dir=tmp_path / "out", match_report_path=None),
    )

    inputs = SimpleNamespace(
        illustration_fusion_mode=ILLUSTRATION_MODE_PRECOMPOSE_DARKEN,
        image_dir=image_dir,
        excel_path=tmp_path / "a.xlsx",
        srt_path=tmp_path / "a.srt",
    )

    pipeline.run(inputs)

    assert called_remove is False
    assert scene.processed_image_path is not None
    assert scene.processed_image_path.name.endswith("_darken.png")
