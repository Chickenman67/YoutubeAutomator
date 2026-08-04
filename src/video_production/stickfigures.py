from hashlib import md5

import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    WHITE,
    Arrow,
    Circle,
    Dot,
    Line,
    Rectangle,
    RegularPolygon,
    Square,
    Star,
    Text,
    Triangle,
    VGroup,
    VMobject,
)

ACCENT_COLOR = "#FFC53D"

_ICON_BUILDERS = [
    lambda c: Circle(radius=0.4, color=c),
    lambda c: Triangle(color=c),
    lambda c: Square(side_length=0.7, color=c),
    lambda c: RegularPolygon(n=5, color=c),
    lambda c: Star(inner_radius=0.3, outer_radius=0.7, color=c),
    lambda c: Rectangle(width=0.9, height=0.5, color=c),
    lambda c: Arrow(LEFT, RIGHT, color=c, stroke_width=6),
    lambda c: Dot(color=c, radius=0.35),
]

_KEYWORD_ICON_INDEX = {
    "planet": 0,
    "moon": 0,
    "sun": 0,
    "triangle": 1,
    "square": 2,
    "star": 4,
    "rectangle": 5,
    "box": 5,
    "arrow": 6,
    "dot": 7,
    "spot": 7,
}


def _pick_index(keyword: str, size: int) -> int:
    digest = md5(str(keyword or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % size


def StickFigure(color=WHITE, scale: float = 1.0) -> VGroup:
    head = Circle(radius=0.3, color=color)
    body = Line(np.array([0.0, -0.3, 0.0]), np.array([0.0, -1.1, 0.0]), color=color, stroke_width=6)
    arm_left = Line(np.array([0.0, -0.55, 0.0]), np.array([-0.55, -0.75, 0.0]), color=color, stroke_width=6)
    arm_right = Line(np.array([0.0, -0.55, 0.0]), np.array([0.55, -0.75, 0.0]), color=color, stroke_width=6)
    leg_left = Line(np.array([0.0, -1.1, 0.0]), np.array([-0.4, -1.6, 0.0]), color=color, stroke_width=6)
    leg_right = Line(np.array([0.0, -1.1, 0.0]), np.array([0.4, -1.6, 0.0]), color=color, stroke_width=6)
    figure = VGroup(head, body, arm_left, arm_right, leg_left, leg_right).scale(scale)
    return figure


def icon_for_keyword(keyword: str, color=WHITE) -> VMobject:
    text = str(keyword or "").lower()
    for token, index in _KEYWORD_ICON_INDEX.items():
        if token in text:
            return _ICON_BUILDERS[index](color)
    return _ICON_BUILDERS[_pick_index(text, len(_ICON_BUILDERS))](color)


def build_keyword_visual(keyword: str, color=WHITE, accent=ACCENT_COLOR) -> VGroup:
    label = Text(str(keyword)[:24], color=accent, font_size=34)
    figure = StickFigure(color=color)
    icon = icon_for_keyword(keyword, color=color)
    row = VGroup(figure, icon).arrange(RIGHT, buff=0.8)
    return VGroup(label, row).arrange(DOWN, buff=0.5)
