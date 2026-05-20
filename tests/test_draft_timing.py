from pathlib import Path

from maowang_psych_template.draft import writer
from maowang_psych_template.models import SceneMatch, StoryboardRow, SubtitleItem


def _scene(end_ms: int) -> SceneMatch:
    row = StoryboardRow(
        scene_id="1",
        script="测试文案",
        summary="",
        flow_prompt_en="",
        flow_prompt_zh="",
        reference_suggestion="",
        retry_prompt="",
        note="",
        row_number=2,
    )
    return SceneMatch(
        storyboard=row,
        subtitles=[SubtitleItem(index=1, start_ms=0, end_ms=end_ms, text="测试字幕")],
        start_ms=0,
        end_ms=end_ms,
        match_score=1.0,
    )


def test_timing_plan_clamps_small_srt_overshoot_to_audio(monkeypatch):
    monkeypatch.setattr(writer, "_get_audio_duration_us", lambda _path: 91_891_000)
    scenes = [_scene(92_058)]

    plan = writer._calculate_timing_plan(Path("voice.wav"), scenes)

    assert plan.srt_total_duration_us == 92_058_000
    assert plan.audio_duration_us == 91_891_000
    assert plan.final_project_duration_us == 91_891_000
    assert plan.clamped_to_audio is True
    assert plan.clamped_segments is True
    assert scenes[0].end_ms == 91_891
    assert scenes[0].subtitles[0].end_ms == 91_891
