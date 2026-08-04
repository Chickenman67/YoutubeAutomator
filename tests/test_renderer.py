import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from script_generation.schema import Scene
from video_production.renderer import RenderResult, SceneRenderer

VW, VH = 1080, 1920


def make_scene(keywords=("stick figure running", "clock ticking", "map of Europe")):
    return Scene(
        scene_id=1,
        narration="word " * 200,
        key_visual_keywords=list(keywords),
        facts=["a verifiable fact", "another verifiable fact"],
    )


def test_estimate_duration_scales_with_word_count():
    renderer = SceneRenderer()
    assert renderer.estimate_duration("word " * 200) == pytest.approx(80.0, rel=0.01)
    assert renderer.estimate_duration("word " * 150) == pytest.approx(60.0, rel=0.01)
    assert renderer.estimate_duration("") == 0.0


def test_resolve_duration_clamps_estimated_to_60_90():
    renderer = SceneRenderer()
    assert renderer.resolve_duration("word " * 300) == pytest.approx(90.0)
    assert renderer.resolve_duration("word " * 100) == pytest.approx(60.0)


def test_resolve_duration_uses_explicit_when_given():
    renderer = SceneRenderer()
    assert renderer.resolve_duration("word " * 300, explicit=0.5) == pytest.approx(0.5)


def test_generate_source_is_valid_python_and_contains_keywords():
    renderer = SceneRenderer()
    scene = make_scene()
    source = renderer.generate_source(scene, duration=10.0)
    compile(source, "<generated>", "exec")
    assert "StickFigureScene" in source
    assert "10.0" in source
    assert "stick figure running" in source
    assert "clock ticking" in source
    assert "video_production.stickfigures" in source
    assert "import StickFigureScene" not in source


def test_generate_source_guards_empty_keywords():
    renderer = SceneRenderer()
    scene = make_scene(keywords=())
    source = renderer.generate_source(scene, duration=5.0)
    compile(source, "<generated>", "exec")


def test_render_creates_vertical_1080x1920_video(tmp_path):
    renderer = SceneRenderer()
    scene = make_scene(keywords=("stick figure running",))
    result = renderer.render(
        scene,
        output_name="scene_1",
        output_dir=str(tmp_path),
        duration=0.5,
        width=VW,
        height=VH,
        fps=20,
    )
    assert isinstance(result, RenderResult)
    assert result.path.exists()
    assert result.width == VW
    assert result.height == VH
    assert result.duration > 0


def test_render_accepts_duration_parameter_and_writes_source(tmp_path):
    renderer = SceneRenderer()
    scene = make_scene(keywords=("circle",))
    result = renderer.render(
        scene,
        output_name="scene_2",
        output_dir=str(tmp_path),
        duration=0.4,
        width=270,
        height=480,
        fps=15,
    )
    assert result.path.exists()
    assert (tmp_path / "scene_2.py").exists()
