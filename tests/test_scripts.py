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
        if p["kind"] == "sticker":  # 贴纸人物可以出血（超出页面边缘，被页面切掉）
            assert x0 < x1 and y0 < y1 and x1 > 0 and y0 < rv.CANVAS_H
            continue
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


@pytest.mark.skipif(not has_cjk_font(), reason="没有中文字体")
def test_draft_then_overlay(tmp_path):
    script = os.path.join(ROOT, "scripts", "render_visuals.py")
    r = subprocess.run([sys.executable, script, "comic", os.path.join(ROOT, "examples", "ep01-pages.json"),
                        "--draft", "--page", "1", "--out", str(tmp_path / "ep.png")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    draft = tmp_path / "ep-01-草稿.png"
    assert draft.exists()
    spec = {"mode": "color", "pages": [{"image": str(draft), "texts": [
        {"speaker": "A", "text": "测试对白", "at": [0.5, 0.2], "tail": [0.4, 0.3]},
        {"text": "旁白", "type": "caption", "at": [0.1, 0.05]},
        {"text": "砰！", "type": "sfx", "at": [0.8, 0.5]},
        {"text": "独白", "type": "monologue", "at": [0.3, 0.7]}]}]}
    sp = tmp_path / "ov.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, script, "overlay", str(sp), "--out", str(tmp_path / "final.png")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "final.png").exists()


def test_lint_flags_person_without_description(tmp_path):
    desc = "Jiang Yao, 28-year-old Chinese woman, chestnut hair in a low ponytail"
    spec = {"mode": "color", "cast": {"江遥": {"desc": desc}}, "pages": [{"layout": "custom", "boxes": {"1": [0, 0, 1, 1]},
            "panels": [{"scene": "吊牌特写", "characters": [],
                        "prompt": "close-up of a price tag, a woman's hand, aspect ratio 1:1, no text"}]}]}
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "lint", str(sp)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "描述串" in r.stdout


@pytest.mark.skipif(not has_cjk_font(), reason="没有中文字体")
def test_sticker_cutout_and_template(tmp_path):
    from PIL import Image, ImageDraw
    art = tmp_path / "fig.png"
    im = Image.new("RGB", (400, 800), (255, 255, 255))
    ImageDraw.Draw(im).ellipse((120, 40, 280, 200), fill=(200, 120, 90))
    ImageDraw.Draw(im).rectangle((100, 200, 300, 780), fill=(60, 60, 120))
    im.save(art)
    cut = rv.cutout(Image.open(art))
    assert cut.mode == "RGBA" and cut.getpixel((0, 0))[3] < 50
    spec = {"layout": "s-hero", "panels": [{}, {}, {}, {"image": str(art)}, {}, {}, {}]}
    sp = tmp_path / "p.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "comic", str(sp),
                        "--out", str(tmp_path / "o.png")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_cutout_keeps_warm_hair_on_cream_background():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (300, 300), (251, 238, 213))     # 奶油底色
    d = ImageDraw.Draw(im)
    d.ellipse((60, 40, 240, 220), fill=(150, 90, 55))      # 暖棕色头发（红色通道和底色差不多）
    d.ellipse((100, 90, 200, 210), fill=(250, 220, 195))   # 浅色皮肤
    d.ellipse((120, 130, 150, 160), fill=(255, 255, 255))  # 眼白
    cut = rv.cutout(im)
    w, h = cut.size
    assert cut.getpixel((w // 2, 30))[3] > 200            # 头发保留
    assert cut.getpixel((w // 2 - 15, 105))[3] > 200      # 眼白保留


def test_bubble_moves_off_face():
    cell = (0, 0, 400, 400)
    box = (150, 50, 300, 150)
    moved = rv.clear_of_face(box, [0.4, 0.1, 0.7, 0.4], cell, 10)
    assert moved != box


def test_example_storyboard_passes_lint():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render_visuals.py"), "lint",
                        os.path.join(ROOT, "examples", "ep01-pages.json")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
