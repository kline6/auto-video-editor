import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.subtitle_service import (
    ASS_WIDTH_FACTOR,
    BACKGROUND_PROBABILITY,
    BLOCK_TEXT_EFFECTS,
    FONTS_DIR,
    MAIN_EFFECT_MAX_MS,
    MAIN_EFFECT_MIN_MS,
    MAX_BLOCK_TEXT_SCALE,
    _extend_block_effect_duration,
    _main_effect_end_ms,
    _block_effect_category,
    _make_block_effect_sequence,
    _make_block_bg,
    _normalize_text_blocks,
    _resolve_block_background_layouts,
    _should_use_block_background,
    _set_y_override,
    _wrap_block_lines_for_box,
)


def _text_width(text, font_path, font_size):
    font = ImageFont.truetype(font_path, font_size)
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def test_wrap_block_lines_keeps_each_visual_line_inside_box():
    font_path = os.path.join(FONTS_DIR, "simhei.ttf")
    font_size = 78
    max_w = int(1080 * 0.98)
    pad_x = int(font_size * 1.4)
    text = "心怀阳光，每一天都是新的起点，勇敢迈出第一步，未来就在脚下"

    wrapped = _wrap_block_lines_for_box([text], font_path, font_size, max_w, pad_x)

    assert len(wrapped) > 1
    assert len(wrapped) <= 3
    bg_path = None
    try:
        bg_path, bg_w, _, eff_font_size = _make_block_bg(
            wrapped,
            font_path,
            font_size,
            font_size,
            (255, 255, 255, 235),
            pad_x=pad_x,
            pad_y=int(font_size * 0.75),
            max_w=max_w,
        )
        min_total_padding = max(48, int(eff_font_size * 1.6))
        max_render_width = bg_w - min_total_padding
        assert max_render_width > 0
        for line in wrapped:
            estimated_render_width = int(
                _text_width(line, font_path, eff_font_size)
                * ASS_WIDTH_FACTOR
                * MAX_BLOCK_TEXT_SCALE
            )
            assert estimated_render_width <= max_render_width
    finally:
        if bg_path and os.path.exists(bg_path):
            os.remove(bg_path)


def test_make_block_bg_keeps_unwrapped_long_text_inside_video_width():
    font_path = os.path.join(FONTS_DIR, "simhei.ttf")
    font_size = 78
    max_w = int(1080 * 0.98)
    text = "心怀阳光，每一天都是新的起点，勇敢迈出第一步，未来就在脚下"
    bg_path = None

    try:
        bg_path, bg_w, _, eff_font_size = _make_block_bg(
            [text],
            font_path,
            font_size,
            font_size,
            (255, 255, 255, 235),
            pad_x=int(font_size * 2.5),
            pad_y=int(font_size * 1.0),
            max_w=max_w,
        )
        estimated_render_width = int(
            _text_width(text, font_path, eff_font_size)
            * ASS_WIDTH_FACTOR
            * MAX_BLOCK_TEXT_SCALE
        )
        min_total_padding = max(48, int(eff_font_size * 1.6))

        assert bg_w <= max_w
        assert estimated_render_width + min_total_padding <= bg_w
    finally:
        if bg_path and os.path.exists(bg_path):
            os.remove(bg_path)


def test_block_text_effects_do_not_start_offscreen_or_invisible():
    risky_tags = (
        "\\clip(",
        "\\frx",
        "\\fry",
        "\\frz",
    )
    risky_scale = re.compile(r"\\fsc[xy](?:0|10)(?!\d)")
    move_tag = re.compile(r"\\move\(([^)]+)\)")

    for effect in BLOCK_TEXT_EFFECTS:
        with _set_y_override(500):
            dialogue = effect("测试字幕", 0, 5, 8, 1080, 1920, 78)

        assert "\\pos(" in dialogue or "\\move(" in dialogue, effect.__name__
        assert "\\t(" in dialogue, effect.__name__
        assert not risky_scale.search(dialogue), effect.__name__
        for tag in risky_tags:
            assert tag not in dialogue, effect.__name__

        move = move_tag.search(dialogue)
        if move:
            coords = [float(part) for part in move.group(1).split(",")[:4]]
            x1, y1, x2, y2 = coords
            assert 0 <= x1 <= 1080, effect.__name__
            assert 0 <= x2 <= 1080, effect.__name__
            assert 0 <= y1 <= 1920, effect.__name__
            assert 0 <= y2 <= 1920, effect.__name__


def test_block_text_effect_pool_has_rich_safe_motion():
    assert len(BLOCK_TEXT_EFFECTS) >= 24

    rendered = []
    for effect in BLOCK_TEXT_EFFECTS:
        with _set_y_override(500):
            rendered.append(effect("测试字幕", 0, 5, 8, 1080, 1920, 78))

    assert sum("\\move(" in dialogue for dialogue in rendered) >= 3
    assert sum("\\blur" in dialogue for dialogue in rendered) >= 3
    assert sum("\\t(" in dialogue for dialogue in rendered) >= 18
    assert sum(re.search(r"\\t\((?:8|9|10|11|12|13|14|15|16|17|18|19)\d{2}", dialogue) is not None
               for dialogue in rendered) >= 6


def test_block_effect_sequence_uses_many_visible_categories_before_repeating():
    sequence = _make_block_effect_sequence(12)
    names = [effect.__name__ for effect in sequence]
    categories = [_block_effect_category(effect) for effect in sequence]

    assert len(set(names)) == len(names)
    assert len(set(categories[:5])) >= 5
    assert all(left != right for left, right in zip(categories, categories[1:]))


def test_block_effect_pool_includes_rich_legacy_entry_states():
    categories = {_block_effect_category(effect) for effect in BLOCK_TEXT_EFFECTS}

    assert len(BLOCK_TEXT_EFFECTS) >= 36
    assert {
        "motion",
        "scale",
        "glow_blur",
        "shadow",
        "alpha",
        "color",
        "flip",
        "reveal",
    }.issubset(categories)


def test_motion_block_effects_have_visible_entry_travel():
    move_tag = re.compile(r"\\move\(([^)]+)\)")
    distances = []

    for effect in BLOCK_TEXT_EFFECTS:
        if _block_effect_category(effect) != "motion":
            continue
        with _set_y_override(500):
            dialogue = effect("测试字幕", 0, 5, 8, 1080, 1920, 78)
        move = move_tag.search(dialogue)
        assert move, effect.__name__
        x1, y1, x2, y2 = [float(part) for part in move.group(1).split(",")[:4]]
        distances.append(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)

    assert len(distances) >= 6
    assert sum(distance >= 90 for distance in distances) >= 5


def test_background_layouts_do_not_overlap_when_fixed_and_replacement_blocks_are_active():
    layouts = _resolve_block_background_layouts(
        [
            {
                "block_idx": 0,
                "pos_idx": 0,
                "preferred_cy": int(1920 * 0.15),
                "bg_h": 428,
                "start": 0.0,
                "end": 6.0,
            },
            {
                "block_idx": 3,
                "pos_idx": 3,
                "preferred_cy": int(1920 * 0.85),
                "bg_h": 428,
                "start": 3.0,
                "end": 6.0,
            },
            {
                "block_idx": 4,
                "pos_idx": 1,
                "preferred_cy": int(1920 * 0.35),
                "bg_h": 194,
                "start": 4.0,
                "end": 6.0,
            },
            {
                "block_idx": 5,
                "pos_idx": 2,
                "preferred_cy": int(1920 * 0.65),
                "bg_h": 194,
                "start": 5.0,
                "end": 6.0,
            },
        ],
        video_height=1920,
        font_size=78,
    )

    active = [layout for layout in layouts if layout["start"] < 5.5 < layout["end"]]
    for i, left in enumerate(active):
        left_top = left["cy"] - left["bg_h"] / 2
        left_bottom = left["cy"] + left["bg_h"] / 2
        for right in active[i + 1:]:
            right_top = right["cy"] - right["bg_h"] / 2
            right_bottom = right["cy"] + right["bg_h"] / 2
            assert left_bottom <= right_top or right_bottom <= left_top


def test_block_effect_duration_is_extended_past_one_second():
    long_transition = re.compile(r"\\t\(\d+,([1-9]\d{3,})")

    for effect in BLOCK_TEXT_EFFECTS:
        with _set_y_override(500):
            dialogue = effect("测试字幕", 0, 5, 8, 1080, 1920, 78)
        extended = _extend_block_effect_duration(dialogue, 5.0)

        assert long_transition.search(extended), effect.__name__


def test_main_block_effect_last_between_point_eight_and_one_second():
    for effect in BLOCK_TEXT_EFFECTS:
        with _set_y_override(500):
            dialogue = effect("测试字幕", 0, 5, 8, 1080, 1920, 78)
        extended = _extend_block_effect_duration(dialogue, 5.0)

        main_end = _main_effect_end_ms(extended)
        assert MAIN_EFFECT_MIN_MS <= main_end <= MAIN_EFFECT_MAX_MS, effect.__name__


def test_background_probability_is_sixty_forty(monkeypatch):
    values = iter([0.0, 0.59, 0.6, 0.99])
    monkeypatch.setattr("services.subtitle_service.random.random", lambda: next(values))

    assert BACKGROUND_PROBABILITY == 0.6
    assert _should_use_block_background() is True
    assert _should_use_block_background() is True
    assert _should_use_block_background() is False
    assert _should_use_block_background() is False


def test_normalize_text_blocks_accepts_old_flat_inputs():
    assert _normalize_text_blocks("单行") == [["单行"]]
    assert _normalize_text_blocks(["第一块", "第二块"]) == [["第一块"], ["第二块"]]
    assert _normalize_text_blocks([["第一块", "第二行"], ["第二块"]]) == [
        ["第一块", "第二行"],
        ["第二块"],
    ]
