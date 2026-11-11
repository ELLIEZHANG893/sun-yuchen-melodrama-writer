#!/usr/bin/env python3
"""把 AI 生成的画面排成封面或竖屏宫格漫画，并负责叠加中文文字。

图像模型写中文容易出错别字，所以片名、对白、旁白、音效字都由本脚本叠加，
出图时只要求“画面里不要有任何文字”。

依赖：Pillow（pip install pillow）+ 一个中文字体（自动查找系统字体，或用 --font 指定）。

用法：
    # 封面：图片可省略，省略时生成占位图，用来预览片名排版
    python scripts/render_visuals.py cover --image cover.png --title "配型单上写着无亲缘" \
        --tagline "全家逼我捐肾那天，真相露出来了" --tag "女频·逆袭" --ratio 3:4 --out cover-final.png

    # 漫画：按分镜 JSON 排版（模板见 references/comic-guide.md）
    python scripts/render_visuals.py comic visuals/ep01-comic.json --out ep01-comic.png
    python scripts/render_visuals.py comic visuals/ep01-comic.json --bw   # 强制黑白

    # 查看某种版式每一格的像素尺寸和建议出图比例
    python scripts/render_visuals.py sizes --layout 3x3
"""
import argparse
import json
import math
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    # Linux（思源黑体 / Noto Sans CJK）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

FONT_PATH = None

CANVAS_W, CANVAS_H = 1080, 1920
MARGIN, GUTTER = 40, 20
TITLE_BAND, FOOTER_BAND = 150, 90


# ---------- 字体与文字 ----------

def find_font(user_path=None):
    if user_path:
        if not os.path.exists(user_path):
            sys.exit(f"找不到字体文件：{user_path}")
        return user_path
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    sys.exit("没找到中文字体。请安装思源黑体 / Noto Sans CJK，或用 --font 指定 .ttf/.ttc/.otf 文件。")


def font(size):
    return ImageFont.truetype(FONT_PATH, int(size))


def text_w(draw, s, f):
    if not s:
        return 0
    l, _, r, _ = draw.textbbox((0, 0), s, font=f)
    return r - l


def line_h(f):
    a, d = f.getmetrics()
    return a + d


def wrap(draw, text, f, max_w):
    """中文按字换行；保留用户写的换行符；避免标点出现在行首。"""
    no_start = set("，。！？、；：”’）》」』…,.!?;:)")
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if text_w(draw, cur + ch, f) <= max_w or not cur:
                cur += ch
            elif ch in no_start:
                cur += ch  # 标点挂在行尾，宁可略超
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


# ---------- 图片处理 ----------

def to_bw(img):
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.35)
    return g.convert("RGB")


def cover_fit(img, w, h, focus=(0.5, 0.5)):
    """等比放大后按焦点裁切，填满 w×h。focus 为 (x, y) 0—1，默认居中。"""
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    nw, nh = math.ceil(img.width * scale), math.ceil(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = int((nw - w) * focus[0])
    top = int((nh - h) * focus[1])
    return img.crop((left, top, left + w, top + h))


def placeholder(w, h, label, desc="", bw=False, at=0.32):
    img = Image.new("RGB", (w, h), (226, 226, 226) if bw else (214, 222, 236))
    d = ImageDraw.Draw(img)
    for i in range(-h, w, 28):  # 斜纹，一眼看出是占位
        d.line([(i, 0), (i + h, h)], fill=(205, 205, 205) if bw else (200, 210, 226), width=2)
    f1 = font(max(22, w * 0.09))
    d.text((w / 2, h * at), label, font=f1, fill=(90, 90, 90), anchor="mm")
    if desc:
        f2 = font(max(14, w * 0.045))
        lines = wrap(d, desc, f2, w * 0.82)[:8]
        y = h * (at + 0.1)
        for ln in lines:
            d.text((w / 2, y), ln, font=f2, fill=(110, 110, 110), anchor="ma")
            y += line_h(f2) * 1.15
    return img


def load_or_placeholder(path, base_dir, w, h, label, desc, bw, focus=(0.5, 0.5)):
    if path:
        full = path if os.path.isabs(path) else os.path.join(base_dir, path)
        if os.path.exists(full):
            img = cover_fit(Image.open(full), w, h, focus)
            return (to_bw(img) if bw else img), True
        print(f"  · 找不到图片 {path}，先用占位图", file=sys.stderr)
    return placeholder(w, h, label, desc, bw), False


# ---------- 漫画元素 ----------

def bubble_shape(d, box, kind, outline_w):
    x0, y0, x1, y1 = box
    if kind == "shout":  # 爆炸气泡：爽点、怒吼
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2 * 1.22 + 10, (y1 - y0) / 2 * 1.35 + 10
        pts, n = [], 22
        for i in range(n * 2):
            a = math.pi * i / n
            k = 1.0 if i % 2 == 0 else 0.86
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
        d.polygon(pts, fill="white", outline="black", width=outline_w)
    elif kind == "thought":  # 内心独白
        r = min((y1 - y0) / 2, (x1 - x0) / 2)
        d.rounded_rectangle(box, radius=r, fill="white", outline="black", width=outline_w)
    else:
        r = min((y1 - y0) / 2, 36)
        d.rounded_rectangle(box, radius=r, fill="white", outline="black", width=outline_w)


def draw_tail(d, box, cell, kind, outline_w):
    """从气泡指向格子中心的尾巴。"""
    x0, y0, x1, y1 = box
    cx, cy = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
    bx = min(max(cx, x0 + 30), x1 - 30)
    below = cy > (y0 + y1) / 2
    edge = y1 if below else y0
    tip = (bx + (cx - bx) * 0.25, edge + (34 if below else -34))
    if kind == "thought":
        for i, r in enumerate((9, 6)):
            t = (i + 1) / 3
            px = bx + (tip[0] - bx) * t
            py = edge + (tip[1] - edge) * t + (6 if below else -6)
            d.ellipse((px - r, py - r, px + r, py + r), fill="white", outline="black", width=max(2, outline_w - 1))
        return
    if kind == "shout":
        return
    base = [(bx - 14, edge), (bx + 14, edge)]
    d.polygon(base + [tip], fill="white")
    d.line([base[0], tip, base[1]], fill="black", width=outline_w, joint="curve")
    # 盖住气泡边框上尾巴根部那一段
    d.line([(bx - 12, edge), (bx + 12, edge)], fill="white", width=outline_w + 1)


def place_box(cell, pos, bw_, bh, pad, stack):
    cx0, cy0, cx1, cy1 = cell
    pos = pos or "top-left"
    vert = "bottom" if pos.startswith("bottom") else ("middle" if pos.startswith("middle") else "top")
    horiz = "right" if pos.endswith("right") else ("left" if pos.endswith("left") else "center")
    if horiz == "left":
        x = cx0 + pad
    elif horiz == "right":
        x = cx1 - pad - bw_
    else:
        x = (cx0 + cx1 - bw_) / 2
    key = (vert, horiz)
    off = stack.get(key, 0)
    if vert == "top":
        y = cy0 + pad + off
    elif vert == "bottom":
        y = cy1 - pad - bh - off
    else:
        y = (cy0 + cy1 - bh) / 2 + off
    stack[key] = off + bh + pad * 0.8
    return (x, y, x + bw_, y + bh)


def draw_dialogue(canvas, cell, items, base_size, stack):
    d = ImageDraw.Draw(canvas)
    cw = cell[2] - cell[0]
    pad = max(10, cw * 0.035)
    for it in items:
        kind = it.get("type", "speech")
        text = it.get("text", "").strip()
        if not text:
            continue
        size = base_size * (1.12 if kind == "shout" else 1.0)
        f = font(size)
        lines = wrap(d, text, f, cw * 0.56)
        tw = max(text_w(d, ln, f) for ln in lines)
        lh = line_h(f) * 1.12
        ip_x, ip_y = size * 0.75, size * 0.5
        bw_, bh = tw + ip_x * 2, lh * len(lines) + ip_y * 2
        spike = 0.25 * bw_ + 12 if kind == "shout" else 0
        spike_y = 0.40 * bh + 12 if kind == "shout" else 0
        outer = place_box(cell, it.get("pos"), bw_ + spike, bh + spike_y, pad, stack)
        box = (outer[0] + spike / 2, outer[1] + spike_y / 2, outer[2] - spike / 2, outer[3] - spike_y / 2)
        ow = max(2, int(base_size / 11))
        bubble_shape(d, box, kind, ow)
        draw_tail(d, box, cell, kind, ow)
        y = box[1] + ip_y
        for ln in lines:
            d.text(((box[0] + box[2]) / 2, y), ln, font=f, fill="black", anchor="ma")
            y += lh


def draw_caption(canvas, cell, text, base_size, bw):
    """旁白框：贴在格子左上角的方框，写时间地点或内心一句话。"""
    d = ImageDraw.Draw(canvas)
    f = font(base_size * 0.82)
    cw = cell[2] - cell[0]
    lines = wrap(d, text, f, cw * 0.7)
    tw = max(text_w(d, ln, f) for ln in lines)
    lh = line_h(f) * 1.1
    p = base_size * 0.35
    box = (cell[0], cell[1], cell[0] + tw + p * 2, cell[1] + lh * len(lines) + p * 2)
    d.rectangle(box, fill=(255, 255, 255) if bw else (255, 241, 186), outline="black", width=3)
    y = box[1] + p
    for ln in lines:
        d.text((box[0] + p, y), ln, font=f, fill="black")
        y += lh
    return box[3] - box[1]


def draw_sfx(canvas, cell, sfx, base_size, bw):
    """音效字：大号描边字，略微倾斜。"""
    text = sfx.get("text") if isinstance(sfx, dict) else str(sfx)
    pos = sfx.get("pos", "middle-right") if isinstance(sfx, dict) else "middle-right"
    if not text:
        return
    size = base_size * 2.0
    f = font(size)
    tmp = ImageDraw.Draw(canvas)
    tw = text_w(tmp, text, f) + 30
    th = line_h(f) + 30
    layer = Image.new("RGBA", (int(tw), int(th)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    fill = (30, 30, 30) if bw else (230, 40, 40)
    ld.text((15, 10), text, font=f, fill=fill, stroke_width=max(3, int(size / 12)), stroke_fill="white")
    layer = layer.rotate(10, expand=True, resample=Image.BICUBIC)
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    xs = {"left": 0.05, "center": 0.5, "right": 0.95}
    ys = {"top": 0.08, "middle": 0.5, "bottom": 0.92}
    vert, _, horiz = pos.partition("-")
    horiz = horiz or "center"
    cx = cell[0] + cw * xs.get(horiz, 0.5)
    cy = cell[1] + ch * ys.get(vert, 0.5)
    x = int(min(max(cx - layer.width / 2, cell[0]), cell[2] - layer.width))
    y = int(min(max(cy - layer.height / 2, cell[1]), cell[3] - layer.height))
    canvas.paste(layer, (x, y), layer)


# ---------- 版式 ----------

def parse_layout(s):
    try:
        cols, rows = (int(v) for v in s.lower().replace("×", "x").split("x"))
        assert 1 <= cols <= 4 and 1 <= rows <= 6
        return cols, rows
    except Exception:
        sys.exit(f"版式写法是 列x行，例如 2x2、3x3、1x4，收到：{s}")


def grid_cells(cols, rows, W, H, has_title, has_footer):
    top = MARGIN + (TITLE_BAND if has_title else 0)
    bottom = H - MARGIN - (FOOTER_BAND if has_footer else 0)
    cw = (W - 2 * MARGIN - (cols - 1) * GUTTER) / cols
    ch = (bottom - top - (rows - 1) * GUTTER) / rows
    cells = []
    for r in range(rows):
        for c in range(cols):
            x = MARGIN + c * (cw + GUTTER)
            y = top + r * (ch + GUTTER)
            cells.append(tuple(int(round(v)) for v in (x, y, x + cw, y + ch)))
    return cells


def nearest_ratio(w, h):
    options = ["1:1", "2:3", "3:4", "3:5", "9:16", "4:3", "3:2", "16:9", "21:9"]
    best = min(options, key=lambda r: abs(math.log((w / h) / (int(r.split(":")[0]) / int(r.split(":")[1])))))
    return best


def cmd_sizes(a):
    cols, rows = parse_layout(a.layout)
    cells = grid_cells(cols, rows, a.width, a.height, True, True)
    x0, y0, x1, y1 = cells[0]
    w, h = x1 - x0, y1 - y0
    print(f"版式 {cols}列×{rows}行，画布 {a.width}×{a.height}")
    print(f"每格约 {w}×{h} 像素，出图建议比例 {nearest_ratio(w, h)}（脚本会自动裁切，比例接近即可）")


def cmd_comic(a):
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(a.spec))
    cols, rows = parse_layout(a.layout or spec.get("layout", "2x2"))
    W, H = spec.get("canvas", [CANVAS_W, CANVAS_H])
    bw = a.bw or spec.get("mode", "color") == "bw"
    title, footer = spec.get("title", ""), spec.get("footer", "")
    panels = spec.get("panels", [])
    need = cols * rows
    if len(panels) != need:
        print(f"  · 版式需要 {need} 格，分镜里有 {len(panels)} 格；多的忽略，少的补占位", file=sys.stderr)
        panels = (panels + [{}] * need)[:need]

    canvas = Image.new("RGB", (W, H), "white")
    cells = grid_cells(cols, rows, W, H, bool(title), bool(footer))
    cw = cells[0][2] - cells[0][0]
    base_size = min(40, max(20, cw * 0.072))
    d = ImageDraw.Draw(canvas)

    if title:
        f = font(56)
        while text_w(d, title, f) > W - 2 * MARGIN and f.size > 28:
            f = font(f.size - 2)
        d.text((W / 2, MARGIN + TITLE_BAND / 2 - 8), title, font=f, fill="black", anchor="mm")

    found = 0
    for i, (cell, p) in enumerate(zip(cells, panels), 1):
        w, h = cell[2] - cell[0], cell[3] - cell[1]
        img, ok = load_or_placeholder(p.get("image"), base_dir, w, h, f"格 {i}",
                                      p.get("scene", ""), bw, tuple(p.get("focus", (0.5, 0.5))))
        found += ok
        canvas.paste(img, cell[:2])
        stack = {}
        if p.get("caption"):
            ch_ = draw_caption(canvas, cell, p["caption"], base_size, bw) + 6
            for hz in ("left", "center", "right"):
                stack[("top", hz)] = ch_
        if p.get("sfx"):
            draw_sfx(canvas, cell, p["sfx"], base_size, bw)
        draw_dialogue(canvas, cell, p.get("dialogue", []), base_size, stack)
        ImageDraw.Draw(canvas).rectangle(cell, outline="black", width=4)

    if footer:
        f = font(38)
        d.text((W / 2, H - MARGIN - FOOTER_BAND / 2 + 6), footer, font=f, fill=(60, 60, 60), anchor="mm")

    out = a.out or os.path.splitext(a.spec)[0] + ".png"
    canvas.save(out)
    print(f"已生成 {out}（{cols}列×{rows}行，{'黑白' if bw else '彩色'}，{found}/{need} 格用了真实图片）")


def cmd_cover(a):
    rw, rh = (int(v) for v in a.ratio.split(":"))
    W = a.width
    H = int(round(W * rh / rw))
    if a.image:
        if not os.path.exists(a.image):
            sys.exit(f"找不到图片：{a.image}")
        img = cover_fit(Image.open(a.image), W, H, (0.5, a.focus_y))
        img = to_bw(img) if a.bw else img
    else:
        img = placeholder(W, H, "封面画面占位", a.placeholder_text or "把生成的图用 --image 传进来", a.bw,
                          at=0.62 if a.position == "top" else 0.25)

    light = a.theme == "light"
    shade = (255, 255, 255) if light else (0, 0, 0)
    ink = (25, 25, 25) if light else (255, 255, 255)
    stroke = (255, 255, 255) if light else (0, 0, 0)
    accent = a.accent

    # 文字区渐变压暗（或提亮），保证小图也看得清片名
    band = int(H * 0.42)
    grad = Image.new("L", (1, band))
    for y in range(band):
        t = y / band
        grad.putpixel((0, y), int(215 * (t ** 1.4)))
    grad = grad.resize((W, band))
    overlay = Image.new("RGB", (W, band), shade)
    if a.position == "top":
        grad = ImageOps.flip(grad)
        img.paste(overlay, (0, 0), grad)
    else:
        img.paste(overlay, (0, H - band), grad)

    d = ImageDraw.Draw(img)
    pad = int(W * 0.07)
    max_w = W - pad * 2

    size = int(W * 0.16)
    while True:
        tf = font(size)
        tlines = wrap(d, a.title, tf, max_w)
        widest = max(text_w(d, ln, tf) for ln in tlines)
        if (len(tlines) <= 2 and widest <= max_w) or size <= 40:
            break
        size -= 4
    if len(tlines) == 2:  # 两行尽量等长，避免“重生回到高/考前一天”
        half = text_w(d, a.title, tf) / 2
        for k in (1.02, 1.08, 1.15, 1.25):
            trial = wrap(d, a.title, tf, half * k)
            if len(trial) == 2 and max(text_w(d, ln, tf) for ln in trial) <= max_w:
                tlines = trial
                break
    tlh = line_h(tf) * 1.05
    sf = font(max(26, W * 0.042))
    slines = wrap(d, a.tagline, sf, max_w) if a.tagline else []
    slh = line_h(sf) * 1.15
    block_h = tlh * len(tlines) + (slh * len(slines) + 18 if slines else 0)

    y = pad * 1.4 if a.position == "top" else H - pad * 1.2 - block_h
    for ln in tlines:
        d.text((W / 2, y), ln, font=tf, fill=ink, anchor="ma",
               stroke_width=max(3, size // 18), stroke_fill=stroke)
        y += tlh
    if slines:
        y += 18
        for ln in slines:
            d.text((W / 2, y), ln, font=sf, fill=accent, anchor="ma",
                   stroke_width=2, stroke_fill=stroke)
            y += slh

    if a.tag:
        gf = font(max(22, W * 0.034))
        gw = text_w(d, a.tag, gf) + 36
        gh = line_h(gf) + 14
        gx, gy = pad * 0.6, pad * 0.6 if a.position == "bottom" else H - pad * 0.6 - gh
        d.rounded_rectangle((gx, gy, gx + gw, gy + gh), radius=gh / 2, fill=accent)
        d.text((gx + gw / 2, gy + gh / 2), a.tag, font=gf, fill="white", anchor="mm")

    out = a.out or "cover.png"
    img.save(out)
    print(f"已生成 {out}（{W}×{H}，比例 {a.ratio}）")


def main():
    global FONT_PATH
    p = argparse.ArgumentParser(description="封面 / 宫格漫画排版")
    p.add_argument("--font", help="中文字体文件路径（默认自动查找）")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cover", help="给封面图叠片名、卖点和题材标签")
    c.add_argument("--image", help="生成好的封面图；省略则用占位图预览排版")
    c.add_argument("--title", required=True)
    c.add_argument("--tagline", default="", help="一句话卖点（副标题）")
    c.add_argument("--tag", default="", help="题材标签，如 女频·复仇")
    c.add_argument("--ratio", default="3:4", help="3:4（默认）、9:16、2:3 等")
    c.add_argument("--width", type=int, default=1080)
    c.add_argument("--position", choices=["top", "bottom"], default="bottom", help="片名放在上方还是下方")
    c.add_argument("--theme", choices=["dark", "light"], default="dark", help="dark=白字压暗，light=黑字提亮")
    c.add_argument("--accent", default="#E8423F", help="卖点和标签的强调色")
    c.add_argument("--focus-y", type=float, default=0.4, help="裁切焦点高度 0—1，默认偏上保住人脸")
    c.add_argument("--bw", action="store_true", help="转成黑白")
    c.add_argument("--placeholder-text", default="")
    c.add_argument("--out")

    m = sub.add_parser("comic", help="按分镜 JSON 排四宫格 / 九宫格 / 竖条漫画")
    m.add_argument("spec", help="分镜 JSON 文件")
    m.add_argument("--layout", help="覆盖 JSON 里的版式，列x行，如 2x2、3x3、1x4")
    m.add_argument("--bw", action="store_true", help="强制黑白")
    m.add_argument("--out")

    s = sub.add_parser("sizes", help="查看版式每格尺寸和建议出图比例")
    s.add_argument("--layout", default="2x2")
    s.add_argument("--width", type=int, default=CANVAS_W)
    s.add_argument("--height", type=int, default=CANVAS_H)

    a = p.parse_args()
    if a.cmd == "sizes":
        return cmd_sizes(a)
    FONT_PATH = find_font(a.font)
    {"cover": cmd_cover, "comic": cmd_comic}[a.cmd](a)


if __name__ == "__main__":
    main()
