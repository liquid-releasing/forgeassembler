# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""The title renderer.

These tests look at the PIXELS, not at a filter string, because the
whole reason the card stopped being a drawtext call is that a filter
string cannot tell you whether the words left the frame. The bounding
box of the non-transparent pixels is the thing worth pinning: it is
exactly the question "did this fit".
"""

from __future__ import annotations

import pytest

from forgeassembler_core.titles import (
    GLYPHS,
    TITLE_LAYOUTS,
    TitleSpec,
    render_title_png,
    title_catalog,
)

pytest.importorskip("PIL")

LONG_TITLE = (
    "An Extremely Long Title That Would Certainly Have Run Straight Off "
    "Both Edges Of The Frame Under drawtext, And Then Some More Besides"
)


def _render(tmp_path, name="card.png", width=1920, height=1080,
            over_frame=False, **params):
    spec = TitleSpec.from_params(params)
    path = render_title_png(spec, width, height, tmp_path / name,
                            over_frame=over_frame)
    from PIL import Image

    return Image.open(path).convert("RGBA")


def _ink(img):
    """The bounding box of everything drawn, or None for a blank card."""
    return img.getchannel("A").getbbox()


# ── It fits. That is the whole point. ────────────────────────────────

@pytest.mark.parametrize("layout", TITLE_LAYOUTS)
def test_a_title_too_long_for_the_frame_stays_inside_it(tmp_path, layout):
    img = _render(tmp_path, f"{layout}.png", layout=layout,
                  title=LONG_TITLE, subtitle="and a subtitle as well")
    box = _ink(img)
    assert box is not None, "a card with words must draw something"
    left, top, right, bottom = box
    assert left >= 0 and top >= 0
    assert right <= img.width, "the title ran off the right of the frame"
    assert bottom <= img.height, "the title ran off the bottom of the frame"


@pytest.mark.parametrize("layout", TITLE_LAYOUTS)
def test_a_single_unbreakable_word_still_fits(tmp_path, layout):
    # No spaces to wrap at. Shrinking is not enough on its own, so the
    # word has to break mid-word rather than leave the frame.
    img = _render(tmp_path, f"{layout}.png", layout=layout,
                  title="A" * 120)
    left, top, right, bottom = _ink(img)
    assert right <= img.width
    assert left >= 0


def test_a_short_title_is_not_shrunk(tmp_path):
    # The fitting must only ever be a rescue. A title that fits is drawn
    # at the size the layout asked for, and a regression here would
    # quietly shrink every card in the app.
    short = _render(tmp_path, "short.png", title="Two")
    _, top, _, bottom = _ink(short)
    # k*130 type; its cap height alone is well over a tenth of the frame.
    assert (bottom - top) > 1080 * 0.10


# ── Every layout draws, and draws differently ────────────────────────

@pytest.mark.parametrize("layout", TITLE_LAYOUTS)
def test_every_layout_puts_ink_on_the_frame(tmp_path, layout):
    img = _render(tmp_path, f"{layout}.png", layout=layout,
                  title="Part Two", subtitle="a subtitle", eyebrow="act i")
    assert _ink(img) is not None


def test_a_lower_third_sits_along_the_bottom(tmp_path):
    img = _render(tmp_path, layout="lower", title="Victoria Oaks")
    _, top, _, _ = _ink(img)
    assert top > img.height * 0.5, "a lower third belongs in the lower half"


def test_a_centred_card_is_centred(tmp_path):
    img = _render(tmp_path, layout="centered", title="Centred")
    left, _, right, _ = _ink(img)
    midpoint = (left + right) / 2
    assert abs(midpoint - img.width / 2) < img.width * 0.02


def test_a_card_with_nothing_to_say_draws_nothing(tmp_path):
    assert _ink(_render(tmp_path)) is None


# ── The backdrop is not ours to paint ────────────────────────────────

def test_the_card_never_paints_its_own_background(tmp_path):
    # The bridge is the background -- a flat theme colour or a real
    # frame. If the card painted one too, a frame-backed card would be
    # a flat colour with words on it.
    img = _render(tmp_path, title="Part Two")
    assert img.getpixel((2, 2))[3] == 0, "the corner must be transparent"


def test_over_a_frame_the_scrim_works_harder(tmp_path):
    # A full-quote card over a picture darkens the whole frame so the
    # words read; over a flat colour there is nothing to hide.
    flat = _render(tmp_path, "flat.png", layout="fullquote", title="Words")
    over = _render(tmp_path, "over.png", layout="fullquote", title="Words",
                   over_frame=True)
    assert flat.getpixel((2, 2))[3] == 0
    assert over.getpixel((2, 2))[3] > 0


def test_a_lower_third_scrim_stops_short_of_opaque_over_a_frame(tmp_path):
    flat = _render(tmp_path, "flat.png", layout="lower", title="Words")
    over = _render(tmp_path, "over.png", layout="lower", title="Words",
                   over_frame=True)
    bottom = (10, 1079)
    assert flat.getpixel(bottom)[3] > over.getpixel(bottom)[3], (
        "over a picture the scrim has to let the picture through"
    )


# ── Resolution independence ──────────────────────────────────────────

def test_the_same_card_renders_the_same_shape_at_4k(tmp_path):
    # One spec, any output size: this is what lets a card be rendered
    # at the target resolution instead of scaled up from 1080p.
    hd = _render(tmp_path, "hd.png", 1920, 1080, title="Part Two",
                 subtitle="a subtitle")
    uhd = _render(tmp_path, "uhd.png", 3840, 2160, title="Part Two",
                  subtitle="a subtitle")
    for a, b in zip(_ink(hd), _ink(uhd)):
        assert b == pytest.approx(a * 2, rel=0.05)


# ── Reading a spec out of whatever the project file holds ────────────

def test_the_old_single_text_field_still_means_the_title():
    assert TitleSpec.from_params({"text": "Part Two"}).title == "Part Two"
    # A project saved with both -- the newer field wins.
    both = TitleSpec.from_params({"text": "old", "title": "new"})
    assert both.title == "new"


def test_an_unknown_layout_falls_back_rather_than_raising():
    spec = TitleSpec.from_params(
        {"layout": "hologram", "theme": "chartreuse", "glyph": "unicorn"},
    )
    assert spec.layout in TITLE_LAYOUTS
    assert spec.theme in dict(
        (t["id"], t) for t in title_catalog()["themes"]
    )
    assert spec.glyph in GLYPHS


def test_windows_line_endings_do_not_become_blank_lines():
    assert TitleSpec.from_params({"title": "one\r\ntwo"}).title == "one\ntwo"


def test_a_junk_colour_override_is_ignored(tmp_path):
    spec = TitleSpec.from_params({"text_color": "not-a-colour"})
    assert spec.text_color == ""
    assert spec.foreground_color() == "#fafafa"   # back to the theme


def test_a_colour_override_survives_a_missing_hash():
    assert TitleSpec.from_params({"accent_color": "00ff00"}).accent() == "#00ff00"


# ── The catalog the UI draws its pickers from ────────────────────────

def test_the_catalog_offers_exactly_what_the_renderer_can_draw():
    catalog = title_catalog()
    assert [layout["id"] for layout in catalog["layouts"]] == list(TITLE_LAYOUTS)
    assert [glyph["id"] for glyph in catalog["glyphs"]] == list(GLYPHS)
    for layout in catalog["layouts"]:
        assert layout["label"] and layout["help"]
    for theme in catalog["themes"]:
        # The UI needs the swatch colours to draw a theme chip.
        assert theme["bg"].startswith("#")
        assert theme["fg"].startswith("#")
        assert theme["accent"].startswith("#")


@pytest.mark.parametrize("glyph", [g for g in GLYPHS if g != "none"])
def test_every_mark_in_the_catalog_actually_draws(tmp_path, glyph):
    # A picker offering a mark that renders as nothing is worse than a
    # picker with fewer marks in it.
    plain = _render(tmp_path, "plain.png", title="Part Two")
    marked = _render(tmp_path, f"{glyph}.png", title="Part Two", glyph=glyph)
    assert _ink(marked)[1] < _ink(plain)[1], f"{glyph} drew nothing above the title"
