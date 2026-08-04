import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from manim import Circle, Star, VGroup, VMobject
from video_production import stickfigures as sf


def test_stick_figure_is_nonempty_white_vgroup():
    figure = sf.StickFigure(color=sf.WHITE)
    assert isinstance(figure, VGroup)
    assert len(figure) > 0
    assert all(isinstance(mp, VMobject) for mp in figure)


def test_stick_figure_scale_changes_size():
    small = sf.StickFigure(scale=1.0)
    big = sf.StickFigure(scale=2.0)
    assert big.width > small.width


def test_icon_for_keyword_returns_vmobject():
    for kw in ("planet", "arrow", "clock", "bomb", "tree", "anything"):
        icon = sf.icon_for_keyword(kw)
        assert isinstance(icon, VMobject)


def test_icon_for_keyword_is_deterministic():
    assert type(sf.icon_for_keyword("clock")) == type(sf.icon_for_keyword("clock"))


def test_icon_for_keyword_maps_semantic_tokens():
    assert isinstance(sf.icon_for_keyword("planet"), Circle)
    assert isinstance(sf.icon_for_keyword("the sun"), Circle)
    assert isinstance(sf.icon_for_keyword("star"), Star)


def test_build_keyword_visual_contains_text_and_mobjects():
    visual = sf.build_keyword_visual("stick figure running", color=sf.WHITE,
                                     accent=sf.ACCENT_COLOR)
    assert isinstance(visual, VGroup)
    assert len(visual) >= 1
