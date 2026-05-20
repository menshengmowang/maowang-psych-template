from maowang_psych_template.models import StoryboardRow, SubtitleItem
from maowang_psych_template.text_matcher import match_storyboard_to_subtitles


def _row(scene_id: str, script: str) -> StoryboardRow:
    return StoryboardRow(
        scene_id=scene_id,
        script=script,
        summary="",
        flow_prompt_en="",
        flow_prompt_zh="",
        reference_suggestion="",
        retry_prompt="",
        note="",
        row_number=1,
    )


def test_match_storyboard_to_subtitles_in_order():
    rows = [
        _row("1", "你越想控制别人，关系越容易失控。"),
        _row("2", "真正稳定的关系，是允许彼此有边界。"),
    ]
    subtitles = [
        SubtitleItem(1, 0, 1200, "你越想控制别人，"),
        SubtitleItem(2, 1200, 2600, "关系越容易失控。"),
        SubtitleItem(3, 2600, 3900, "真正稳定的关系，"),
        SubtitleItem(4, 3900, 5200, "是允许彼此有边界。"),
    ]

    scenes = match_storyboard_to_subtitles(rows, subtitles)

    assert len(scenes) == 2
    assert scenes[0].start_ms == 0
    assert scenes[0].end_ms == 2600
    assert scenes[1].start_ms == 2600
    assert scenes[1].end_ms == 5200

