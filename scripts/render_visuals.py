#!/usr/bin/env python3
"""把 AI 生成的画面排成封面或竖屏宫格漫画，并负责叠加中文文字。

图像模型写中文容易出错别字，所以片名、对白、旁白、音效字都由本脚本叠加，
出图时只要求“画面里不要有任何文字”。漫画的两套固定画风（彩色 / 黑白）
定义在 references/design.md，本脚本里的 STYLES 与之一一对应。

依赖：Pillow（pip install pillow）+ 中文字体（自动查找系统黑体 / 宋体，或用 --font / --serif-font 指定）。

用法：
    # 封面：图片可省略，省略时生成占位图，用来预览片名排版
    python scripts/render_visuals.py cover --image cover.png --title "配型单上写着无亲缘" \
        --tagline "全家逼我捐肾那天，真相露出来了" --tag "女频·逆袭" --ratio 3:4 --out cover-final.png

    # 漫画：按分镜 JSON 排版（模板见 references/comic-guide.md）
    python scripts/render_visuals.py comic visuals/ep01-comic.json            # JSON 里 mode 决定彩色 / 黑白
    python scripts/render_visuals.py comic visuals/ep01-comic.json --bw       # 强制黑白风格

    # 查看某种版式每一格的像素尺寸和建议出图比例
    python scripts/render_visuals.py layouts                      # 列出自由分格模板
    python scripts/render_visuals.py sizes --layout 4-splash      # 每格尺寸、比例、是否无框
"""
import argparse
import json
import math
import os
import sys

try:
    from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

SANS_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    # Windows
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    # Linux（思源黑体 / Noto Sans CJK）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
SERIF_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Songti.ttc",
    "/System/Library/Fonts/STSong.ttf",
    # Windows
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/STZHONGS.TTF",
    "C:/Windows/Fonts/STSONG.TTF",
    # Linux（思源宋体 / Noto Serif CJK）
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
]

FONT_FILES = {"sans": None, "serif": None}
_FONT_CACHE, _FACE_INDEX, _GLYPH_CACHE = {}, {}, {}

CANVAS_W, CANVAS_H = 1080, 1920
TITLE_BAND, FOOTER_BAND = 150, 90

# 两套固定画风的版式令牌，与 references/design.md 保持一致。
# 分镜 JSON 里可以用 "style": {...} 覆盖其中任意一项。
STYLES = {
    "color": {  # 暖调扁平图像小说风
        "bg": "#FBF3E6",          # 奶油纸色底，格距里露出来
        "ink": "#1F1A17",         # 暖黑：边框、文字、描线
        "border": 5,              # 粗黑格框
        "gutter": 26,
        "margin": 44,
        "text_font": "sans",      # 对白用圆润黑体
        "title_font": "sans",
        "vertical": False,        # 横排对白
        "bubble_line": 3,
        "caption_fill": "#FFFFFF",
        "caption_pos": "top-left",
        "sfx_fill": "#1F1A17",
        "sfx_stroke": "#FFFFFF",
        "rtl": False,
        "placeholder": ["#F2B5A3", "#F7D6B5", "#BCD9EA", "#F4E4A1", "#CDE2CF", "#E9C3D3"],
    },
    "bw": {  # 日式都市恋爱漫画风
        "bg": "#FFFFFF",
        "ink": "#111111",
        "border": 3,              # 细黑格框
        "gutter": 16,
        "margin": 36,
        "text_font": "serif",     # 对白用宋体
        "title_font": "serif",
        "vertical": True,         # 竖排对白，长椭圆气泡
        "bubble_line": 2,
        "caption_fill": "#FFFFFF",
        "caption_pos": "top-right",
        "sfx_fill": "#111111",
        "sfx_stroke": "#FFFFFF",
        "rtl": False,             # true 时同一行从右往左读（日漫原版顺序）
        "placeholder": None,
    },
}

# 竖排时换成竖排标点
VERTICAL_FORMS = {
    "，": "︐", "。": "︒", "、": "︑", "：": "︓", "；": "︔", "！": "︕", "？": "︖",
    "!": "︕", "?": "︖", "…": "︙", "—": "︱", "（": "︵", "）": "︶",
    "「": "﹁", "」": "﹂", "“": "﹁", "”": "﹂", "《": "︽", "》": "︾",
}
NO_LINE_START = set("，。！？、；：”’）》」』…,.!?;:)︐︒︑︓︔︕︖︙︶﹂︾")


# ---------- 字体与文字 ----------

def pick_font(user_path, candidates):
    if user_path:
        if not os.path.exists(user_path):
            sys.exit(f"找不到字体文件：{user_path}")
        return user_path
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def setup_fonts(sans=None, serif=None):
    FONT_FILES["sans"] = pick_font(sans, SANS_CANDIDATES)
    FONT_FILES["serif"] = pick_font(serif, SERIF_CANDIDATES) or FONT_FILES["sans"]
    if not FONT_FILES["sans"]:
        FONT_FILES["sans"] = FONT_FILES["serif"]
    if not FONT_FILES["sans"]:
        sys.exit("没找到中文字体。请安装思源黑体 / Noto Sans CJK，或用 --font 指定 .ttf/.ttc/.otf 文件。")


def face_index(path):
    """.ttc 里有多个字体时，优先简体中文（SC）那一个。"""
    if path in _FACE_INDEX:
        return _FACE_INDEX[path]
    idx = 0
    if path.lower().endswith(".ttc"):
        for i in range(20):
            try:
                name = " ".join(ImageFont.truetype(path, 20, index=i).getname())
            except OSError:
                break
            if " SC" in name or "SC " in name or "GB" in name:
                idx = i
                break
    _FACE_INDEX[path] = idx
    return idx


def font(size, kind="sans"):
    path = FONT_FILES[kind]
    key = (path, int(size))
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size), index=face_index(path))
    return _FONT_CACHE[key]


def has_glyph(f, ch):
    key = (f.path, ch)
    if key not in _GLYPH_CACHE:
        def raster(s):
            im = Image.new("L", (f.size * 2, f.size * 2), 0)
            ImageDraw.Draw(im).text((f.size, f.size), s, font=f, fill=255, anchor="mm")
            return im.tobytes()
        _GLYPH_CACHE[key] = raster(ch) != raster("\U000F0000")  # 和“缺字方框”一样就是没这个字形
    return _GLYPH_CACHE[key]


def text_w(draw, s, f):
    if not s:
        return 0
    l, _, r, _ = draw.textbbox((0, 0), s, font=f)
    return r - l


def line_h(f):
    a, d = f.getmetrics()
    return a + d


def wrap(draw, text, f, max_w):
    """横排：中文按字换行；保留用户写的换行符；避免标点出现在行首。"""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if text_w(draw, cur + ch, f) <= max_w or not cur:
                cur += ch
            elif ch in NO_LINE_START:
                cur += ch  # 标点挂在行尾，宁可略超
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def vertical_columns(text, f, max_h):
    """竖排：按列切分，列从右往左排。返回列（字符列表）的列表。"""
    step = f.size * 1.06
    per_col = max(2, int(max_h // step))
    cols = []
    for para in str(text).split("\n"):
        chars = [VERTICAL_FORMS.get(c, c) if has_glyph(f, VERTICAL_FORMS.get(c, c)) else c for c in para]
        while chars:
            col, chars = chars[:per_col], chars[per_col:]
            while chars and chars[0] in NO_LINE_START:  # 标点不放列首
                col.append(chars.pop(0))
            cols.append(col)
    return cols or [[]]


def vertical_block(cols, f):
    step = f.size * 1.06
    gap = f.size * 0.38
    w = len(cols) * f.size + (len(cols) - 1) * gap
    h = max(len(c) for c in cols) * step
    return w, h, step, gap


def draw_vertical(d, x_right, y_top, cols, f, fill):
    _, _, step, gap = vertical_block(cols, f)
    for i, col in enumerate(cols):
        cx = x_right - f.size / 2 - i * (f.size + gap)
        for j, ch in enumerate(col):
            d.text((cx, y_top + j * step + step / 2), ch, font=f, fill=fill, anchor="mm")


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


def placeholder(w, h, label, desc="", bw=False, at=0.32, fill=None):
    """占位图：彩色风格用平涂色块，黑白风格用网点，一眼看出是占位。"""
    if fill:
        img = Image.new("RGB", (w, h), fill)
        d = ImageDraw.Draw(img)
    elif bw:
        img = Image.new("RGB", (w, h), (255, 255, 255))
        d = ImageDraw.Draw(img)
        for y in range(0, h, 12):
            for x in range((y // 12 % 2) * 6, w, 12):
                d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(200, 200, 200))
    else:
        img = Image.new("RGB", (w, h), (214, 222, 236))
        d = ImageDraw.Draw(img)
        for i in range(-h, w, 28):
            d.line([(i, 0), (i + h, h)], fill=(200, 210, 226), width=2)
    f1 = font(max(20, min(w, h * 0.8) * 0.09))
    d.text((w / 2, h * at), label, font=f1, fill=(90, 90, 90), anchor="mm",
           stroke_width=3, stroke_fill=fill or (255, 255, 255))
    if desc:
        f2 = font(max(14, min(w, h * 0.8) * 0.045))
        lines = wrap(d, desc, f2, w * 0.82)[:8]
        y = h * (at + 0.1)
        for ln in lines:
            d.text((w / 2, y), ln, font=f2, fill=(95, 95, 95), anchor="ma",
                   stroke_width=2, stroke_fill=fill or (255, 255, 255))
            y += line_h(f2) * 1.15
    return img


def load_panel(path, base_dir, w, h, label, desc, bw, focus, fill):
    if path:
        full = path if os.path.isabs(path) else os.path.join(base_dir, path)
        if os.path.exists(full):
            img = cover_fit(Image.open(full), w, h, focus)
            return (to_bw(img) if bw else img), True
        print(f"  · 找不到图片 {path}，先用占位图", file=sys.stderr)
    return placeholder(w, h, label, desc, bw, fill=fill), False


# ---------- 漫画元素 ----------

def bubble_outer(kind, w, h, vertical):
    """文字块尺寸 → 气泡外框尺寸（爆炸气泡和椭圆要留出更多空间）。"""
    if kind == "shout":
        return w * 1.55 + 24, h * 1.75 + 24
    if vertical:
        return w * 1.42 + 18, h * 1.22 + 24
    return w, h


def bubble_shape(d, box, kind, vertical, ow, ink):
    x0, y0, x1, y1 = box
    if kind == "shout":  # 爆炸气泡：爽点、怒吼
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
        pts, n = [], 22
        for i in range(n * 2):
            a = math.pi * i / n
            k = 1.0 if i % 2 == 0 else 0.84
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
        d.polygon(pts, fill="white", outline=ink, width=ow)
    elif vertical:  # 竖排：长椭圆
        d.ellipse(box, fill="white", outline=ink, width=ow)
    else:
        r = min((y1 - y0) / 2, (x1 - x0) / 2) * (1.0 if kind == "thought" else 0.9)
        d.rounded_rectangle(box, radius=r, fill="white", outline=ink, width=ow)


def draw_tail(d, box, cell, kind, vertical, ow, ink):
    """从气泡指向格子中心的尾巴。"""
    if kind == "shout":
        return
    x0, y0, x1, y1 = box
    cx, cy = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    below = cy > my
    if vertical:
        bx = min(max(cx, mx - rx * 0.3), mx + rx * 0.3)
        dy = ry * math.sqrt(max(0.0, 1 - ((bx - mx) / rx) ** 2))
        edge = my + dy if below else my - dy
    else:
        bx = min(max(cx, x0 + 30), x1 - 30)
        edge = y1 if below else y0
    tip = (bx + (cx - bx) * 0.25, edge + (32 if below else -32))
    if kind == "thought":
        for i, r in enumerate((8, 5)):
            t = (i + 1) / 3
            px = bx + (tip[0] - bx) * t
            py = edge + (tip[1] - edge) * t + (6 if below else -6)
            d.ellipse((px - r, py - r, px + r, py + r), fill="white", outline=ink, width=max(2, ow - 1))
        return
    inset = 3 if below else -3
    base = [(bx - 12, edge - inset), (bx + 12, edge - inset)]
    d.polygon(base + [tip], fill="white")
    d.line([base[0], tip, base[1]], fill=ink, width=ow, joint="curve")


def place_box(cell, pos, bw_, bh, pad, stack, vertical):
    """按位置摆放；同一位置的第二个气泡：横排往下叠，竖排往内侧并排（右往左读）。"""
    cx0, cy0, cx1, cy1 = cell
    pos = pos or ("top-right" if vertical else "top-left")
    vert = "bottom" if pos.startswith("bottom") else ("middle" if pos.startswith("middle") else "top")
    horiz = "right" if pos.endswith("right") else ("left" if pos.endswith("left") else "center")
    key = (vert, horiz)
    off = stack.get(key, 0)
    side = vertical and horiz != "center"
    if horiz == "left":
        x = cx0 + pad + (off if side else 0)
    elif horiz == "right":
        x = cx1 - pad - bw_ - (off if side else 0)
    else:
        x = (cx0 + cx1 - bw_) / 2
    yoff = 0 if side else off
    if vert == "top":
        y = cy0 + pad + yoff
    elif vert == "bottom":
        y = cy1 - pad - bh - yoff
    else:
        y = (cy0 + cy1 - bh) / 2 + yoff
    stack[key] = off + (bw_ if side else bh) + pad * 0.6
    # 不让气泡越出格子
    x = min(max(x, cx0 + 4), cx1 - 4 - bw_) if bw_ < cx1 - cx0 - 8 else cx0 + 4
    y = min(max(y, cy0 + 4), cy1 - 4 - bh) if bh < cy1 - cy0 - 8 else cy0 + 4
    return (x, y, x + bw_, y + bh)


def avoid_overlap(box, placed, cell, pad):
    """和同一格里已经放好的气泡重叠时，往下（下半格的往上）挪开；挪不开就保持原位。"""
    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    x0, y0, x1, y1 = box
    h = y1 - y0
    down = (y0 + y1) / 2 < (cell[1] + cell[3]) / 2
    for _ in range(len(placed) + 1):
        other = next((o for o in placed if hit((x0, y0, x1, y1), o)), None)
        if not other:
            break
        y0 = other[3] + pad * 0.5 if down else other[1] - pad * 0.5 - h
        if y0 < cell[1] or y0 + h > cell[3]:
            return box
        y1 = y0 + h
    return (x0, y0, x1, y1)


def draw_dialogue(canvas, cell, items, base_size, stack, st):
    d = ImageDraw.Draw(canvas)
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    pad = max(10, cw * 0.035)
    vertical, ink = st["vertical"], st["ink"]
    placed = stack.setdefault("_placed", [])
    for it in items:
        kind = it.get("type", "speech")
        text = it.get("text", "").strip()
        if not text:
            continue
        f = font(base_size * (1.1 if kind == "shout" else 1.0), st["text_font"])
        if vertical:
            cols = vertical_columns(text, f, ch * 0.27)
            tw, th, _, _ = vertical_block(cols, f)
        else:
            lines = wrap(d, text, f, cw * (0.36 if kind == "shout" else 0.56))  # 爆炸气泡外圈更大，文字收窄
            lh = line_h(f) * 1.12
            tw, th = max(text_w(d, ln, f) for ln in lines), lh * len(lines)
            tw, th = tw + f.size * 1.5, th + f.size
        ow_, oh_ = bubble_outer(kind, tw, th, vertical)
        box = place_box(cell, it.get("pos"), ow_, oh_, pad, stack, vertical)
        box = avoid_overlap(box, placed, cell, pad)
        placed.append(box)
        bubble_shape(d, box, kind, vertical, st["bubble_line"], ink)
        draw_tail(d, box, cell, kind, vertical, st["bubble_line"], ink)
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if vertical:
            draw_vertical(d, mx + tw / 2, my - th / 2, cols, f, ink)
        else:
            y = my - lh * len(lines) / 2
            for ln in lines:
                d.text((mx, y), ln, font=f, fill=ink, anchor="ma")
                y += lh


def draw_caption(canvas, cell, text, base_size, st):
    """旁白框：贴在格子角上。横排写在左上；竖排写在右上，和日漫一样。"""
    d = ImageDraw.Draw(canvas)
    f = font(base_size * 0.82, st["text_font"])
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    p = base_size * 0.4
    right = st["caption_pos"].endswith("right")
    if st["vertical"]:
        cols = vertical_columns(text, f, ch * 0.38)
        tw, th, _, _ = vertical_block(cols, f)
    else:
        lines = wrap(d, text, f, cw * 0.7)
        lh = line_h(f) * 1.1
        tw, th = max(text_w(d, ln, f) for ln in lines), lh * len(lines)
    bw_, bh = tw + p * 2, th + p * 2
    x0 = cell[2] - bw_ if right else cell[0]
    box = (x0, cell[1], x0 + bw_, cell[1] + bh)
    d.rectangle(box, fill=st["caption_fill"], outline=st["ink"], width=max(2, st["border"] - 1))
    if st["vertical"]:
        draw_vertical(d, box[2] - p, box[1] + p, cols, f, st["ink"])
    else:
        y = box[1] + p
        for ln in lines:
            d.text((box[0] + p, y), ln, font=f, fill=st["ink"])
            y += lh
    return (bw_ if st["vertical"] else bh), ("right" if right else "left")


def draw_sfx(canvas, cell, sfx, base_size, st):
    """音效字：大号描边手写感字体，略微倾斜。"""
    text = sfx.get("text") if isinstance(sfx, dict) else str(sfx)
    pos = sfx.get("pos", "middle-right") if isinstance(sfx, dict) else "middle-right"
    fill = sfx.get("color", st["sfx_fill"]) if isinstance(sfx, dict) else st["sfx_fill"]
    if not text:
        return
    size = base_size * 2.0
    f = font(size, "sans")
    tmp = ImageDraw.Draw(canvas)
    tw = text_w(tmp, text, f) + 30
    th = line_h(f) + 30
    layer = Image.new("RGBA", (int(tw), int(th)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((15, 10), text, font=f, fill=fill, stroke_width=max(3, int(size / 12)), stroke_fill=st["sfx_stroke"])
    layer = layer.rotate(8, expand=True, resample=Image.BICUBIC)
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

# 自由分格模板（彩色风格的默认版式），坐标是内容区的比例 [x0, y0, x1, y1]。
# 列表顺序 = 阅读顺序。kind：box 有框格；free 无框大格（画面羽化融进底色）；inset 压在别的格子上的插入小格。
# fx：speed 加放射速度线。
TEMPLATES = {
    "4-hero": {
        "name": "主角大格",
        "use": "四格：全景 → 两格推进 → 无框大格放主角的反应脸。结尾是一张震惊 / 决绝的脸时用",
        "panels": [
            ([0, 0, 1, .24], "box", None),
            ([0, .24, .42, .50], "box", None),
            ([.42, .24, 1, .50], "box", None),
            ([0, .50, 1, 1], "free", None),
        ],
    },
    "4-splash": {
        "name": "动作爆发",
        "use": "四格：三个小格蓄力 → 无框大格 + 速度线放动作。结尾是一个动作（巴掌、摔门、冲出去）时用",
        "panels": [
            ([0, 0, 1 / 3, .28], "box", None),
            ([1 / 3, 0, 2 / 3, .28], "box", None),
            ([2 / 3, 0, 1, .28], "box", None),
            ([0, .28, 1, 1], "free", "speed"),
        ],
    },
    "4-inset": {
        "name": "插入特写",
        "use": "四格：两格 → 大场景格 → 压在大格角上的特写小格。结尾是一个物件或一句话的揭露时用",
        "panels": [
            ([0, 0, .58, .32], "box", None),
            ([.58, 0, 1, .32], "box", None),
            ([0, .32, 1, 1], "box", None),
            ([.05, .63, .52, .95], "inset", None),
        ],
    },
    "9-hero": {
        "name": "情绪大格",
        "use": "九格：全景 → 两格 → 中间无框主角大格，左右压着三个特写小格 → 横条 → 宽格钩子。情绪戏为主时用",
        "panels": [
            ([0, 0, 1, .15], "box", None),
            ([0, .15, .40, .33], "box", None),
            ([.40, .15, 1, .33], "box", None),
            ([0, .345, .29, .50], "inset", None),
            ([0, .515, .29, .67], "inset", None),
            ([0, .33, 1, .69], "free", None),
            ([.71, .345, 1, .67], "inset", None),
            ([0, .69, 1, .81], "box", None),
            ([0, .81, 1, 1], "box", None),
        ],
    },
    "9-splash": {
        "name": "动作九格",
        "use": "九格：三小格 → 大小错落三格 → 无框动作大格 + 速度线 → 插入特写 → 宽格钩子。动作戏为主时用",
        "panels": [
            ([0, 0, 1 / 3, .17], "box", None),
            ([1 / 3, 0, 2 / 3, .17], "box", None),
            ([2 / 3, 0, 1, .17], "box", None),
            ([0, .17, .62, .42], "box", None),
            ([.62, .17, 1, .295], "box", None),
            ([.62, .295, 1, .42], "box", None),
            ([0, .42, 1, .72], "free", "speed"),
            ([.04, .685, .44, .83], "inset", None),
            ([0, .72, 1, 1], "box", None),
        ],
    },
}
KIND_LABEL = {"box": "", "free": " · 无框", "inset": " · 插入小格"}


def parse_grid(s):
    try:
        cols, rows = (int(v) for v in s.lower().replace("×", "x").split("x"))
        assert 1 <= cols <= 4 and 1 <= rows <= 6
        return cols, rows
    except Exception:
        names = "、".join(TEMPLATES)
        sys.exit(f"版式写法：自由分格模板（{names}），或规整网格 列x行（如 2x2、3x3、1x4），收到：{s}")


def layout_panels(layout, W, H, has_title, has_footer, st):
    """返回 [{box, kind, fx}]，顺序即阅读顺序。"""
    m, g = st["margin"], st["gutter"]
    top = m + (TITLE_BAND if has_title else 0)
    bottom = H - m - (FOOTER_BAND if has_footer else 0)
    if layout in TEMPLATES:
        X0, Y0, CW, CH = m, top, W - 2 * m, bottom - top
        out = []
        for (fx0, fy0, fx1, fy1), kind, fx in TEMPLATES[layout]["panels"]:
            if st["rtl"]:
                fx0, fx1 = 1 - fx1, 1 - fx0
            x0, y0, x1, y1 = X0 + fx0 * CW, Y0 + fy0 * CH, X0 + fx1 * CW, Y0 + fy1 * CH
            if kind != "inset":  # 有框格和无框格之间留格距；外边缘对齐页边
                x0 += g / 2 if fx0 > 0 else 0
                y0 += g / 2 if fy0 > 0 else 0
                x1 -= g / 2 if fx1 < 1 else 0
                y1 -= g / 2 if fy1 < 1 else 0
            out.append({"box": tuple(int(round(v)) for v in (x0, y0, x1, y1)), "kind": kind, "fx": fx})
        return out
    cols, rows = parse_grid(layout)
    cw = (W - 2 * m - (cols - 1) * g) / cols
    ch = (bottom - top - (rows - 1) * g) / rows
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            x, y = m + c * (cw + g), top + r * (ch + g)
            row.append({"box": tuple(int(round(v)) for v in (x, y, x + cw, y + ch)), "kind": "box", "fx": None})
        out += row[::-1] if st["rtl"] else row
    return out


def nearest_ratio(w, h):
    options = ["1:1", "2:3", "3:4", "3:5", "9:16", "4:3", "3:2", "16:9", "21:9"]
    return min(options, key=lambda r: abs(math.log((w / h) / (int(r.split(":")[0]) / int(r.split(":")[1])))))


def resolve_style(mode, overrides=None):
    st = dict(STYLES["bw" if mode == "bw" else "color"])
    st.update(overrides or {})
    return st


def mix(c1, c2, t):
    a, b = ImageColor.getrgb(c1), ImageColor.getrgb(c2)
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def paste_free(canvas, img, box):
    """无框格：四边羽化，画面像直接画在纸上。"""
    w, h = box[2] - box[0], box[3] - box[1]
    f = int(min(w, h) * 0.07)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rectangle((f, f, w - f, h - f), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(f / 2))
    canvas.paste(img, box[:2], mask)


def draw_speedlines(canvas, box, ink):
    """放射速度线：从格子边缘往中心收，中间留给人物。"""
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    n = 36
    for k in range(n):
        a = 2 * math.pi * k / n + 0.07 * math.sin(k * 2.3)
        dx, dy = math.cos(a), math.sin(a)
        tx = ((x1 - cx) / dx if dx > 0 else (x0 - cx) / dx) if abs(dx) > 1e-6 else 1e9
        ty = ((y1 - cy) / dy if dy > 0 else (y0 - cy) / dy) if abs(dy) > 1e-6 else 1e9
        r_edge = min(tx, ty)
        r_in = r_edge * (0.62 + 0.18 * ((k * 7) % 5) / 4)
        half = 2.5 + (k % 3) * 1.5
        px, py = -dy, dx
        ox, oy = cx + dx * r_edge, cy + dy * r_edge
        d.polygon([(ox + px * half, oy + py * half), (ox - px * half, oy - py * half),
                   (cx + dx * r_in, cy + dy * r_in)], fill=ink)


def panel_size_text(i, p):
    x0, y0, x1, y1 = p["box"]
    return f"格 {i}｜{x1 - x0}×{y1 - y0}｜建议比例 {nearest_ratio(x1 - x0, y1 - y0)}{KIND_LABEL[p['kind']]}" + \
        ("｜加速度线" if p["fx"] == "speed" else "")


def cmd_layouts(a):
    print("自由分格模板（彩色风格默认用这些，规整网格写 2x2、3x3、1x4）：")
    for k, t in TEMPLATES.items():
        print(f"  {k:9s} {t['name']}：{t['use']}")


def cmd_sizes(a):
    st = resolve_style(a.mode)
    panels = layout_panels(a.layout, a.width, a.height, True, True, st)
    print(f"版式 {a.layout}，{'黑白' if a.mode == 'bw' else '彩色'}风格，画布 {a.width}×{a.height}，共 {len(panels)} 格")
    for i, p in enumerate(panels, 1):
        print("  " + panel_size_text(i, p))
    print("脚本会自动裁切，比例接近即可。无框格请让画面背景简洁（纯色或浅色），边缘会羽化融进底色。")


def cmd_comic(a):
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(a.spec))
    mode = "bw" if (a.bw or spec.get("mode", "color") == "bw") else "color"
    bw = mode == "bw"
    st = resolve_style(mode, spec.get("style"))
    layout = a.layout or spec.get("layout") or ("4-inset" if not bw else "2x2")
    W, H = spec.get("canvas", [CANVAS_W, CANVAS_H])
    title, footer = spec.get("title", ""), spec.get("footer", "")
    slots = layout_panels(layout, W, H, bool(title), bool(footer), st)
    panels = spec.get("panels", [])
    need = len(slots)
    if len(panels) != need:
        print(f"  · 版式 {layout} 需要 {need} 格，分镜里有 {len(panels)} 格；多的忽略，少的补占位", file=sys.stderr)
        panels = (panels + [{}] * need)[:need]

    canvas = Image.new("RGB", (W, H), st["bg"])
    d = ImageDraw.Draw(canvas)
    if title:
        f = font(56, st["title_font"])
        while text_w(d, title, f) > W - 2 * st["margin"] and f.size > 28:
            f = font(f.size - 2, st["title_font"])
        d.text((W / 2, st["margin"] + TITLE_BAND / 2 - 8), title, font=f, fill=st["ink"], anchor="mm")

    palette = st.get("placeholder")
    items = list(enumerate(zip(slots, panels), 1))
    zorder = {"free": 0, "box": 1, "inset": 2}
    items.sort(key=lambda it: zorder[it[1][0]["kind"]])  # 先铺无框大格，再有框格，最后插入小格
    found = 0

    for i, (slot, p) in items:  # 第一遍：画面和格框
        box, kind = slot["box"], slot["kind"]
        w, h = box[2] - box[0], box[3] - box[1]
        fill = palette[(i - 1) % len(palette)] if palette else None
        if kind == "free" and fill:
            fill = mix(fill, st["bg"], 0.45)
        label = f"格 {i} · {nearest_ratio(w, h)}{KIND_LABEL[kind]}"
        img, ok = load_panel(p.get("image"), base_dir, w, h, label, p.get("scene", ""), bw,
                             tuple(p.get("focus", (0.5, 0.5))), fill)
        found += ok
        if kind == "free":
            paste_free(canvas, img, box)
            if slot["fx"] == "speed" or p.get("speedlines"):
                draw_speedlines(canvas, box, st["ink"])
            continue
        if kind == "inset":  # 插入小格外圈留一道底色，像贴在大格上
            ring = st["gutter"] * 0.6
            d.rectangle((box[0] - ring, box[1] - ring, box[2] + ring, box[3] + ring), fill=st["bg"])
        canvas.paste(img, box[:2])
        if p.get("speedlines"):
            draw_speedlines(canvas, box, st["ink"])
        d.rectangle(box, outline=st["ink"], width=st["border"])

    for i, (slot, p) in items:  # 第二遍：文字压在所有画面上面
        box = slot["box"]
        w, h = box[2] - box[0], box[3] - box[1]
        base_size = min(38, max(21, min(w, h * 0.9) * 0.075))
        stack = {}
        if p.get("caption"):
            size_, side = draw_caption(canvas, box, p["caption"], base_size, st)
            if st["vertical"]:
                stack[("top", side)] = size_ + 4
            else:
                for hz in ("left", "center", "right"):
                    stack[("top", hz)] = size_ + 6
        if p.get("sfx"):
            draw_sfx(canvas, box, p["sfx"], base_size, st)
        draw_dialogue(canvas, box, p.get("dialogue", []), base_size, stack, st)

    if footer:
        f = font(38, st["title_font"])
        d.text((W / 2, H - st["margin"] - FOOTER_BAND / 2 + 6), footer, font=f, fill=st["ink"], anchor="mm")

    out = a.out or os.path.splitext(a.spec)[0] + ".png"
    canvas.save(out)
    print(f"已生成 {out}（版式 {layout}，{'黑白' if bw else '彩色'}风格，{found}/{need} 格用了真实图片）")


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
        grad.putpixel((0, y), int(215 * ((y / band) ** 1.4)))
    grad = grad.resize((W, band))
    overlay = Image.new("RGB", (W, band), shade)
    if a.position == "top":
        img.paste(overlay, (0, 0), ImageOps.flip(grad))
    else:
        img.paste(overlay, (0, H - band), grad)

    d = ImageDraw.Draw(img)
    pad = int(W * 0.07)
    max_w = W - pad * 2
    kind = a.title_font

    size = int(W * 0.16)
    while True:
        tf = font(size, kind)
        tlines = wrap(d, a.title, tf, max_w)
        widest = max(text_w(d, ln, tf) for ln in tlines)
        if (len(tlines) <= 2 and widest <= max_w) or size <= 40:
            break
        size -= 4
    if len(tlines) == 2:  # 两行尽量等长
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
            d.text((W / 2, y), ln, font=sf, fill=accent, anchor="ma", stroke_width=2, stroke_fill=stroke)
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
    p = argparse.ArgumentParser(description="封面 / 宫格漫画排版")
    p.add_argument("--font", help="黑体字体文件路径（默认自动查找）")
    p.add_argument("--serif-font", help="宋体字体文件路径，黑白漫画对白用（默认自动查找）")
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
    c.add_argument("--title-font", choices=["sans", "serif"], default="sans", help="片名用黑体或宋体")
    c.add_argument("--accent", default="#E8423F", help="卖点和标签的强调色")
    c.add_argument("--focus-y", type=float, default=0.4, help="裁切焦点高度 0—1，默认偏上保住人脸")
    c.add_argument("--bw", action="store_true", help="转成黑白")
    c.add_argument("--placeholder-text", default="")
    c.add_argument("--out")

    m = sub.add_parser("comic", help="按分镜 JSON 排四宫格 / 九宫格 / 竖条漫画")
    m.add_argument("spec", help="分镜 JSON 文件")
    m.add_argument("--layout", help="覆盖 JSON 里的版式：自由分格模板（4-hero、4-splash、4-inset、9-hero、9-splash）或网格 2x2、3x3、1x4")
    m.add_argument("--bw", action="store_true", help="强制黑白风格")
    m.add_argument("--out")

    sub.add_parser("layouts", help="列出自由分格模板和适用场景")

    s = sub.add_parser("sizes", help="查看版式每格尺寸、建议出图比例和格子类型")
    s.add_argument("--layout", default="4-inset")
    s.add_argument("--mode", choices=["color", "bw"], default="color")
    s.add_argument("--width", type=int, default=CANVAS_W)
    s.add_argument("--height", type=int, default=CANVAS_H)

    a = p.parse_args()
    if a.cmd == "sizes":
        return cmd_sizes(a)
    if a.cmd == "layouts":
        return cmd_layouts(a)
    setup_fonts(a.font, a.serif_font)
    {"cover": cmd_cover, "comic": cmd_comic}[a.cmd](a)


if __name__ == "__main__":
    main()
