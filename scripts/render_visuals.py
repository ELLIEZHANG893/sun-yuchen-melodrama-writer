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
    python scripts/render_visuals.py comic visuals/ep01-pages.json            # 多页：输出 ep01-pages-01.png、-02.png……
    python scripts/render_visuals.py comic visuals/ep01-pages.json --page 3 --strip

    # 查看某种版式每一格的像素尺寸和建议出图比例
    python scripts/render_visuals.py layouts                      # 列出自由分格模板
    python scripts/render_visuals.py sizes --layout 4-splash      # 每格尺寸、比例、是否无框
"""
import argparse
import json
import re
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
MEDIUM_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",               # 选 PingFang SC Medium
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
# 随 skill 一起分发的开源字体（OFL）：站酷快乐体，用于音效字和旁白，手写感、活泼
DISPLAY_CANDIDATES = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts",
                                   "ZCOOLKuaiLe-Regular.ttf")]
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

FONT_FILES = {"sans": None, "serif": None, "medium": None, "display": None}
FACE_WANT = {"medium": "Medium"}
_FONT_CACHE, _FACE_INDEX, _GLYPH_CACHE = {}, {}, {}

CANVAS_W, CANVAS_H = 1080, 1920
TITLE_BAND, FOOTER_BAND = 150, 90

# 两套固定画风的版式令牌，与 references/design.md 保持一致。
# 分镜 JSON 里可以用 "style": {...} 覆盖其中任意一项。
STYLES = {
    "color": {  # 暖调扁平图像小说风
        "bg": "#FBF3E6",          # 奶油纸色底，格距里露出来
        "ink": "#4A3A30",         # 暖深棕：格框、气泡线（参考图是细的深棕线，不是纯黑粗线）
        "text": "#2F2722",        # 对白文字：深棕灰，不用纯黑
        "border": 2.5,            # 细格框
        "gutter": 22,
        "margin": 40,
        "text_font": "medium",    # 对白用中等字重的黑体，不用粗体
        "title_font": "display",  # 标题、页码用手写感字体
        "caption_font": "display",
        "sfx_font": "display",
        "title_size": 40,
        "vertical": False,        # 横排对白
        "bubble": "oval",         # 椭圆气泡
        "bubble_line": 2,
        "speed_weight": 0.5,      # 速度线细一些
        "caption_fill": "#FFFDF8",
        "caption_pos": "top-left",
        "sfx_fill": "#3B2E27",
        "sfx_stroke": "#FFFFFF",
        "rtl": False,
        "placeholder": ["#F2B5A3", "#F7D6B5", "#BCD9EA", "#F4E4A1", "#CDE2CF", "#E9C3D3"],
    },
    "bw": {  # 日式都市恋爱漫画风
        "bg": "#FFFFFF",
        "ink": "#111111",
        "text": "#111111",
        "border": 3,              # 细黑格框
        "title_size": 44,
        "caption_font": "serif",
        "sfx_font": "display",
        "speed_weight": 0.8,
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
    FONT_FILES["medium"] = pick_font(None, MEDIUM_CANDIDATES) or FONT_FILES["sans"]
    FONT_FILES["display"] = pick_font(None, DISPLAY_CANDIDATES) or FONT_FILES["sans"]


def face_index(path, want=None):
    """.ttc 里有多个字体时，优先简体中文（SC）那一个；want 指定字重（如 Medium）。"""
    key = (path, want)
    if key in _FACE_INDEX:
        return _FACE_INDEX[key]
    idx, fallback = 0, None
    if path.lower().endswith(".ttc"):
        for i in range(30):
            try:
                name = " ".join(ImageFont.truetype(path, 20, index=i).getname())
            except OSError:
                break
            sc = " SC" in name or "SC " in name or "GB" in name
            if sc and fallback is None:
                fallback = i
            if sc and (not want or want in name):
                idx = i
                break
        else:
            idx = fallback or 0
        if fallback is not None and idx == 0 and want:
            idx = fallback
    _FACE_INDEX[key] = idx
    return idx


def font(size, kind="sans"):
    path = FONT_FILES.get(kind) or FONT_FILES["sans"]
    key = (path, int(size), kind)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size), index=face_index(path, FACE_WANT.get(kind)))
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


def draw_vertical(d, x_right, y_top, cols, f, fill, stroke=0, stroke_fill="white"):
    _, _, step, gap = vertical_block(cols, f)
    for i, col in enumerate(cols):
        cx = x_right - f.size / 2 - i * (f.size + gap)
        for j, ch in enumerate(col):
            d.text((cx, y_top + j * step + step / 2), ch, font=f, fill=fill, anchor="mm",
                   stroke_width=stroke, stroke_fill=stroke_fill)


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

def bubble_outer(kind, w, h, vertical, oval=False):
    """文字块尺寸 → 气泡外框尺寸（爆炸气泡和椭圆要留出更多空间）。"""
    if kind == "shout":
        return w * 1.55 + 24, h * 1.75 + 24
    if vertical:
        return w * 1.42 + 18, h * 1.22 + 24
    if oval:
        return w * 1.22 + 12, h * 1.38 + 10
    return w, h


def bubble_shape(d, box, kind, vertical, ow, ink, oval=False):
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
    elif vertical or oval:  # 竖排长椭圆 / 彩色风格的椭圆气泡
        d.ellipse(box, fill="white", outline=ink, width=ow)
    else:
        r = min((y1 - y0) / 2, (x1 - x0) / 2) * (1.0 if kind == "thought" else 0.9)
        d.rounded_rectangle(box, radius=r, fill="white", outline=ink, width=ow)


def draw_tail(d, box, cell, kind, vertical, ow, ink, target=None, oval=False):
    """从气泡指向说话人的尾巴；没给 target 时指向格子中心。"""
    if kind == "shout":
        return
    x0, y0, x1, y1 = box
    cx, cy = target or ((cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    below = cy > my
    if vertical or oval:
        bx = min(max(cx, mx - rx * 0.3), mx + rx * 0.3)
        dy = ry * math.sqrt(max(0.0, 1 - ((bx - mx) / rx) ** 2))
        edge = my + dy if below else my - dy
    else:
        bx = min(max(cx, x0 + 30), x1 - 30)
        edge = y1 if below else y0
    tip = (bx + (cx - bx) * 0.25, edge + ((26 if oval else 32) if below else -(26 if oval else 32)))
    if kind == "thought":
        for i, r in enumerate((8, 5)):
            t = (i + 1) / 3
            px = bx + (tip[0] - bx) * t
            py = edge + (tip[1] - edge) * t + (6 if below else -6)
            d.ellipse((px - r, py - r, px + r, py + r), fill="white", outline=ink, width=max(2, ow - 1))
        return
    inset = 3 if below else -3
    half_w = 8 if oval else 12
    base = [(bx - half_w, edge - inset), (bx + half_w, edge - inset)]
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


def draw_monologue(d, cell, text, base_size, st, stack, placed, pad, pos, at=None):
    f = font(base_size * 1.15, "sans")
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    stroke = max(3, int(f.size / 7))
    if st["vertical"]:
        cols = vertical_columns(text, f, ch * 0.4)
        tw, th, _, _ = vertical_block(cols, f)
    else:
        lines = wrap(d, text, f, cw * 0.6)
        lh = line_h(f) * 1.1
        tw, th = max(text_w(d, ln, f) for ln in lines), lh * len(lines)
    bw_, bh = tw + stroke * 2, th + stroke * 2
    if at:
        box = at_box(cell, at, bw_, bh)
    else:
        box = place_box(cell, pos or "middle-left", bw_, bh, pad, stack, st["vertical"])
        box = avoid_overlap(box, placed, cell, pad)
    placed.append(box)
    if st["vertical"]:
        draw_vertical(d, box[2] - stroke, box[1] + stroke, cols, f, st["ink"], stroke, "white")
    else:
        y = box[1] + stroke
        for ln in lines:
            d.text((box[0] + stroke, y), ln, font=f, fill=st["ink"], stroke_width=stroke, stroke_fill="white")
            y += lh


def frac_point(cell, fp):
    if not fp:
        return None
    return (cell[0] + (cell[2] - cell[0]) * fp[0], cell[1] + (cell[3] - cell[1]) * fp[1])


def at_box(cell, at, w, h):
    cx, cy = frac_point(cell, at)
    x = min(max(cx - w / 2, cell[0] + 4), cell[2] - 4 - w)
    y = min(max(cy - h / 2, cell[1] + 4), cell[3] - 4 - h)
    return (x, y, x + w, y + h)


def clear_of_face(box, face, cell, pad):
    """face 是说话人脸部区域（格子内比例坐标 [x0, y0, x1, y1]）。气泡最多盖住脸的 30%；超过就往远离脸的方向挪。"""
    if not face:
        return box
    fx0, fy0 = cell[0] + (cell[2] - cell[0]) * face[0], cell[1] + (cell[3] - cell[1]) * face[1]
    fx1, fy1 = cell[0] + (cell[2] - cell[0]) * face[2], cell[1] + (cell[3] - cell[1]) * face[3]
    farea = max(1, (fx1 - fx0) * (fy1 - fy0))

    def cover(b):
        x0, y0, x1, y1 = max(b[0], fx0), max(b[1], fy0), min(b[2], fx1), min(b[3], fy1)
        return max(0, x1 - x0) * max(0, y1 - y0) / farea

    if cover(box) <= 0.3:
        return box
    w, h = box[2] - box[0], box[3] - box[1]
    cands = [(fx0 - pad - w, box[1]), (fx1 + pad, box[1]), (box[0], fy0 - pad - h), (box[0], fy1 + pad)]
    best = box
    for x, y in cands:
        x = min(max(x, cell[0] + 4), cell[2] - 4 - w)
        y = min(max(y, cell[1] + 4), cell[3] - 4 - h)
        b = (x, y, x + w, y + h)
        if cover(b) < cover(best):
            best = b
    return best


def draw_dialogue(canvas, cell, items, base_size, stack, st):
    d = ImageDraw.Draw(canvas)
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    pad = max(10, cw * 0.035)
    vertical, ink = st["vertical"], st["ink"]
    txt = st.get("text", ink)
    oval = st.get("bubble") == "oval" and not vertical
    placed = stack.setdefault("_placed", [])
    for it in items:
        kind = it.get("type", "speech")
        text = it.get("text", "").strip()
        if not text:
            continue
        if kind == "monologue":  # 浮空独白：没有气泡和框，粗一点的字加白描边，直接浮在人物旁边
            draw_monologue(d, cell, text, base_size, st, stack, placed, pad, it.get("pos"), it.get("at"))
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
        ow_, oh_ = bubble_outer(kind, tw, th, vertical, oval)
        if it.get("at"):  # 精确位置：气泡中心在格子内的比例坐标
            box = at_box(cell, it["at"], ow_, oh_)
        else:
            box = place_box(cell, it.get("pos"), ow_, oh_, pad, stack, vertical)
            box = avoid_overlap(box, placed, cell, pad)
        box = clear_of_face(box, it.get("face"), cell, pad)
        placed.append(box)
        bubble_shape(d, box, kind, vertical, st["bubble_line"], ink, oval)
        draw_tail(d, box, cell, kind, vertical, st["bubble_line"], ink, frac_point(cell, it.get("tail")), oval)
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if vertical:
            draw_vertical(d, mx + tw / 2, my - th / 2, cols, f, txt)
        else:
            y = my - lh * len(lines) / 2
            for ln in lines:
                d.text((mx, y), ln, font=f, fill=txt, anchor="ma")
                y += lh


def draw_caption(canvas, cell, text, base_size, st):
    """旁白框：贴在格子角上。横排写在左上；竖排写在右上，和日漫一样。"""
    d = ImageDraw.Draw(canvas)
    f = font(base_size * 0.86, st.get("caption_font", st["text_font"]))
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
    d.rectangle(box, fill=st["caption_fill"], outline=st["ink"], width=max(1, int(st["border"] - 0.5)))
    if st["vertical"]:
        draw_vertical(d, box[2] - p, box[1] + p, cols, f, st["ink"])
    else:
        y = box[1] + p
        for ln in lines:
            d.text((box[0] + p, y), ln, font=f, fill=st.get("text", st["ink"]))
            y += lh
    return (bw_ if st["vertical"] else bh), ("right" if right else "left")


def draw_sfx(canvas, cell, sfx, base_size, st):
    """音效字：手写感字体，一个字一个字地错落、旋转、大小不一，像手绘拟声词。"""
    text = sfx.get("text") if isinstance(sfx, dict) else str(sfx)
    pos = sfx.get("pos", "middle-right") if isinstance(sfx, dict) else "middle-right"
    fill = sfx.get("color", st["sfx_fill"]) if isinstance(sfx, dict) else st["sfx_fill"]
    if not text:
        return
    size = base_size * 2.1
    chars = [c for c in text if c.strip()]
    pieces = []
    for k, c in enumerate(chars):
        f = font(size * (1.12 if k == 0 else (0.92 + 0.12 * ((k * 7) % 3) / 2)), st.get("sfx_font", "sans"))
        w_ = int(f.size * 1.5)
        lay = Image.new("RGBA", (w_, w_), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((w_ / 2, w_ / 2), c, font=f, fill=fill, anchor="mm",
                                 stroke_width=max(3, int(f.size / 10)), stroke_fill=st["sfx_stroke"])
        angle = (-12, 9, -5, 12, -8)[k % 5]
        pieces.append(lay.rotate(angle, expand=True, resample=Image.BICUBIC))
    step = size * 0.82
    tw = int(step * (len(pieces) - 1) + max(p.width for p in pieces))
    th = int(max(p.height for p in pieces) + size * 0.5)
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    for k, pc in enumerate(pieces):
        dy = int(size * (0.0, 0.22, 0.05, 0.3, 0.12)[k % 5])
        layer.paste(pc, (int(k * step), dy), pc)
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

# 自由分格模板，坐标是内容区的比例：矩形写 [x0, y0, x1, y1]，斜切格写多边形 [(x, y), ...]（顺时针，必须是凸多边形）。
# 列表顺序 = 阅读顺序。kind：box 有框格；free 无框大格（画面羽化融进底色）；inset 压在别的格子上的插入小格。
# fx：speed 加放射速度线。4-*/9-* 是彩色风格的模板，m4-*/m9-* 是黑白日漫风格的模板（斜切分格）。
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
    # ----- 黑白日漫：斜切分格 -----
    "m4-closeup": {
        "name": "大脸对话",
        "use": "黑白四格：无框大脸特写 + 全身格 → 下方两张脸被斜线切开。两人对话、试探、表情反转时用",
        "panels": [
            ([0, 0, .60, .50], "free", None),
            ([.60, 0, 1, .50], "box", None),
            ([(0, .50), (.53, .50), (.46, 1), (0, 1)], "box", None),
            ([(.53, .50), (1, .50), (1, 1), (.46, 1)], "box", None),
        ],
    },
    "m4-embrace": {
        "name": "双人大格",
        "use": "黑白四格：特写 + 斜切动作格 → 无框双人大场景，角上压一个反应特写。拥抱、对峙、靠近时用",
        "panels": [
            ([0, 0, .44, .55], "box", None),
            ([(.44, 0), (1, 0), (1, .49), (.44, .55)], "box", None),
            ([0, .55, 1, 1], "free", None),
            ([.60, .58, .97, .80], "inset", None),
        ],
    },
    "m4-confess": {
        "name": "告白大脸",
        "use": "黑白四格：宽场景 → 两格斜切推进 → 无框大脸收尾。告白、拒绝、崩溃、狠话这类结尾是一张脸时用",
        "panels": [
            ([0, 0, 1, .36], "box", None),
            ([(0, .36), (.56, .36), (.49, .60), (0, .60)], "box", None),
            ([(.56, .36), (1, .36), (1, .60), (.49, .60)], "box", None),
            ([0, .60, 1, 1], "free", "speed"),
        ],
    },
    "m9-page": {
        "name": "日漫整页",
        "use": "黑白九格：斜底宽格 → 三格斜切 → 无框大脸 + 两小格 → 两格斜切收尾。九格默认",
        "panels": [
            ([(0, 0), (1, 0), (1, .14), (0, .17)], "box", None),
            ([(0, .17), (.36, .1592), (.30, .36), (0, .36)], "box", None),
            ([(.36, .1592), (.70, .149), (.66, .36), (.30, .36)], "box", None),
            ([(.70, .149), (1, .14), (1, .36), (.66, .36)], "box", None),
            ([0, .36, .62, .70], "free", None),
            ([.62, .36, 1, .53], "box", None),
            ([.62, .53, 1, .70], "box", None),
            ([(0, .70), (.45, .70), (.39, 1), (0, 1)], "box", None),
            ([(.45, .70), (1, .70), (1, 1), (.39, 1)], "box", None),
        ],
    },
    # ----- 贴纸人物：异形、无边框、压在格子上的人物（两种风格都能用）-----
    "s-hero": {
        "name": "贴纸主角",
        "use": "顶部横条 → 左侧两个小格 + 右侧一格，中间一个贴纸人物压在格子之间 → 底部两格。人物登场、情绪顶点、这一页的主角时刻",
        "panels": [
            ([0, 0, 1, .2], "box", None),
            ([0, .22, .3, .42], "box", None),
            ([0, .44, .3, .64], "box", None),
            ([.16, .19, .84, .74], "sticker", None),
            ([.7, .22, 1, .64], "box", None),
            ([0, .74, .5, 1], "box", None),
            ([.5, .74, 1, 1], "box", None),
        ],
    },
    "s-action": {
        "name": "贴纸动作",
        "use": "顶部三个小格蓄力 → 一个大幅动作的贴纸人物 + 速度线横跨页面中部 → 底部一格被人物压住一角。摔倒、扑过来、拍桌这类大动作",
        "panels": [
            ([0, 0, 1 / 3, .24], "box", None),
            ([1 / 3, 0, 2 / 3, .24], "box", None),
            ([2 / 3, 0, 1, .24], "box", None),
            ([.02, .2, .98, .8], "sticker", "speed"),
            ([0, .72, 1, 1], "box", None),
        ],
    },
    "s-bust": {
        "name": "半身压底",
        "use": "顶部宽景 → 两格并排 → 底部一个大的半身人物压在左下，右边一格；人物下半身被页面底边切掉。人物的情绪时刻（紧张、愣住、下决心）。格子少、人物大",
        "panels": [
            ([0, 0, 1, .24], "box", None),
            ([0, .26, .49, .56], "box", None),
            ([.51, .26, 1, .56], "box", None),
            ([.64, .6, 1, 1], "box", None),
            ([-.04, .5, .74, 1.1], "sticker", None),
        ],
    },
    "s-fly": {
        "name": "飞出画面",
        "use": "顶部三个小格（左右留白）→ 一个横跨整页的大动作人物 + 四周速度线和飞出去的物件 → 底部一个大格，人物的脚压在它上面。摔倒、扑出去、被撞飞",
        "panels": [
            ([.06, 0, .36, .19], "box", None),
            ([.37, 0, .66, .19], "box", None),
            ([.67, 0, .96, .19], "box", None),
            ([-.04, .17, 1.04, .66], "sticker", "speed"),
            ([.1, .62, 1, 1], "box", None),
            ([.12, .66, .5, .82], "inset", None),
        ],
    },
    "s-pop": {
        "name": "出格反应",
        "use": "四格叙事，最后一个人物从右下角“跳出”格子压在边框上做夸张反应。喜剧的吐槽、震惊、社死",
        "panels": [
            ([0, 0, 1, .3], "box", None),
            ([0, .3, .55, .62], "box", None),
            ([.55, .3, 1, .62], "box", None),
            ([0, .62, 1, 1], "box", None),
            ([.7, .62, 1.03, 1.04], "sticker", None),
        ],
    },
}
KIND_LABEL = {"box": "", "free": " · 无框", "inset": " · 插入小格", "sticker": " · 贴纸人物（抠图）"}


def rect_poly(r):
    x0, y0, x1, y1 = r
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def inset_poly(pts, ds):
    """凸多边形每条边各自往里收 ds[i] 像素（用来留格距；页边上的边收 0）。"""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L * sgn, dx / L * sgn
        lines.append(((x0 + nx * ds[i], y0 + ny * ds[i]), (dx, dy)))
    out = []
    for i in range(n):
        (p, r), (q, t) = lines[i - 1], lines[i]
        den = r[0] * t[1] - r[1] * t[0]
        if abs(den) < 1e-9:
            out.append(q)
            continue
        u = ((q[0] - p[0]) * t[1] - (q[1] - p[1]) * t[0]) / den
        out.append((p[0] + r[0] * u, p[1] + r[1] * u))
    return out


def on_page_edge(a, b):
    return any(abs(a[k] - v) < 1e-6 and abs(b[k] - v) < 1e-6 for k in (0, 1) for v in (0, 1))


def parse_grid(s):
    try:
        cols, rows = (int(v) for v in s.lower().replace("×", "x").split("x"))
        assert 1 <= cols <= 4 and 1 <= rows <= 6
        return cols, rows
    except Exception:
        names = "、".join(TEMPLATES)
        sys.exit(f"版式写法：自由分格模板（{names}），或规整网格 列x行（如 2x2、3x3、1x4），收到：{s}")


def layout_panels(layout, W, H, has_title, has_footer, st, boxes=None):
    """返回 [{box, poly, kind, fx}]，顺序即阅读顺序。box 是外接矩形，文字按它摆放。"""
    m, g = st["margin"], st["gutter"]
    top = m + (TITLE_BAND if has_title else 0)
    bottom = H - m - (FOOTER_BAND if has_footer else 0)
    if layout == "custom":  # 自定义版式：格子全部由 boxes 给出，按格号排序就是阅读顺序
        if not boxes:
            sys.exit("layout 写 custom 时，要用 boxes 给出每一格的位置")
        shapes = []
        for key in sorted(boxes, key=int):
            val = boxes[key]
            shapes.append((val["box"], val.get("kind", "box"), val.get("fx")) if isinstance(val, dict)
                          else (val, "box", None))
        boxes = None
    if layout == "custom" or layout in TEMPLATES:
        X0, Y0, CW, CH = m, top, W - 2 * m, bottom - top
        out = []
        if layout != "custom":
            shapes = list(TEMPLATES[layout]["panels"])
        for key, val in (boxes or {}).items():  # 单格位置微调：{"格号": [x0, y0, x1, y1]} 或 {"box": [...], "kind": "inset"}
            i = int(key) - 1
            if not 0 <= i < len(shapes):
                sys.exit(f"boxes 里的格号 {key} 超出了版式 {layout} 的 {len(shapes)} 格")
            old = shapes[i]
            if isinstance(val, dict):
                shapes[i] = (val.get("box", old[0]), val.get("kind", old[1]), val.get("fx", old[2]))
            else:
                shapes[i] = (val, old[1], old[2])
        for shape, kind, fx in shapes:
            fpts = rect_poly(shape) if not isinstance(shape[0], (tuple, list)) else [tuple(v) for v in shape]
            if st["rtl"]:
                fpts = [(1 - x, y) for x, y in fpts][::-1]
            pts = [(X0 + x * CW, Y0 + y * CH) for x, y in fpts]
            if kind not in ("inset", "sticker"):  # 格子之间留格距；页边上的边不收，外缘对齐页边
                n = len(fpts)
                ds = [0 if on_page_edge(fpts[i], fpts[(i + 1) % n]) else g / 2 for i in range(n)]
                pts = inset_poly(pts, ds)
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            box = tuple(int(round(v)) for v in (min(xs), min(ys), max(xs), max(ys)))
            out.append({"box": box, "poly": pts, "kind": kind, "fx": fx})
        return out
    cols, rows = parse_grid(layout)
    cw = (W - 2 * m - (cols - 1) * g) / cols
    ch = (bottom - top - (rows - 1) * g) / rows
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            x, y = m + c * (cw + g), top + r * (ch + g)
            box = tuple(int(round(v)) for v in (x, y, x + cw, y + ch))
            row.append({"box": box, "poly": rect_poly(box), "kind": "box", "fx": None})
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


def cutout(img, tol=38, pocket=0.0):
    """把纯色背景（白 / 奶油色等）抠掉。

    颜色判断用 RGB 三个通道的差值之和（不用 Pillow floodfill 的“单通道最大差”——那样暖棕色头发和奶油底色
    在红色通道只差 30 多，会被整片当成背景抠掉）。
    1. 从图像四边往里灌：和背景色足够接近的连通区域变透明；
    2. 可选（pocket > 0）：被线条围起来的背景（手臂和身体之间）也抠掉，只抠面积大于 pocket（占全图比例）的块。
       默认关闭：围起来的白色到底是背景还是眼白、高光、白衬衫，脚本分不清，大白眼会被抠出洞。
       需要时在分镜里给这一格写 "pocket": 0.01，排完一定要看图检查。"""
    from collections import deque
    img = img.convert("RGB")
    small = img.copy()
    small.thumbnail((900, 900))
    w, h = small.size
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata())
    border = [px[x] for x in range(0, w, 5)] + [px[(h - 1) * w + x] for x in range(0, w, 5)] + \
             [px[y * w] for y in range(0, h, 5)] + [px[y * w + w - 1] for y in range(0, h, 5)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    dist = [abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) for c in px]
    loose, strict = tol * 1.6, max(12, tol * 0.7)
    BG, POCKET = 1, 2
    label = bytearray(w * h)

    def grow(starts, limit, mark):
        q = deque(i for i in starts if not label[i] and dist[i] <= limit)
        for i in q:
            label[i] = mark
        members = []
        while q:
            i = q.popleft()
            members.append(i)
            x, y = i % w, i // w
            for j in ((i - 1) if x else -1, (i + 1) if x < w - 1 else -1, (i - w) if y else -1, (i + w) if y < h - 1 else -1):
                if j >= 0 and not label[j] and dist[j] <= limit:
                    label[j] = mark
                    q.append(j)
        return members

    edge = [x for x in range(w)] + [(h - 1) * w + x for x in range(w)] + [y * w for y in range(h)] + \
           [y * w + w - 1 for y in range(h)]
    grow(edge, loose, BG)
    min_area = pocket * w * h
    for i in (range(w * h) if pocket > 0 else ()):
        if not label[i] and dist[i] <= strict:
            members = grow([i], strict, POCKET)
            if len(members) < min_area:
                for j in members:
                    label[j] = 3  # 太小：眼白、高光，保留
    mask = Image.frombytes("L", (w, h), bytes(0 if v in (BG, POCKET) else 255 for v in label))
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))  # 去掉孤立噪点
    mask = mask.resize(img.size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8))
    bbox = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out.crop(bbox) if bbox else out


def paste_sticker(canvas, img, slot, anchor="bottom", outline=0, shadow=False):
    """贴纸人物：抠图后等比放进格子（不裁切），直接压在其他格子上面。
    参考图里的人物是直接画在纸面上的，所以默认不加白描边和阴影；格子可以超出页面边缘（出血），人物会被页面边缘切掉。"""
    x0, y0, x1, y1 = slot["box"]
    bw_, bh = x1 - x0, y1 - y0
    scale = min(bw_ / img.width, bh / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    px = x0 + (bw_ - img.width) // 2
    py = y1 - img.height if anchor == "bottom" else (y0 if anchor == "top" else y0 + (bh - img.height) // 2)
    if outline or shadow:
        pad = outline + 12
        a = Image.new("L", (img.width + pad * 2, img.height + pad * 2), 0)
        a.paste(img.getchannel("A"), (pad, pad))
        ring = a.filter(ImageFilter.MaxFilter(outline * 2 + 1)) if outline else a
        if shadow:
            sh = ring.filter(ImageFilter.GaussianBlur(8)).point(lambda v: int(v * 0.3))
            canvas.paste((40, 30, 25), (px - pad + 6, py - pad + 8), sh)
        if outline:
            canvas.paste((255, 255, 255), (px - pad, py - pad), ring)
    canvas.paste(img, (px, py), img)


def placeholder_sticker(w, h, label, desc, fill):
    """没有图时，用一个人形轮廓占位，方便预览版式。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = fill or (200, 200, 200)
    cx = w / 2
    r = min(w, h) * 0.13
    d.ellipse((cx - r, h * 0.06, cx + r, h * 0.06 + 2 * r), fill=c)
    d.rounded_rectangle((cx - r * 1.9, h * 0.06 + 2 * r + 6, cx + r * 1.9, h), radius=r, fill=c)
    f = font(max(18, min(w, h) * 0.05))
    d.text((cx, h * 0.55), label, font=f, fill=(90, 90, 90), anchor="mm")
    if desc:
        f2 = font(max(13, min(w, h) * 0.03))
        for k, ln in enumerate(wrap(d, desc, f2, r * 3.4)[:5]):
            d.text((cx, h * 0.62 + k * line_h(f2) * 1.1), ln, font=f2, fill=(100, 100, 100), anchor="ma")
    return img


def poly_mask(slot, shrink=0):
    box, pts = slot["box"], slot["poly"]
    w, h = box[2] - box[0], box[3] - box[1]
    local = [(x - box[0], y - box[1]) for x, y in pts]
    if shrink:
        local = inset_poly(local, [shrink] * len(local))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(local, fill=255)
    return mask


def paste_free(canvas, img, slot, feather=0.07):
    """无框格：四边羽化，画面像直接画在纸上。feather 是羽化宽度占短边的比例。"""
    box = slot["box"]
    f = max(2, int(min(box[2] - box[0], box[3] - box[1]) * feather))
    mask = poly_mask(slot, f).filter(ImageFilter.GaussianBlur(f / 2))
    canvas.paste(img, box[:2], mask)


def draw_speedlines(canvas, slot, ink, weight=1.0):
    """放射速度线：从格子边缘往中心收，中间留给人物；斜切格按形状裁掉多余部分。"""
    box = slot["box"]
    layer = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = 0, 0, layer.width, layer.height
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    n = 36
    for k in range(n):
        a = 2 * math.pi * k / n + 0.07 * math.sin(k * 2.3)
        dx, dy = math.cos(a), math.sin(a)
        tx = ((x1 - cx) / dx if dx > 0 else (x0 - cx) / dx) if abs(dx) > 1e-6 else 1e9
        ty = ((y1 - cy) / dy if dy > 0 else (y0 - cy) / dy) if abs(dy) > 1e-6 else 1e9
        r_edge = min(tx, ty)
        r_in = r_edge * (0.62 + 0.18 * ((k * 7) % 5) / 4)
        half = (2.5 + (k % 3) * 1.5) * weight
        px, py = -dy, dx
        ox, oy = cx + dx * r_edge, cy + dy * r_edge
        d.polygon([(ox + px * half, oy + py * half), (ox - px * half, oy - py * half),
                   (cx + dx * r_in, cy + dy * r_in)], fill=ink)
    alpha = Image.composite(layer.getchannel("A"), Image.new("L", layer.size, 0), poly_mask(slot))
    layer.putalpha(alpha)
    canvas.paste(layer, box[:2], layer)


def covered_by_insets(panels):
    """找出被插入小格压住的格子：返回 {格号: [(压住它的格号, 位置, 比例)]}。"""
    out = {}
    for j, ins in enumerate(panels, 1):
        if ins["kind"] not in ("inset", "sticker"):
            continue
        for i, p in enumerate(panels, 1):
            if i == j or p["kind"] in ("inset", "sticker"):
                continue
            a, b = p["box"], ins["box"]
            x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
            if x1 <= x0 or y1 <= y0:
                continue
            area = (x1 - x0) * (y1 - y0) / ((a[2] - a[0]) * (a[3] - a[1]))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            v = "上" if cy < (a[1] + a[3]) / 2 else "下"
            hz = "左" if cx < (a[0] + a[2]) / 2 else "右"
            out.setdefault(i, []).append((j, hz + v, area))
    return out


def panel_size_text(i, p):
    x0, y0, x1, y1 = p["box"]
    return f"格 {i}｜{x1 - x0}×{y1 - y0}｜建议比例 {nearest_ratio(x1 - x0, y1 - y0)}{KIND_LABEL[p['kind']]}" + \
        ("｜加速度线" if p["fx"] == "speed" else "")


def cmd_layouts(a):
    print("自由分格模板（规整网格写 2x2、3x3、1x4）：")
    print(" 彩色：")
    for k, t in TEMPLATES.items():
        if k.startswith(("m", "s-")):
            continue
        print(f"  {k:11s} {t['name']}：{t['use']}")
    print(" 贴纸人物 / 出格（彩色、黑白都能用）：")
    for k, t in TEMPLATES.items():
        if k.startswith("s-"):
            print(f"  {k:11s} {t['name']}：{t['use']}")
    print(" 黑白：")
    for k, t in TEMPLATES.items():
        if k.startswith("m"):
            print(f"  {k:11s} {t['name']}：{t['use']}")


def cmd_sizes(a):
    st = resolve_style(a.mode)
    panels = layout_panels(a.layout, a.width, a.height, True, True, st)
    print(f"版式 {a.layout}，{'黑白' if a.mode == 'bw' else '彩色'}风格，画布 {a.width}×{a.height}，共 {len(panels)} 格")
    cov = covered_by_insets(panels)
    for i, p in enumerate(panels, 1):
        note = "".join(f"｜{pos}角约 {int(a * 100)}% 被第{j}格压住，出图时这块不要放人脸、主要人物和关键物件"
                       for j, pos, a in cov.get(i, []))
        print("  " + panel_size_text(i, p) + note)
    print("脚本会自动裁切，比例接近即可。无框格请让画面背景简洁（纯色或浅色），边缘会羽化融进底色。")
    if any(p["kind"] == "sticker" for p in panels):
        print("贴纸人物格：出全身或半身人物，isolated on a plain pure white background, no background, no ground shadow；"
              "脚本会自动抠图、加白描边，不裁切。其他有框格要画满背景。")


def render_page(spec, base_dir, out, force_bw=False, layout_override=None, page_label="", draft=False):
    """排一页。spec 是一页的分镜（layout / panels / title / footer / boxes ...）。返回 (用了真图的格数, 总格数)。
    draft=True 时不画对白、旁白、音效、标题和页码，得到给生图平台做整页重绘用的“版式草稿”。"""
    if draft:
        spec = dict(spec, _draft=True, title="", footer="", page_no="")
    mode = "bw" if (force_bw or spec.get("mode", "color") == "bw") else "color"
    bw = mode == "bw"
    st = resolve_style(mode, spec.get("style"))
    layout = layout_override or spec.get("layout") or ("m4-closeup" if bw else "4-inset")
    W, H = spec.get("canvas", [CANVAS_W, CANVAS_H])
    title, footer = spec.get("title", ""), spec.get("footer", "")
    slots = layout_panels(layout, W, H, bool(title), bool(footer), st, spec.get("boxes"))
    panels = spec.get("panels", [])
    need = len(slots)
    if len(panels) != need:
        print(f"  · {page_label}版式 {layout} 需要 {need} 格，分镜里有 {len(panels)} 格；多的忽略，少的补占位", file=sys.stderr)
        panels = (panels + [{}] * need)[:need]

    canvas = Image.new("RGB", (W, H), st["bg"])
    d = ImageDraw.Draw(canvas)
    if title:
        f = font(st.get("title_size", 52), st["title_font"])
        while text_w(d, title, f) > W - 2 * st["margin"] and f.size > 28:
            f = font(f.size - 2, st["title_font"])
        d.text((W / 2, st["margin"] + TITLE_BAND / 2 - 8), title, font=f, fill=st["ink"], anchor="mm")

    palette = st.get("placeholder")
    items = list(enumerate(zip(slots, panels), 1))
    zorder = {"free": 0, "box": 1, "inset": 2, "sticker": 3}
    items.sort(key=lambda it: zorder[it[1][0]["kind"]])  # 先铺无框大格，再有框格、插入小格，最后贴纸人物
    found = 0

    for i, (slot, p) in items:  # 第一遍：画面和格框
        box, kind = slot["box"], slot["kind"]
        w, h = box[2] - box[0], box[3] - box[1]
        fill = palette[(i - 1) % len(palette)] if palette else None
        if kind == "free" and fill:
            fill = mix(fill, st["bg"], 0.45)
        label = f"格 {i} · {nearest_ratio(w, h)}{KIND_LABEL[kind]}"
        if kind == "sticker":
            path = p.get("image")
            full = path and (path if os.path.isabs(path) else os.path.join(base_dir, path))
            if full and os.path.exists(full):
                src = Image.open(full)
                if p.get("crop"):  # 从一张大图（比如定妆表）里裁出人物：[x0, y0, x1, y1] 比例
                    c = p["crop"]
                    src = src.crop((int(src.width * c[0]), int(src.height * c[1]),
                                    int(src.width * c[2]), int(src.height * c[3])))
                stk = cutout(to_bw(src) if bw else src, int(p.get("cutout_tol", 38)), float(p.get("pocket", 0)))
                found += 1
            else:
                if path:
                    print(f"  · 找不到图片 {path}，先用占位图", file=sys.stderr)
                stk = placeholder_sticker(w, h, f"格 {i} · 贴纸人物", p.get("scene", ""), fill)
            if p.get("speedlines", slot["fx"] == "speed"):
                draw_speedlines(canvas, slot, st["ink"], st.get("speed_weight", 1.0))
            paste_sticker(canvas, stk, slot, p.get("anchor", "bottom"), int(p.get("outline", 0)), bool(p.get("shadow", False)))
            continue
        img, ok = load_panel(p.get("image"), base_dir, w, h, label, p.get("scene", ""), bw,
                             tuple(p.get("focus", (0.5, 0.5))), fill)
        found += ok
        if kind == "free":
            paste_free(canvas, img, slot, float(p.get("feather", 0.07)))
            if p.get("speedlines", slot["fx"] == "speed"):
                draw_speedlines(canvas, slot, st["ink"], st.get("speed_weight", 1.0))
            continue
        if kind == "inset":  # 插入小格外圈留一道底色，像贴在大格上
            ring = max(8, st["gutter"] * 0.6)
            d.rectangle((box[0] - ring, box[1] - ring, box[2] + ring, box[3] + ring), fill=st["bg"])
        canvas.paste(img, box[:2], poly_mask(slot))
        if p.get("speedlines", slot["fx"] == "speed"):
            draw_speedlines(canvas, slot, st["ink"], st.get("speed_weight", 1.0))
        pts = slot["poly"]
        d.line(pts + [pts[0], pts[1]], fill=st["ink"], width=max(1, round(st["border"])), joint="curve")

    for i, (slot, p) in items:  # 第二遍：文字压在所有画面上面（草稿模式不画字）
        if spec.get("_draft"):
            break
        box = slot["box"]
        w, h = box[2] - box[0], box[3] - box[1]
        base_size = min(38, max(21, min(w, h * 0.9) * 0.075)) * float(p.get("text_scale", 1))
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
        f = font(32, st["title_font"])
        d.text((W / 2, H - st["margin"] - FOOTER_BAND / 2 + 6), footer, font=f, fill=st["ink"], anchor="mm")
    page_no = spec.get("page_no")
    if page_no:  # 页码：右下角小字
        f = font(24, st["title_font"])
        d.text((W / 2, H - st["margin"] / 2 - 2), page_no, font=f, fill=st["ink"], anchor="mm")  # 底部居中，避开右下角的贴纸人物

    canvas.save(out)
    print(f"已生成 {out}（{page_label}版式 {layout}，{'黑白' if bw else '彩色'}风格，{found}/{need} 格用了真实图片）")
    return found, need


INHERIT = ("mode", "style", "canvas")


def cmd_comic(a):
    """一页：JSON 顶层就是一页的分镜。多页：JSON 里写 "pages": [ {一页}, {一页}, ... ]，
    mode / style / canvas 写在顶层，各页继承；只有第 1 页显示章节标题，每页自动加页码。"""
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(a.spec))
    stem = os.path.splitext(a.out or os.path.splitext(a.spec)[0] + ".png")[0]
    pages = spec.get("pages")
    if not pages:
        render_page(spec, base_dir, stem + ("-草稿.png" if a.draft else ".png"), a.bw, a.layout, draft=a.draft)
        return
    if len(pages) > 10:
        print(f"  · 这一章有 {len(pages)} 页，超过建议的最多 10 页，考虑拆成两章", file=sys.stderr)
    only = {int(x) for x in a.page.split(",")} if a.page else None
    total = len(pages)
    outs = []
    for n, page in enumerate(pages, 1):
        if only and n not in only:
            continue
        ps = {k: spec[k] for k in INHERIT if k in spec}
        ps.update(page)
        if n == 1 and "title" not in page and spec.get("title"):
            ps["title"] = spec["title"]
        if n == total and "footer" not in page and spec.get("footer"):
            ps["footer"] = spec["footer"]
        ps.setdefault("page_no", f"{n} / {total}")
        out = f"{stem}-{n:02d}{'-草稿' if a.draft else ''}.png"
        render_page(ps, base_dir, out, a.bw, a.layout, f"第 {n} 页 ", a.draft)
        outs.append(out)
    if a.strip and outs and not a.draft:
        ims = [Image.open(o) for o in outs]
        strip = Image.new("RGB", (ims[0].width, sum(i.height for i in ims)), "white")
        y = 0
        for im in ims:
            strip.paste(im, (0, y))
            y += im.height
        strip.save(stem + "-长条.png")
        print(f"已生成 {stem}-长条.png（{len(ims)} 页拼成一张竖长图，方便发条漫平台）")



def cmd_overlay(a):
    """第二步：给生图平台重绘好的整页漫画叠对白。
    JSON：{"mode": "color", "pages": [{"image": "page-01.png", "texts": [
        {"speaker": "江遥", "text": "……", "type": "speech", "at": [0.7, 0.12], "tail": [0.62, 0.25]},
        {"text": "湾景会·周五晚", "type": "caption", "at": [0.12, 0.05]},
        {"text": "哗啦！", "type": "sfx", "at": [0.8, 0.6]} ]}]}
    at / tail 是整页上的比例坐标（0—1），at 是气泡中心，tail 是尾巴指向的说话人位置。"""
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(a.spec))
    st = resolve_style("bw" if spec.get("mode") == "bw" else "color", spec.get("style"))
    pages = spec.get("pages") or [spec]
    for n, pg in enumerate(pages, 1):
        path = pg["image"] if os.path.isabs(pg["image"]) else os.path.join(base_dir, pg["image"])
        canvas = Image.open(path).convert("RGB")
        W, H = canvas.size
        cell = (0, 0, W, H)
        base = W * 0.034 * float(pg.get("text_scale", spec.get("text_scale", 1)))
        stack = {}
        for t in pg.get("texts", []):
            kind = t.get("type", "speech")
            if kind == "caption":
                f = font(base * 0.82, st["text_font"])
                d = ImageDraw.Draw(canvas)
                lines = str(t["text"]).split("\n")
                tw = max(text_w(d, ln, f) for ln in lines)
                lh = line_h(f) * 1.1
                pad = base * 0.4
                bw_, bh = tw + pad * 2, lh * len(lines) + pad * 2
                x0, y0, _, _ = at_box(cell, t["at"], bw_, bh)
                d.rectangle((x0, y0, x0 + bw_, y0 + bh), fill=st["caption_fill"], outline=st["ink"], width=3)
                for k, ln in enumerate(lines):
                    d.text((x0 + pad, y0 + pad + k * lh), ln, font=f, fill=st["ink"])
            elif kind == "sfx":
                fx, fy = t["at"]
                vert = "top" if fy < 0.33 else ("bottom" if fy > 0.66 else "middle")
                hz = "left" if fx < 0.33 else ("right" if fx > 0.66 else "center")
                sub = (int(W * max(0, fx - 0.2)), int(H * max(0, fy - 0.1)), int(W * min(1, fx + 0.2)), int(H * min(1, fy + 0.1)))
                draw_sfx(canvas, sub, {"text": t["text"], "pos": f"{vert}-{hz}"}, base, st)
            else:
                draw_dialogue(canvas, cell, [t], base, stack, st)
        stem = os.path.splitext(a.out or os.path.splitext(a.spec)[0] + ".png")[0]
        out = f"{stem}-{n:02d}.png" if len(pages) > 1 else stem + ".png"
        canvas.save(out)
        print(f"已生成 {out}（{len(pg.get('texts', []))} 处文字）")


def cmd_lint(a):
    """出图前检查提示词。分镜 JSON 顶层写 "cast": {"江遥": {"desc": "英文描述串", "ref": "ref-江遥.png"}}，
    每格写 "characters": ["江遥"] 和 "prompt": "完整提示词"。"""
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    cast = spec.get("cast", {})
    pages = spec.get("pages") or [spec]
    st = resolve_style("bw" if spec.get("mode") == "bw" else "color", spec.get("style"))
    errors, warns = [], []
    for n, pg in enumerate(pages, 1):
        ps = dict(pg)
        for k in INHERIT:
            if k in spec and k not in ps:
                ps[k] = spec[k]
        W, H = ps.get("canvas", [CANVAS_W, CANVAS_H])
        layout = ps.get("layout") or "4-inset"
        slots = layout_panels(layout, W, H, n == 1 and bool(spec.get("title") or ps.get("title")),
                              n == len(pages) and bool(spec.get("footer") or ps.get("footer")), st, ps.get("boxes"))
        for i, (slot, p) in enumerate(zip(slots, ps.get("panels", [])), 1):
            where = f"第{n}页 格{i}"
            prompt = p.get("prompt", "")
            if not prompt:
                warns.append(f"{where}：没有 prompt，跳过（复用已有的图可以忽略）")
                continue
            low = prompt.lower()
            chars = p.get("characters", [])
            for name, info in cast.items():
                desc = info["desc"] if isinstance(info, dict) else info
                mentioned = name in p.get("scene", "") or desc.split(",")[0].strip().lower() in low
                if name in chars and desc not in prompt:
                    errors.append(f"{where}：画面里有{name}，但提示词里没有她/他完整的描述串")
                elif mentioned and name not in chars:
                    errors.append(f"{where}：画面描述提到了{name}，但 characters 里没列，提示词也可能缺描述串")
            people = re.search(r"\b(woman|women|man|men|girl|boy|person|people|she|he|her|his|hand|hands|sleeve|"
                               r"shoulder|face|figure|someone)\b", low)
            if people and not any((info["desc"] if isinstance(info, dict) else info) in prompt for info in cast.values()):
                extras = ("receptionist", "manager", "crowd", "passenger", "staff", "waiter", "bartender")
                if not any(x in low for x in extras) or "her " in low or "hand" in low:
                    errors.append(f"{where}：提示词里出现了人（{people.group(0)}），却没有任何主要角色的描述串；"
                                  "如果是主角的手、背影、袖子，也要写完整描述串，否则模型会自己编一个人")
            w, h = slot["box"][2] - slot["box"][0], slot["box"][3] - slot["box"][1]
            ratio = nearest_ratio(w, h)
            if f"aspect ratio {ratio}" not in low:
                warns.append(f"{where}：这一格建议比例是 {ratio}，提示词里没写或写的不一样")
            if "no text" not in low:
                errors.append(f"{where}：负面提示缺少 no text")
            if slot["kind"] in ("free", "sticker"):
                if "plain" not in low or "background" not in low:
                    errors.append(f"{where}：{KIND_LABEL[slot['kind']].strip(' ·')}要写纯色背景（isolated on a plain ... background）")
            elif "background" not in low:
                warns.append(f"{where}：有框格最好写明背景铺满整格（detailed background filling the entire frame），避免留白")
            if any(k in p.get("scene", "") for k in ("手机", "屏幕", "二维码")) and not any(
                    k in low for k in ("screen facing", "screen-up", "screen up", "face-down", "screen faces")):
                warns.append(f"{where}：画面里有手机 / 屏幕，提示词没写屏幕朝向")
    for e in errors:
        print("✗ " + e)
    for w_ in warns:
        print("· " + w_)
    print(f"检查完：{len(errors)} 个错误，{len(warns)} 个提醒")
    if errors:
        sys.exit(1)


def cmd_sheet(a):
    """一致性核查对照图：定妆表放第一行，其余图按顺序排成网格，每张标上文件名。"""
    W = a.width
    rows = []
    for group in (a.refs or [], a.images or []):
        ims = []
        for f in group:
            im = Image.open(f).convert("RGB")
            im = im.resize((W, int(im.height * W / im.width)))
            canvas = Image.new("RGB", (W, im.height + 34), "white")
            canvas.paste(im, (0, 34))
            ImageDraw.Draw(canvas).text((6, 4), os.path.basename(f), font=font(22), fill=(30, 30, 30))
            ims.append(canvas)
        for k in range(0, len(ims), a.cols):
            rows.append(ims[k:k + a.cols])
    if not rows:
        sys.exit("没有图片")
    gap = 10
    out = Image.new("RGB", (a.cols * (W + gap) + gap, sum(max(i.height for i in r) + gap for r in rows) + gap), (150, 150, 150))
    y = gap
    for r in rows:
        x = gap
        for im in r:
            out.paste(im, (x, y))
            x += W + gap
        y += max(i.height for i in r) + gap
    out.save(a.out)
    print(f"已生成 {a.out}：第一行是定妆表，下面是要核查的图")


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
    m.add_argument("--layout", help="覆盖 JSON 里的版式：自由分格模板（彩色 4-inset 等，黑白 m4-closeup 等，见 layouts）或网格 2x2、3x3、1x4")
    m.add_argument("--bw", action="store_true", help="强制黑白风格")
    m.add_argument("--page", help="多页时只排其中几页，如 2 或 2,3")
    m.add_argument("--strip", action="store_true", help="多页时另外把所有页拼成一张竖长图")
    m.add_argument("--draft", action="store_true", help="只排画面不画字，输出给生图平台整页重绘用的版式草稿")

    o = sub.add_parser("overlay", help="第二步：给平台重绘好的整页漫画叠对白（按比例坐标放气泡）")
    o.add_argument("spec", help="叠字 JSON")
    o.add_argument("--out")
    m.add_argument("--out")

    sub.add_parser("layouts", help="列出自由分格模板和适用场景")

    lt = sub.add_parser("lint", help="出图前检查提示词：人物描述串、比例、背景、负面提示、屏幕朝向")
    lt.add_argument("spec")

    sh = sub.add_parser("sheet", help="生成一致性核查对照图：定妆表 + 所有分格图")
    sh.add_argument("--refs", nargs="*")
    sh.add_argument("--images", nargs="*")
    sh.add_argument("--cols", type=int, default=4)
    sh.add_argument("--width", type=int, default=420)
    sh.add_argument("--out", default="consistency-sheet.png")

    s = sub.add_parser("sizes", help="查看版式每格尺寸、建议出图比例和格子类型")
    s.add_argument("--layout", default="4-inset")  # 黑白可用 m4-closeup 等
    s.add_argument("--mode", choices=["color", "bw"], default="color")
    s.add_argument("--width", type=int, default=CANVAS_W)
    s.add_argument("--height", type=int, default=CANVAS_H)

    a = p.parse_args()
    if a.cmd == "sizes":
        return cmd_sizes(a)
    if a.cmd == "layouts":
        return cmd_layouts(a)
    setup_fonts(a.font, a.serif_font)
    if a.cmd in ("lint", "sheet"):
        return {"lint": cmd_lint, "sheet": cmd_sheet}[a.cmd](a)
    {"cover": cmd_cover, "comic": cmd_comic, "overlay": cmd_overlay}[a.cmd](a)


if __name__ == "__main__":
    main()
