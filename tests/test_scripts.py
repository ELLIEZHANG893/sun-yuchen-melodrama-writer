"""冒烟测试：版式模板能算出格子、分镜样例能排版、连载检查脚本能跑。

渲染相关的测试需要中文字体；本机没有中文字体时会自动跳过。
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import render_visuals as rv  # noqa: E402


def has_cjk_font():
    return any(os.path.exists(p) for p in rv.SANS_CANDIDATES + rv.SERIF_CANDIDATES)


@pytest.mark.parametrize("layout", list(rv.TEMPLATES) + ["2x2", "3x3", "1x4"])
@pytest.mark.parametrize("mode", ["color", "bw"])
def test_layouts_fit_on_canvas(layout, mode):
    st = rv.resolve_style(mode)
    panels = rv.layout_panels(layout, rv.CANVAS_W, rv.CANVAS_H, True, True, st)
    assert panels
    for p in panels:
        x0, y0, x1, y1 = p["box"]
        assert 0 <= x0 < x1 <= rv.CANVAS_W
        assert 0 <= y0 < y1 <= rv.CANVAS_H


def test_box_override_moves_one_panel():
    st = rv.resolve_style("color")
    base = rv.layout_panels("9-splash", 1080, 1920, True, True, st)
    moved = rv.layout_panels("9-splash", 1080, 1920, True, True, st, {"8": [0.64, 0.615, 0.97, 0.715]})
    assert base[7]["box"] != moved[7]["box"]
    assert base[0]["box"] == moved[0]["box"]


def test_inset_coverage_is_reported():
    st = rv.resolve_style("color")
    cov = rv.covered_by_insets(rv.layout_panels("9-splash", 1080, 1920, True, True, st))
    assert 9 in cov


@pytest.mark.skipif(not has_cjk_font(), reason="没有中文字体")
@pytest.mark.parametrize("spec", ["ep01-comic.json", "ep01-comic-bw.json"])
def test_sample_storyboards_render(tmp_path, spec):
    out = tmp_path / "out.png"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "comic",
                        os.path.join(ROOT, "examples", spec), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists() and out.stat().st_size > 10000


@pytest.mark.skipif(not has_cjk_font(), reason="没有中文字体")
def test_cover_renders(tmp_path):
    out = tmp_path / "cover.png"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "cover",
                        "--title", "测试片名", "--tagline", "一句话卖点", "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_storyboard_samples_are_valid_json():
    for name in ("ep01-comic.json", "ep01-comic-bw.json"):
        with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as fh:
            spec = json.load(fh)
        assert spec["panels"]


def test_check_episodes_runs_on_sample():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_episodes.py"),
                        os.path.join(ROOT, "examples", "sample-12-episodes.md")],
                       capture_output=True, text=True)
    assert "没有找到" not in (r.stdout + r.stderr)


@pytest.mark.skipif(not has_cjk_font(), reason="没有中文字体")
def test_multipage_storyboard_renders_each_page(tmp_path):
    out = tmp_path / "ep.png"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "comic",
                        os.path.join(ROOT, "examples", "ep01-pages.json"), "--out", str(out), "--strip"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with open(os.path.join(ROOT, "examples", "ep01-pages.json"), encoding="utf-8") as fh:
        n = len(json.load(fh)["pages"])
    for i in range(1, n + 1):
        assert (tmp_path / f"ep-{i:02d}.png").exists()
    assert (tmp_path / "ep-长条.png").exists()


def test_custom_layout_uses_boxes_in_order():
    st = rv.resolve_style("color")
    boxes = {"1": [0, 0, 1, .5], "2": {"box": [0, .5, 1, 1], "kind": "free"}, "3": {"box": [.6, .6, .95, .8], "kind": "inset"}}
    panels = rv.layout_panels("custom", 1080, 1920, False, False, st, boxes)
    assert [p["kind"] for p in panels] == ["box", "free", "inset"]
    assert panels[0]["box"][1] < panels[1]["box"][1]
