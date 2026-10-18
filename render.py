"""Render the 30s 9:16 "3 cara guna Claude" explainer video from assets/voiceover.wav.

Usage: python3 render.py [--preview SECONDS ...]
Needs: Python 3, Pillow, numpy, ffmpeg.
"""
import math
import re
import subprocess
import sys
import wave
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
AUDIO = "assets/voiceover.wav"
OUT = "output/claude-3-cara.mp4"

FONT_DIR = "/usr/share/fonts/opentype/inter/"
BLACK = FONT_DIR + "InterDisplay-Black.otf"
XBOLD = FONT_DIR + "Inter-ExtraBold.otf"
BOLD = FONT_DIR + "Inter-Bold.otf"
SEMI = FONT_DIR + "Inter-SemiBold.otf"

CREAM = (245, 240, 232)
ACCENT = (232, 119, 74)
YELLOW = (242, 193, 78)
GREEN = (91, 192, 138)
RED = (229, 83, 75)
DARK = (20, 18, 16)
CARD = (38, 33, 29)

# Phrase timings measured from pauses in the voiceover (seconds).
SEGS = [
    (0.24, 1.80, "Nak guna AI dengan lebih berkesan?"),
    (2.20, 4.44, "Ini 3 cara penggunaan Claude yang betul!"),
    (5.20, 5.66, "Pertama,"),
    (5.84, 9.94, "beri arahan yang jelas dan spesifik supaya Claude faham apa yang anda perlukan."),
    (10.52, 11.04, "Kedua,"),
    (11.28, 12.80, "berikan konteks yang mencukupi,"),
    (13.16, 17.16, "seperti tujuan, sasaran audiens dan format jawapan yang diinginkan."),
    (17.84, 18.26, "Ketiga,"),
    (18.60, 21.04, "semak semula fakta dan hasil yang diberikan."),
    (21.46, 23.16, "Jangan terus percaya tanpa pengesahan."),
    (23.76, 23.98, "Ingat,"),
    (24.36, 25.16, "arahan yang jelas,"),
    (25.48, 26.38, "konteks yang tepat"),
    (26.66, 27.64, "dan semakan fakta"),
    (27.86, 30.18, "membantu anda menggunakan Claude dengan lebih bijak!"),
]
# Which phrases share one on-screen caption.
CAPTION_GROUPS = [[0], [1], [2, 3], [4, 5], [6], [7, 8], [9], [10, 11, 12, 13], [14]]
HIGHLIGHT = {"berkesan", "3", "cara", "claude", "jelas", "spesifik", "konteks", "mencukupi",
             "tujuan", "sasaran", "audiens", "format", "jawapan", "semak", "fakta",
             "pengesahan", "tepat", "semakan", "bijak"}
# Scene cuts sit in the middle of the pauses; a wipe hides each cut.
CUTS = [4.85, 10.25, 17.50, 23.50]
WIPE = 0.24


def norm(word):
    return re.sub(r"[^\w]", "", word.lower())


# Spread each phrase's duration over its words by length to get word timings.
WORDS = []
for si, (s, e, text) in enumerate(SEGS):
    toks = text.split()
    weights = [len(norm(t)) + 2 for t in toks]
    total, acc = sum(weights), 0
    for tok, wgt in zip(toks, weights):
        ws = s + (e - s) * acc / total
        acc += wgt
        WORDS.append({"t": tok, "s": ws, "e": s + (e - s) * acc / total, "seg": si})


def wt(seg, word):
    for w in WORDS:
        if w["seg"] == seg and norm(w["t"]).startswith(word):
            return w["s"]
    raise KeyError(word)


# ---------- easing ----------
def clamp(x):
    return max(0.0, min(1.0, x))


def ease_out_back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def pop(t, t0, d=0.38):
    """Scale/alpha for an element popping in at t0."""
    return ease_out_back((t - t0) / d), ease_out((t - t0) / (d * 0.6))


# ---------- drawing helpers ----------
@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=None)
def text_sprite(text, path, size, color, pill=None, pad=(36, 18)):
    f = font(path, size)
    l, t, r, b = f.getbbox(text)
    tw, th = r - l, b - t
    px, py = pad if pill else (8, 8)
    im = Image.new("RGBA", (tw + 2 * px, th + 2 * py), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if pill:
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=min(im.height // 2, 40), fill=pill)
    d.text((px - l, py - t), text, font=f, fill=color)
    return im


def put(fr, sprite, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if alpha <= 0.01 or scale <= 0.01:
        return
    sp = sprite
    if abs(scale - 1) > 0.005:
        sp = sp.resize((max(1, int(sp.width * scale)), max(1, int(sp.height * scale))), Image.BILINEAR)
    if rot:
        sp = sp.rotate(rot, resample=Image.BILINEAR, expand=True)
    if alpha < 0.999:
        a = sp.getchannel("A").point(lambda v: int(v * alpha))
        sp = sp.copy()
        sp.putalpha(a)
    fr.paste(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)), sp)


def ptext(fr, t, t0, text, path, size, color, cx, cy, pill=None, d=0.38):
    if t < t0:
        return
    s, a = pop(t, t0, d)
    put(fr, text_sprite(text, path, size, color, pill), cx, cy, s, a)


@lru_cache(maxsize=None)
def background():
    bw, bh = W + 240, H + 320
    y = np.linspace(0, 1, bh)[:, None]
    top, bot = np.array([26, 21, 18]), np.array([12, 11, 10])
    grad = (top * (1 - y) + bot * y)[:, :, None].repeat(bw, axis=2).transpose(0, 2, 1)
    bg = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
    glow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-200, 150, 700, 1050), fill=ACCENT + (70,))
    g.ellipse((600, 1300, 1500, 2200), fill=YELLOW + (38,))
    glow = glow.filter(ImageFilter.GaussianBlur(190))
    bg.alpha_composite(glow)
    dots = ImageDraw.Draw(bg)
    for yy in range(0, bh, 64):
        for xx in range(0, bw, 64):
            dots.ellipse((xx - 2, yy - 2, xx + 2, yy + 2), fill=(255, 255, 255, 14))
    return bg


@lru_cache(maxsize=None)
def burst():
    s = 1000
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(16):
        a0 = i * 2 * math.pi / 16
        a1 = a0 + math.pi / 30
        d.polygon([(s / 2, s / 2), (s / 2 + s * math.cos(a0), s / 2 + s * math.sin(a0)),
                   (s / 2 + s * math.cos(a1), s / 2 + s * math.sin(a1))], fill=ACCENT + (40,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, s, s), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(120))
    im.putalpha(Image.fromarray((np.array(im.getchannel("A")) * (np.array(mask) / 255)).astype(np.uint8)))
    return im


@lru_cache(maxsize=None)
def badge(num):
    s = 190
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4, 4, s - 4, s - 4), fill=ACCENT)
    d.ellipse((4, 4, s - 4, s - 4), outline=YELLOW, width=6)
    f = font(BLACK, 92)
    d.text((s / 2, s / 2 + 2), num, font=f, fill=DARK, anchor="mm")
    return im


def icon(kind, size=96, color=DARK):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    if kind == "flag":
        d.line((s * .3, s * .15, s * .3, s * .88), fill=color, width=int(s * .09))
        d.polygon([(s * .32, s * .17), (s * .8, s * .32), (s * .32, s * .5)], fill=color)
    elif kind == "people":
        d.ellipse((s * .35, s * .12, s * .65, s * .42), fill=color)
        d.pieslice((s * .18, s * .48, s * .82, s * 1.1), 180, 360, fill=color)
    elif kind == "doc":
        d.rounded_rectangle((s * .2, s * .1, s * .8, s * .9), radius=int(s * .08), outline=color, width=int(s * .08))
        for k in range(3):
            y = s * (.35 + k * .17)
            d.line((s * .32, y, s * .68, y), fill=color, width=int(s * .07))
    elif kind == "check":
        d.line((s * .2, s * .52, s * .42, s * .74, s * .82, s * .28), fill=color, width=int(s * .13), joint="curve")
    elif kind == "cross":
        w = int(s * .13)
        d.line((s * .25, s * .25, s * .75, s * .75), fill=color, width=w)
        d.line((s * .75, s * .25, s * .25, s * .75), fill=color, width=w)
    elif kind == "warn":
        d.polygon([(s / 2, s * .08), (s * .95, s * .9), (s * .05, s * .9)], fill=color)
        d.text((s / 2, s * .6), "!", font=font(BLACK, int(s * .55)), fill=RED, anchor="mm")
    elif kind == "lens":
        d.ellipse((s * .1, s * .1, s * .62, s * .62), outline=color, width=int(s * .1))
        d.line((s * .55, s * .55, s * .9, s * .9), fill=color, width=int(s * .14))
    return im


@lru_cache(maxsize=None)
def chip(label, kind, color):
    cw, ch = 820, 124
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=30, fill=CARD, outline=color + (160,), width=3)
    d.ellipse((18, 14, 18 + 96, 14 + 96), fill=color)
    im.paste(ic := icon(kind, 70), (18 + 13, 14 + 13), ic)
    d.text((140, ch / 2), label, font=font(XBOLD, 52), fill=CREAM, anchor="lm")
    return im


@lru_cache(maxsize=None)
def example_card(good):
    cw, ch = 900, 120
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = GREEN if good else RED
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=28, fill=col + (40,), outline=col, width=3)
    d.ellipse((18, 18, 102, 102), fill=col)
    im.paste(ic := icon("check" if good else "cross", 64), (28, 28), ic)
    tag = "SPESIFIK" if good else "KABUR"
    d.text((126, 34), tag, font=font(BOLD, 26), fill=col, anchor="lm")
    txt = "“Poster A4 promosi kopi, tona hangat”" if good else "“Buat poster”"
    d.text((126, 78), txt, font=font(SEMI, 38), fill=CREAM, anchor="lm")
    return im


# ---------- scenes ----------
def scene_hook(fr, t):
    out = ease_in_out((t - 2.05) / 0.3)  # first line leaves as "Ini 3 cara" starts
    if out < 1:
        dy, a = -160 * out, 1 - out
        for txt, path, size, col, y, t0 in [
            ("NAK GUNA AI", BLACK, 120, CREAM, 690, 0.24),
            ("DENGAN LEBIH", BLACK, 96, CREAM, 830, wt(0, "dengan")),
            ("BERKESAN?", BLACK, 160, ACCENT, 1000, wt(0, "berkesan")),
        ]:
            if t >= t0:
                s, al = pop(t, t0)
                put(fr, text_sprite(txt, path, size, col), W / 2, y + dy, s, al * a)
        t0 = wt(0, "berkesan") + 0.15
        if t >= t0:
            bw = int(620 * ease_out((t - t0) / 0.4))
            if bw > 2:
                bar = Image.new("RGBA", (bw, 16), YELLOW + (int(255 * a),))
                fr.paste(bar, (int(W / 2 - 310), int(1100 + dy)), bar)
    if t >= 2.2:
        t3 = wt(1, "3")
        if t >= t3:
            s, a = pop(t, t3, 0.5)
            put(fr, burst(), W / 2, 860, s * 1.1, a, rot=(t - t3) * 25)
        ptext(fr, t, 2.2, "INI", BLACK, 80, CREAM, W / 2, 520)
        ptext(fr, t, t3, "3", BLACK, 560, ACCENT, W / 2, 850, d=0.5)
        ptext(fr, t, wt(1, "penggunaan"), "CARA GUNA CLAUDE", BLACK, 92, CREAM, W / 2, 1150)
        ptext(fr, t, wt(1, "betul"), "YANG BETUL!", BLACK, 64, DARK, W / 2, 1275, pill=GREEN)


def step_header(fr, t, num, t0):
    s, a = pop(t, t0, 0.45)
    put(fr, badge(num), W / 2, 450, s, a, rot=(1 - clamp((t - t0) / 0.45)) * -90)


def scene_one(fr, t):
    step_header(fr, t, "01", 5.2)
    ptext(fr, t, wt(3, "arahan"), "ARAHAN", BLACK, 130, CREAM, W / 2, 640)
    ptext(fr, t, wt(3, "jelas"), "JELAS", BLACK, 104, DARK, W / 2, 790, pill=ACCENT)
    ptext(fr, t, wt(3, "spesifik"), "& SPESIFIK", BLACK, 104, ACCENT, W / 2, 925)
    for good, y, t0 in [(False, 1085, wt(3, "supaya")), (True, 1225, wt(3, "faham"))]:
        if t >= t0:
            p = ease_out((t - t0) / 0.35)
            put(fr, example_card(good), W / 2 + (1 - p) * 500, y, 1, p)


def scene_two(fr, t):
    step_header(fr, t, "02", 10.52)
    ptext(fr, t, wt(5, "konteks"), "KONTEKS", BLACK, 140, ACCENT, W / 2, 650)
    ptext(fr, t, wt(5, "mencukupi"), "YANG MENCUKUPI", BLACK, 76, CREAM, W / 2, 790)
    for label, kind, col, y, t0 in [
        ("Tujuan", "flag", ACCENT, 960, wt(6, "tujuan")),
        ("Sasaran audiens", "people", YELLOW, 1105, wt(6, "sasaran")),
        ("Format jawapan", "doc", GREEN, 1250, wt(6, "format")),
    ]:
        if t >= t0:
            p = ease_out_back((t - t0) / 0.4)
            put(fr, chip(label, kind, col), W / 2 + (1 - p) * 700, y, 1, ease_out((t - t0) / 0.25))


@lru_cache(maxsize=None)
def doc_card():
    cw, ch = 760, 360
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=30, fill=CARD, outline=(255, 255, 255, 40), width=2)
    d.text((40, 48), "JAWAPAN AI", font=font(BOLD, 30), fill=(200, 190, 180), anchor="lm")
    return im


DOC_LINES = [(1, 0.95), (2, 0.8), (3, 0.9), (4, 0.6)]


def scene_three(fr, t):
    step_header(fr, t, "03", 17.84)
    ptext(fr, t, wt(8, "semak"), "SEMAK", BLACK, 130, CREAM, W / 2, 640)
    ptext(fr, t, wt(8, "fakta"), "FAKTA", BLACK, 130, DARK, W / 2, 790, pill=ACCENT)
    t_doc, t_warn = wt(8, "semak"), 21.46
    if t >= t_doc:
        fade = 1 - ease_out((t - t_warn) / 0.3) if t >= t_warn else 1
        a = ease_out((t - t_doc) / 0.3) * fade
        cx, cy = W / 2, 1110
        card = doc_card().copy()
        d = ImageDraw.Draw(card)
        scan = clamp((t - (t_doc + 0.3)) / 2.2)  # lens sweeps the lines while "semak..." is spoken
        for i, frac in DOC_LINES:
            y = 70 + i * 62
            done = scan * len(DOC_LINES) >= i
            d.rounded_rectangle((40, y, 40 + int(560 * frac), y + 22), radius=11,
                                fill=GREEN if done else (90, 82, 75))
            if done:
                d.line((640, y - 4, 660, y + 16, 700, y - 16), fill=GREEN, width=8)
        put(fr, card, cx, cy, 1, a)
        if a > 0:
            line = min(int(scan * len(DOC_LINES)), len(DOC_LINES) - 1)
            within = scan * len(DOC_LINES) - line
            lx = cx - 330 + 560 * within
            ly = cy - 180 + 70 + (line + 1) * 62
            put(fr, icon("lens", 150, YELLOW), lx + 40, ly + 30, 1, a)
    if t >= t_warn:
        shake = math.sin((t - t_warn) * 60) * 14 * (1 - clamp((t - t_warn) / 0.5))
        s, a = pop(t, t_warn, 0.4)
        put(fr, warn_card(), W / 2 + shake, 1110, s, a)


@lru_cache(maxsize=None)
def warn_card():
    cw, ch = 900, 300
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=34, fill=RED + (55,), outline=RED, width=4)
    im.paste(ic := icon("warn", 150, YELLOW), (40, 75), ic)
    d.text((220, 105), "JANGAN TERUS", font=font(BLACK, 68), fill=CREAM, anchor="lm")
    d.text((220, 180), "PERCAYA", font=font(BLACK, 68), fill=YELLOW, anchor="lm")
    d.text((222, 245), "tanpa pengesahan", font=font(SEMI, 40), fill=(235, 210, 200), anchor="lm")
    return im


@lru_cache(maxsize=None)
def check_row(label, ticked):
    cw, ch = 780, 112
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=28, fill=CARD)
    d.rounded_rectangle((22, 18, 98, 94), radius=18, fill=GREEN if ticked else None, outline=GREEN, width=5)
    if ticked:
        im.paste(ic := icon("check", 66), (27, 23), ic)
    d.text((130, ch / 2), label, font=font(XBOLD, 54), fill=CREAM, anchor="lm")
    return im


def scene_recap(fr, t):
    ptext(fr, t, 23.76, "INGAT!", BLACK, 150, ACCENT, W / 2, 470)
    for label, y, t0 in [("Arahan jelas", 680, 24.36), ("Konteks tepat", 815, 25.48), ("Semakan fakta", 950, 26.66)]:
        if t >= t0:
            p = ease_out((t - t0) / 0.3)
            put(fr, check_row(label, t >= t0 + 0.45), W / 2 - (1 - p) * 600, y, 1, p)
    ptext(fr, t, 27.86, "GUNA CLAUDE DENGAN", BLACK, 70, CREAM, W / 2, 1110)
    tb = wt(14, "lebih")
    if t >= tb:
        s, a = pop(t, tb, 0.5)
        put(fr, burst(), W / 2, 1250, s * 0.9, a * 0.9, rot=(t - tb) * 30)
    ptext(fr, t, tb, "LEBIH BIJAK!", BLACK, 130, DARK, W / 2, 1250, pill=YELLOW, d=0.5)


SCENES = [(0, scene_hook), (CUTS[0], scene_one), (CUTS[1], scene_two), (CUTS[2], scene_three), (CUTS[3], scene_recap)]


def draw_wipe(fr, t):
    for c in CUTS:
        p = (t - (c - WIPE)) / (2 * WIPE)
        if 0 <= p <= 1:
            e = ease_in_out(p)
            d = ImageDraw.Draw(fr)
            skew = 500
            for col, off, width in [(YELLOW, 0, 2.2 * W), (ACCENT, 140, 2.2 * W - 280)]:
                x0 = -2.4 * W + e * 3.6 * W + off
                d.polygon([(x0 + skew, 0), (x0 + width + skew, 0), (x0 + width, H), (x0, H)], fill=col)


def draw_chrome(fr, t, total):
    d = ImageDraw.Draw(fr)
    d.rectangle((0, 0, int(W * t / total), 12), fill=ACCENT)
    if CUTS[0] <= t < CUTS[3]:
        step = sum(t >= c for c in CUTS[:3]) - 1
        for i in range(3):
            x = W / 2 + (i - 1) * 120
            on = i == step
            done = i < step
            col = ACCENT if on else (GREEN if done else (70, 64, 58))
            w = 90 if on else 60
            d.rounded_rectangle((x - w / 2, 250, x + w / 2, 264), radius=7, fill=col)
        d.text((W / 2, 200), "3 TIPS GUNA CLAUDE", font=font(BOLD, 34), fill=(200, 190, 180), anchor="mm")


def caption_layout(group):
    f = font(XBOLD, 60)
    words = [w for w in WORDS if w["seg"] in group]
    space = f.getlength(" ")
    lines, cur, cur_w = [], [], 0
    for w in words:
        ww = f.getlength(w["t"])
        if cur and cur_w + space + ww > 920:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
        cur_w += (space if cur else 0) + ww
        cur.append((w, ww))
    if cur:
        lines.append((cur, cur_w))
    return lines


LAYOUTS = [caption_layout(g) for g in CAPTION_GROUPS]


def draw_caption(fr, t):
    gi = None
    for i, g in enumerate(CAPTION_GROUPS):
        start = SEGS[g[0]][0] - 0.1
        end = SEGS[CAPTION_GROUPS[i + 1][0]][0] - 0.12 if i + 1 < len(CAPTION_GROUPS) else 99
        end = min([end] + [c for c in CUTS if start < c < end])  # swap captions under the wipe
        if start <= t < end:
            gi = i
    if gi is None:
        return
    f = font(XBOLD, 60)
    space = f.getlength(" ")
    lines = LAYOUTS[gi]
    lh = 88
    y0 = 1500 - (len(lines) - 1) * lh / 2
    appear = ease_out((t - (SEGS[CAPTION_GROUPS[gi][0]][0] - 0.1)) / 0.2)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for li, (ws, lw) in enumerate(lines):
        x = W / 2 - lw / 2
        y = y0 + li * lh + (1 - appear) * 30
        for w, ww in ws:
            spoken = t >= w["s"]
            hl = norm(w["t"]) in HIGHLIGHT
            if hl and spoken:
                k = ease_out_back((t - w["s"]) / 0.25)
                pad = 10 * k
                d.rounded_rectangle((x - pad, y - 40 - pad * .4, x + ww + pad, y + 36 + pad * .4), radius=16, fill=ACCENT)
                d.text((x, y), w["t"], font=f, fill=DARK, anchor="lm")
            else:
                col = CREAM + ((255,) if spoken else (95,))
                d.text((x, y), w["t"], font=f, fill=col, anchor="lm", stroke_width=4, stroke_fill=(0, 0, 0, 150 if spoken else 60))
            x += ww + space
    if appear < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * appear)))
    fr.alpha_composite(layer)


def render_frame(t, total):
    bg = background()
    ox = 120 + 90 * math.sin(t * 0.35)
    oy = 160 + 120 * math.sin(t * 0.22 + 1)
    fr = bg.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
    scene = [fn for start, fn in SCENES if t >= start][-1]
    scene(fr, t)
    draw_chrome(fr, t, total)
    draw_caption(fr, t)
    draw_wipe(fr, t)
    return fr.convert("RGB")


# ---------- audio ----------
def build_audio(path_out):
    with wave.open(AUDIO) as w:
        sr = w.getframerate()
        voice = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    mix = voice.copy()
    rng = np.random.default_rng(7)

    def add(sig, at):
        i = int(at * sr)
        j = min(len(mix), i + len(sig))
        if j > i:
            mix[i:j] += sig[: j - i]

    # whoosh for each wipe: noise through a sweeping one-pole low-pass
    n = int(0.55 * sr)
    for c in CUTS:
        noise = rng.standard_normal(n).astype(np.float32)
        out = np.zeros(n, np.float32)
        y = 0.0
        for k in range(n):
            a = 0.02 + 0.5 * math.sin(math.pi * k / n) ** 2
            y += a * (noise[k] - y)
            out[k] = y
        env = np.sin(np.pi * np.arange(n) / n) ** 2
        add(out * env * 0.16, c - 0.3)
    # soft pops when key words land
    m = int(0.09 * sr)
    tt = np.arange(m) / sr
    blip = (np.sin(2 * np.pi * 880 * tt * (1 + 0.6 * tt / 0.09)) * np.exp(-tt * 45)).astype(np.float32) * 0.07
    for at in [wt(0, "berkesan"), wt(1, "3"), wt(1, "betul"), wt(3, "jelas"), wt(3, "spesifik"),
               wt(6, "tujuan"), wt(6, "sasaran"), wt(6, "format"), 21.46, 24.81, 25.93, 27.11, wt(14, "lebih")]:
        add(blip, at)
    mix = np.clip(mix, -1, 1)
    with wave.open(path_out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return len(voice) / sr


def main():
    if "--preview" in sys.argv:
        total = 30.6
        for arg in sys.argv[sys.argv.index("--preview") + 1:]:
            render_frame(float(arg), total).save(f"output/preview_{arg}.png")
        return
    mixed = "output/_mix.wav"
    total = build_audio(mixed)
    frames = int(math.ceil(total * FPS))
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", mixed,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)
    for i in range(frames):
        ff.stdin.write(render_frame(i / FPS, total).tobytes())
        if i % 90 == 0:
            print(f"frame {i}/{frames}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
