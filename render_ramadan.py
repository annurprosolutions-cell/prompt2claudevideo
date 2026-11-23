"""Ramadan video: "Belum Ramadan, tapi boleh mula!" (9:16, ~102s) from assets/voiceover_ramadan.wav.

Re-uses the effect engine of render_v2.py (motion blur, DOF, balloon text, glossy pills, starburst /
flash / whip transitions, confetti) with a night-sky + gold Ramadan palette.

Usage: python3 render_ramadan.py [--preview SEC ...]   (no args = full video)
Output: output/ramadan-5-persediaan.mp4
"""
import math
import re
import subprocess
import sys
import wave
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from render import (BLACK, BOLD, FPS, H, SEMI, W, XBOLD, clamp, ease_in_out, ease_out, ease_out_back, font, pop)
from render_v2 import bake_shadow, fly, fx, label, put2, vgrad

AUDIO = "assets/voiceover_ramadan.wav"
OUT = "output/ramadan-5-persediaan.mp4"

GOLD = (244, 190, 60)
GOLD_L = (255, 228, 135)
GOLD_M = (236, 160, 30)
GOLD_D = (130, 80, 10)
EMER = (16, 150, 120)
ROSE = (232, 84, 112)
CREAMT = (252, 246, 232)
INKN = (18, 30, 60)
NIGHT = (7, 16, 40)

# (start, end, text) -- aligned to the pauses detected in the audio
PH = [
    (0.28, 2.09, "Assalamualaikum warahmatullahi wabarakatuh!"),
    (2.92, 5.55, "Ramadan semakin dekat!"),
    (6.54, 7.86, "Persoalannya..."),
    (8.66, 9.34, "dah bersedia?"),
    (9.88, 10.57, "Sebenarnya,"),
    (11.43, 14.82, "kita tak perlu tunggu Ramadan untuk mula buat kebaikan."),
    (15.46, 17.45, "Persediaan itu boleh bermula hari ini!"),
    (18.30, 20.59, "Yang pertama, jaga solat lima waktu."),
    (21.39, 24.40, "Usahakan solat di awal waktu dan perbaiki kekhusyukan."),
    (25.16, 28.48, "Jadikan solat sebagai keutamaan, bukan sekadar rutin harian."),
    (29.34, 31.56, "Yang kedua, biasakan membaca al-Quran."),
    (32.40, 33.37, "Tak perlu terus banyak."),
    (33.82, 37.11, "Walaupun hanya beberapa ayat sehari, yang penting kita istiqamah."),
    (37.98, 39.99, "Biarlah sedikit, asalkan berterusan."),
    (40.80, 41.41, "Yang ketiga,"),
    (41.72, 43.21, "latih diri dengan puasa sunat."),
    (44.21, 47.84, "Mulakan mengikut kemampuan, seperti puasa pada hari Isnin dan Khamis."),
    (48.47, 54.06, "Dengan cara ini, kita dapat membiasakan diri dan menyediakan tubuh serta jiwa untuk berpuasa di bulan Ramadan."),
    (54.91, 58.13, "Yang keempat, bersihkan hati dengan memperbanyakkan istighfar."),
    (58.97, 62.07, "Mohon keampunan Allah atas segala dosa dan kesilapan."),
    (62.90, 64.28, "Kurangkan perkara yang sia-sia."),
    (64.67, 66.72, "Gantikan dengan perkara yang membawa manfaat."),
    (67.49, 68.23, "Dan yang kelima,"),
    (68.53, 71.12, "pilih satu amalan baik dan lakukan secara konsisten."),
    (71.92, 75.52, "Jangan terlalu mengejar banyaknya amalan sehingga kita lupa untuk istiqamah."),
    (76.31, 76.60, "Ingat!"),
    (77.06, 79.53, "Perubahan yang besar bermula dengan langkah yang kecil."),
    (80.35, 81.37, "Ramadan belum tiba..."),
    (81.74, 84.72, "tetapi pahala kebaikan boleh kita usahakan mulai sekarang!"),
    (85.48, 87.38, "Jangan tunggu esok untuk menjadi lebih baik."),
    (87.94, 88.77, "Mulakan hari ini."),
    (89.29, 91.09, "Perbaiki diri sedikit demi sedikit."),
    (91.96, 96.96, "Semoga Allah memberikan kita kesempatan untuk bertemu Ramadan dan menjalaninya dengan penuh keimanan."),
    (97.89, 98.83, "Ramadan belum tiba,"),
    (99.20, 101.41, "tapi persediaan kita boleh bermula hari ini!"),
]
CAPTION_GROUPS = [[0], [1], [2, 3], [4], [5], [6], [7], [8], [9], [10], [11], [12], [13], [14, 15], [16], [17], [18], [19],
                  [20], [21], [22, 23], [24], [25, 26], [27, 28], [29], [30], [31], [32], [33, 34]]
CUTS = [17.87, 28.91, 40.40, 54.50, 67.10, 80.00]
HIGHLIGHT = {"ramadan", "solat", "awal", "kekhusyukan", "alquran", "istiqamah", "puasa", "sunat", "isnin", "khamis",
             "istighfar", "keampunan", "manfaat", "konsisten", "ingat", "kecil", "perubahan", "pahala", "esok",
             "sekarang", "bersedia", "kebaikan", "persediaan", "keimanan", "mulakan", "sia-sia", "siasia", "kemampuan"}


class OD:
    """ImageDraw that really alpha-blends onto an RGBA frame (flush with .done())."""

    def __init__(self, fr):
        self.fr, self.l = fr, Image.new("RGBA", fr.size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.l)

    def __getattr__(self, n):
        return getattr(self.d, n)

    def done(self):
        self.fr.alpha_composite(self.l)


def cr(x, a, b):
    return max(a, min(b, x))


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


WORDS = []
for si, (s, e, text) in enumerate(PH):
    toks = text.split()
    wts = [len(norm(x)) + 2 for x in toks]
    tot, acc = sum(wts), 0
    for tok, wg in zip(toks, wts):
        ws = s + (e - s) * acc / tot
        acc += wg
        WORDS.append({"t": tok, "s": ws, "e": s + (e - s) * acc / tot, "seg": si})


def gwt(seg, word):
    for w in WORDS:
        if w["seg"] == seg and norm(w["t"]).startswith(word):
            return w["s"]
    raise KeyError((seg, word))


# ------------------------------------------------------------------ sprites
def gb(text, size):
    return V_balloon(text, size, GOLD_L, GOLD_M, GOLD_D)


def wb(text, size):
    return V_balloon(text, size, (255, 255, 255), (206, 222, 240), (70, 95, 140))


def V_balloon(text, size, top, bot, ext):
    from render_v2 import balloon
    return balloon(text, size, top, bot, ext)


@lru_cache(maxsize=None)
def pillg(text, size=64, fill=GOLD, fg=(40, 24, 6), padx=58, pady=30):
    from render_v2 import pill
    return pill(text, size, fill, fg, padx, pady)


@lru_cache(maxsize=None)
def txt(text, size, color=CREAMT, path=BLACK, shadow=True):
    sp = label(text, path, size, color)
    return bake_shadow(sp, (4, 8), 10, 140, (0, 0, 0)) if shadow else sp


@lru_cache(maxsize=None)
def crescent(size, light=GOLD_L, dark=GOLD_M, glow=True):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size - 1, size - 1), fill=255)
    cut = Image.new("L", (size, size), 0)
    ImageDraw.Draw(cut).ellipse((size * .27, -size * .08, size * 1.2, size * .92), fill=255)
    m = ImageChops.subtract(m, cut).filter(ImageFilter.GaussianBlur(.8))
    im = vgrad(size, size, light, dark).convert("RGBA")
    im.putalpha(m)
    return bake_shadow(im, (0, 0), size // 5, 210, (255, 205, 90)) if glow else im


@lru_cache(maxsize=None)
def star5(size, color=GOLD_L):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = size / 2 * (1 if i % 2 == 0 else .42)
        pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
    ImageDraw.Draw(im).polygon(pts, fill=color + (255,))
    return bake_shadow(im, (0, 0), size // 4, 200, (255, 210, 100))


@lru_cache(maxsize=None)
def lantern(w=150, h=280):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = w / 2
    d.ellipse((cx - 9, 2, cx + 9, 22), outline=GOLD, width=4)
    d.polygon([(cx - 16, 24), (cx + 16, 24), (cx + w * .34, 72), (cx - w * .34, 72)], fill=GOLD)
    bt, bb = 72, h - 72
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(cx - w * .34, bt), (cx + w * .34, bt), (cx + w * .46, (bt + bb) / 2), (cx + w * .34, bb),
                                  (cx - w * .34, bb), (cx - w * .46, (bt + bb) / 2)], fill=255)
    im.paste(vgrad(w, h, (255, 238, 160), (246, 150, 40)).convert("RGBA"), (0, 0), mask)
    for k in (-.2, 0, .2):
        d.line((cx + k * w, bt + 4, cx + k * w * 1.15, bb - 4), fill=GOLD_D, width=4)
    d.polygon([(cx - w * .34, bb), (cx + w * .34, bb), (cx + 14, h - 34), (cx - 14, h - 34)], fill=GOLD)
    d.line((cx, h - 34, cx, h - 8), fill=GOLD, width=6)
    d.ellipse((cx - 8, h - 16, cx + 8, h), fill=GOLD_L)
    return bake_shadow(im, (0, 0), 22, 200, (255, 200, 80))


@lru_cache(maxsize=None)
def skyline():
    h = 250
    im = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = NIGHT + (255,)
    d.rectangle((0, 170, W, h), fill=c)
    for cx, r in [(330, 120), (830, 80)]:
        d.pieslice((cx - r, 170 - r, cx + r, 170 + r), 180, 360, fill=c)
        d.rectangle((cx - 6, 170 - r - 36, cx + 6, 170 - r), fill=c)
        d.ellipse((cx - 14, 170 - r - 58, cx + 14, 170 - r - 30), fill=c)
    for x, hh in [(110, 150), (560, 170), (1000, 130)]:
        d.rectangle((x - 18, 170 - hh, x + 18, 175), fill=c)
        d.polygon([(x - 22, 170 - hh), (x + 22, 170 - hh), (x, 170 - hh - 50)], fill=c)
        d.ellipse((x - 9, 170 - hh - 66, x + 9, 170 - hh - 46), fill=c)
    for x, y in [(110, 70), (560, 50), (1000, 90), (300, 150), (360, 150), (800, 150), (860, 150), (200, 200), (700, 200)]:
        d.rounded_rectangle((x - 6, y - 10, x + 6, y + 10), radius=5, fill=(255, 205, 100, 230))
    return im


def glyph(d, kind, cx, cy, r, accent):
    wht = (255, 255, 255)
    w = max(3, int(r * .24))
    if kind == "check":
        d.line((cx - r * .5, cy + r * .05, cx - r * .1, cy + r * .45, cx + r * .55, cy - r * .4), fill=wht, width=w, joint="curve")
    elif kind == "x":
        d.line((cx - r * .4, cy - r * .4, cx + r * .4, cy + r * .4), fill=wht, width=w)
        d.line((cx + r * .4, cy - r * .4, cx - r * .4, cy + r * .4), fill=wht, width=w)
    elif kind == "star":
        pts = [(cx + r * (1 if i % 2 == 0 else .42) * math.cos(-math.pi / 2 + i * math.pi / 5),
                cy + r * (1 if i % 2 == 0 else .42) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        d.polygon(pts, fill=wht)
    elif kind == "moon":
        d.ellipse((cx - r * .6, cy - r * .6, cx + r * .6, cy + r * .6), fill=wht)
        d.ellipse((cx - r * .2, cy - r * .75, cx + r * .9, cy + r * .45), fill=accent)
    elif kind == "heart":
        d.ellipse((cx - r * .62, cy - r * .55, cx + .02 * r, cy + r * .1), fill=wht)
        d.ellipse((cx - .02 * r, cy - r * .55, cx + r * .62, cy + r * .1), fill=wht)
        d.polygon([(cx - r * .6, cy - r * .1), (cx + r * .6, cy - r * .1), (cx, cy + r * .68)], fill=wht)
    elif kind == "clock":
        d.ellipse((cx - r * .62, cy - r * .62, cx + r * .62, cy + r * .62), outline=wht, width=w)
        d.line((cx, cy, cx, cy - r * .38), fill=wht, width=w)
        d.line((cx, cy, cx + r * .3, cy + r * .12), fill=wht, width=w)


@lru_cache(maxsize=None)
def item(text, accent, kind, w=900, h=130):
    sp = card_sprite(w, h, accent).copy()
    P = 94
    d = ImageDraw.Draw(sp)
    d.ellipse((P + 34, P + 20, P + 34 + 90, P + 20 + 90), fill=accent)
    glyph(d, kind, P + 34 + 45, P + 20 + 45, 32, accent)
    size = 46
    while font(XBOLD, size).getlength(text) > w - 210 and size > 24:
        size -= 2
    d.text((P + 146, P + h / 2), text, font=font(XBOLD, size), fill=INKN, anchor="lm")
    return sp


@lru_cache(maxsize=None)
def card_sprite(w, h, accent):
    from render_v2 import card
    return card(w, h, accent)


@lru_cache(maxsize=None)
def heart(size=300):
    s = size
    m = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((s * .06, s * .1, s * .54, s * .58), fill=255)
    d.ellipse((s * .46, s * .1, s * .94, s * .58), fill=255)
    d.polygon([(s * .09, s * .43), (s * .91, s * .43), (s * .5, s * .93)], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(1.5))
    im = vgrad(s, s, (255, 140, 165), (205, 50, 90)).convert("RGBA")
    im.putalpha(m)
    hl = Image.new("L", (s, s), 0)
    ImageDraw.Draw(hl).ellipse((s * .14, s * .16, s * .4, s * .34), fill=140)
    im.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(6)), m))
    return bake_shadow(im, (0, 0), s // 6, 190, (255, 120, 150))


@lru_cache(maxsize=None)
def quran(w=560):
    h = int(w * .62)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(8, h * .18), (w / 2, h * .1), (w - 8, h * .18), (w - 8, h * .98), (w / 2, h * .9), (8, h * .98)], fill=(10, 100, 78))
    d.polygon([(22, h * .12), (w / 2 - 6, h * .2), (w / 2 - 6, h * .88), (22, h * .8)], fill=(255, 250, 236))
    d.polygon([(w - 22, h * .12), (w / 2 + 6, h * .2), (w / 2 + 6, h * .88), (w - 22, h * .8)], fill=(250, 244, 228))
    for side in (0, 1):
        for i in range(6):
            y = h * (.3 + i * .09)
            x0 = 52 + side * (w / 2 + 6 - 22)
            d.rounded_rectangle((x0, y, x0 + (w / 2 - 80) * (.55 + .45 * ((i * 7 + side * 3) % 5) / 4), y + 8), radius=4,
                                fill=(210, 170, 70) if i % 3 == 0 else (150, 130, 110))
    d.ellipse((w / 2 - 38, h * .08 - 6, w / 2 + 38, h * .08 + 50), fill=GOLD, outline=GOLD_D, width=3)
    return bake_shadow(im, (0, 14), 22, 150, (255, 200, 90))


# ------------------------------------------------------------------ background layers
@lru_cache(maxsize=None)
def background():
    bw, bh = W + 240, H + 320
    y = np.linspace(0, 1, bh)[:, None, None]
    top, mid, bot = np.array([8, 14, 40], np.float32), np.array([18, 46, 92], np.float32), np.array([10, 84, 86], np.float32)
    arr = np.where(y < .6, top * (1 - y / .6) + mid * (y / .6), mid * (1 - (y - .6) / .4) + bot * ((y - .6) / .4))
    xx = np.linspace(-1, 1, bw)[None, :, None]
    arr = arr + np.exp(-((xx) ** 2 + ((y - .3) * 1.6) ** 2) * 2.2) * np.array([30, 24, 8], np.float32)
    return Image.fromarray(np.clip(np.repeat(arr, 1, axis=1) * np.ones((1, bw, 1)), 0, 255).astype(np.uint8), "RGB").convert("RGBA")


_RNG = np.random.default_rng(11)
STARS = [(_RNG.uniform(0, W), _RNG.uniform(0, H * .85), _RNG.uniform(1, 3.2), _RNG.uniform(0, 6.28), _RNG.uniform(1, 3)) for _ in range(130)]


def sky(fr, t):
    d = OD(fr)
    for x, y, r, ph, sp in STARS:
        a = int(90 + 150 * (.5 + .5 * math.sin(t * sp + ph)))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 244, 210, a))
        if r > 2.6:
            d.line((x - r * 3, y, x + r * 3, y), fill=(255, 244, 210, a // 2), width=1)
            d.line((x, y - r * 3, x, y + r * 3), fill=(255, 244, 210, a // 2), width=1)
    d.done()
    # corner crescent
    put2(fr, crescent(190), 905 + math.sin(t * .6) * 6, 380, 1, .55, 12)


def hang(fr, t):
    for px, rope, (lw, lh), amp, per, ph in [(120, 150, (150, 280), .09, 3.3, 0), (965, 300, (118, 220), .07, 2.7, 1.5)]:
        th = amp * math.sin(t * 2 * math.pi / per + ph)
        L = rope + lh / 2
        cx, cy = px + L * math.sin(th), -30 + L * math.cos(th)
        d = ImageDraw.Draw(fr, "RGBA")
        d.line((px, -30, cx - (lh / 2 - 14) * math.sin(th) * -1 * 0 + 0, cy - lh / 2 + 14), fill=GOLD_D + (230,), width=3)
        put2(fr, lantern(lw, lh), cx, cy, 1, 1, math.degrees(th))


def rays(fr, t, cx, cy, alpha, color=GOLD_L, rad=560, n=18, spd=16):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i in range(n):
        a0 = math.radians(spd * t) + i * 2 * math.pi / n
        a1 = a0 + math.pi / n * .8
        d.polygon([(cx, cy), (cx + 2000 * math.cos(a0), cy + 2000 * math.sin(a0)), (cx + 2000 * math.cos(a1), cy + 2000 * math.sin(a1))],
                  fill=color + (255,))
    yy, xx = np.mgrid[0:H:4, 0:W:4].astype(np.float32)
    m = np.clip(1 - np.hypot(xx - cx, yy - cy) / rad, 0, 1) ** 1.2
    mk = Image.fromarray((m * 255 * alpha * .55).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    ov.putalpha(ImageChops.multiply(ov.getchannel("A"), mk))
    fr.alpha_composite(ov)


def confetti(fr, t, t0, cx, cy, n=80, seed=5, dur=2.8):
    if t < t0 or t > t0 + dur:
        return
    rng = np.random.default_rng(seed)
    d = OD(fr)
    tau = t - t0
    cols = [GOLD, GOLD_L, (255, 255, 255), EMER, (120, 170, 255)]
    for i in range(n):
        ang = rng.uniform(-math.pi, 0) if i % 3 else rng.uniform(-math.pi, math.pi)
        spd = rng.uniform(450, 1300)
        x = cx + math.cos(ang) * spd * (1 - math.exp(-tau * 3)) / 3
        y = cy + math.sin(ang) * spd * (1 - math.exp(-tau * 3)) / 3 + 520 * tau * tau
        s = rng.uniform(12, 28)
        a = rng.uniform(0, 6.28) + tau * rng.uniform(-9, 9)
        al = int(255 * clamp(1 - (tau - dur * .6) / (dur * .4)))
        col = cols[i % len(cols)] + (al,)
        if i % 3 == 0:  # tiny 4-point star
            pts = [(x + s * math.cos(a + k * 1.571) * (1 if k % 2 == 0 else .35), y + s * math.sin(a + k * 1.571) * (1 if k % 2 == 0 else .35)) for k in range(4)]
        elif i % 3 == 1:
            sq = abs(math.cos(tau * 8 + i))
            pts = [(x + s * math.cos(a) * sq, y + s * math.sin(a)), (x + s * .5 * math.cos(a + 1.57), y + s * .5 * math.sin(a + 1.57)),
                   (x - s * math.cos(a) * sq, y - s * math.sin(a)), (x - s * .5 * math.cos(a + 1.57), y - s * .5 * math.sin(a + 1.57))]
        else:
            pts = [(x + s * .8 * math.cos(a + k * 2.094), y + s * .8 * math.sin(a + k * 2.094)) for k in range(3)]
        d.polygon(pts, fill=col)
    d.done()


def ripple(fr, t, t0, cx, cy, color=GOLD_L, maxr=170):
    p = (t - t0) / .6
    if 0 <= p <= 1:
        r = 30 + maxr * ease_out(p)
        o = OD(fr)
        o.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color + (int(220 * (1 - p)),), width=int(10 * (1 - p)) + 2)
        o.done()


# ------------------------------------------------------------------ scene helpers
def show(fr, sp, t, t0, t1, cx, cy, d=.4, rot=0.0, fout=.3, side=0):
    """Pop in at t0 (with settle blur), fade/slide out ending at t1."""
    if t < t0 or t >= t1:
        return
    sc, a = pop(t, t0, d)
    o = ease_in_out((t - (t1 - fout)) / fout)
    put2(fr, sp, cx + side * o * 700, cy - (0 if side else o * 70), sc * (1 - .08 * o), a * (1 - o), rot,
         blur=max(0, (1 - clamp((t - t0) / d)) * 10) + o * 6)


def card_in(fr, t, t0, t1, sp, x, y, rot=0.0, frm=(1000, 0), dur=.45, fout=.25):
    if t < t0 or t >= t1:
        return
    (cx, cy), vel = fly(t, t0, dur, (x + frm[0], y + frm[1]), (x, y), ease_out)
    o = ease_in_out((t - (t1 - fout)) / fout)
    put2(fr, sp, cx, cy, 1, ease_out((t - t0) / .15) * (1 - o), rot + (1 - clamp((t - t0) / dur)) * 8 * (1 if frm[0] > 0 else -1), vel=vel)


def header(fr, t, num, t_num, t_end, title, t_title, tsize, sub=None, t_sub=0, sub_fill=EMER):
    show(fr, gb(num, 120), t, t_num, t_end, W / 2, 440, .5, (1 - clamp((t - t_num) / .5)) * -50 * 0)
    if t >= t_title:
        show(fr, gb(title, tsize), t, t_title, t_end, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    if sub and t >= t_sub:
        show(fr, pillg(sub, 46, sub_fill, (255, 255, 255), 44, 20), t, t_sub, t_end, W / 2, 790, .45, -2)


# ------------------------------------------------------------------ scenes
def scene_hook(fr, t):
    E = CUTS[0] + .05
    # A: greeting
    show(fr, gb("ASSALAMUALAIKUM", 82), t, .28, 2.75, W / 2, 760)
    show(fr, txt("WARAHMATULLAHI", 66), t, gwt(0, "warahmatullahi"), 2.75, W / 2, 880)
    show(fr, txt("WABARAKATUH", 66), t, gwt(0, "wabarakatuh"), 2.75, W / 2, 970)
    show(fr, crescent(320), t, .5, 2.75, W / 2, 1180, .6, 8)
    # B: Ramadan semakin dekat
    if 2.92 <= t < 6.3:
        rays(fr, t, W / 2, 760, ease_out((t - 2.92) / .3), GOLD_L)
    show(fr, crescent(300), t, 2.92, 6.3, W / 2, 520, .6, 10)
    show(fr, gb("RAMADAN", 170), t, gwt(1, "ramadan"), 6.3, W / 2, 800, .5)
    show(fr, pillg("SEMAKIN DEKAT!", 62), t, gwt(1, "semakin"), 6.3, W / 2, 1000, .45, -3)
    confetti(fr, t, 2.95, W / 2, 800, 50, 2, 2.0)
    # C: dah bersedia?
    show(fr, txt("PERSOALANNYA...", 78), t, 6.54, 10.9, W / 2, 600, .4)
    tb = 8.66
    if tb <= t < 10.9:
        shake = math.sin((t - tb) * 40) * 10 * (1 - clamp((t - tb) / .5))
        show(fr, wb("DAH", 230), t, tb - .05, 10.9, W / 2 + shake, 820, .5)
        show(fr, gb("BERSEDIA?", 150), t, tb + .02, 10.9, W / 2 + shake, 1030, .5)
    show(fr, pillg("Sebenarnya...", 56, EMER, (255, 255, 255)), t, gwt(4, "sebenarnya"), 10.9, W / 2, 1230, .4, -2)
    # D: no need to wait
    show(fr, txt("TAK PERLU TUNGGU", 100), t, gwt(5, "tak"), E, W / 2, 640, .45)
    show(fr, gb("RAMADAN", 190), t, gwt(5, "ramadan"), E, W / 2, 830 + math.sin(t * 3) * 7, .5)
    show(fr, txt("UNTUK MULA BUAT KEBAIKAN", 58), t, gwt(5, "mula"), E, W / 2, 1010, .4)
    tp = gwt(6, "persediaan")
    if tp <= t < E:
        rays(fr, t, W / 2, 1200, ease_out((t - tp) / .3), GOLD_L, 480)
    show(fr, pillg("BERMULA HARI INI!", 74), t, gwt(6, "bermula"), E, W / 2, 1200, .5, -2)
    confetti(fr, t, gwt(6, "hari"), W / 2, 1200, 60, 4, 2.2)


def scene_solat(fr, t):
    a, E = CUTS[0], CUTS[1] + .05
    tt = gwt(7, "solat")
    if a + .3 <= t < E:
        rays(fr, t, W / 2, 640, ease_out((t - tt) / .5), GOLD_L, 560, 20, 12)
    header(fr, t, "01", a + .15, E, "SOLAT", tt, 230, "LIMA WAKTU", gwt(7, "lima"))
    card_in(fr, t, gwt(8, "awal"), E, item("Solat di awal waktu", GOLD_M, "clock"), W / 2, 1010, -1.5)
    card_in(fr, t, gwt(8, "perbaiki"), E, item("Perbaiki kekhusyukan", EMER, "heart"), W / 2, 1160, 1.5, (-1000, 0))
    tk = gwt(9, "keutamaan")
    card_in(fr, t, gwt(9, "jadikan"), E, item("Solat sebagai keutamaan", (80, 110, 220), "star"), W / 2, 1310, -1.5)
    ripple(fr, t, tk, W / 2 - 340, 1310)


def scene_quran(fr, t):
    a, E = CUTS[1], CUTS[2] + .05
    tq = gwt(10, "biasakan")
    header(fr, t, "02", a + .15, E, "AL-QURAN", tq, 170, "BACA SETIAP HARI", gwt(10, "membaca"))
    tb = gwt(10, "membaca")
    show(fr, quran(), t, tb, E, W / 2, 1020 + math.sin(t * 2) * 8, .6, math.sin(t * 1.4) * 2)
    if tb <= t < E:
        rays(fr, t, W / 2, 1000, ease_out((t - tb) / .5) * .8, GOLD_L, 440, 16, 10)
    # 7-day dots fill while "beberapa ayat sehari" is spoken
    t0, t1 = gwt(12, "walaupun"), gwt(12, "istiqamah")
    if t >= t0 - .1:
        n = clamp((t - t0) / (t1 - t0 + .2)) * 7
        d = OD(fr)
        for i in range(7):
            x = W / 2 - 270 + i * 90
            r = 26
            d.ellipse((x - r, 1290 - r, x + r, 1290 + r), outline=GOLD_L + (255,), width=4, fill=(255, 255, 255, 25))
            if n >= i + 1:
                k = ease_out_back((n - i - 1) / .6) if n < i + 1.6 else 1
                rr = r * .72 * cr(k, 0, 1.2)
                d.ellipse((x - rr, 1290 - rr, x + rr, 1290 + rr), fill=GOLD + (255,))
        d.done()
        if n >= 7:
            ripple(fr, t, t1 + .2, W / 2, 1290, GOLD_L, 220)
    tl = gwt(13, "biarlah")
    show(fr, pillg("SEDIKIT, ASALKAN BERTERUSAN", 44, GOLD, padx=40, pady=24), t, tl, E, W / 2, 1375, .45, -2)


def scene_puasa(fr, t):
    a, E = CUTS[2], CUTS[3] + .05
    tt = gwt(15, "latih") if False else gwt(14, "ketiga")
    header(fr, t, "03", a + .15, E, "PUASA SUNAT", tt + .05, 125, "IKUT KEMAMPUAN", gwt(15, "puasa"))
    days = ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Aha"]
    tc, ti, tk = gwt(16, "mulakan"), gwt(16, "isnin"), gwt(16, "khamis")
    d = OD(fr)
    for i, dn in enumerate(days):
        t0 = tc + i * .08
        if t < t0 or t >= E:
            continue
        p = ease_out_back((t - t0) / .4)
        x, y = W / 2 - 456 + i * 132 + 59, 1020
        hl = (i == 0 and t >= ti) or (i == 3 and t >= tk)
        w2, h2 = 59 * cr(p, 0, 1.15), 82 * cr(p, 0, 1.15)
        d.rounded_rectangle((x - w2, y - h2, x + w2, y + h2), radius=24, fill=(GOLD + (255,)) if hl else (255, 255, 255, 40),
                            outline=(GOLD_L + (255,)) if hl else (255, 255, 255, 90), width=3)
        d.text((x, y - 36), dn, font=font(XBOLD, 38), fill=INKN if hl else CREAMT, anchor="mm")
        if hl:
            d.done()
            put2(fr, crescent(58, (255, 255, 255), (230, 215, 190), False), x, y + 26, 1, 1, 0)
            d = OD(fr)
    d.done()
    ripple(fr, t, ti, W / 2 - 456 + 59, 1020)
    ripple(fr, t, tk, W / 2 - 456 + 3 * 132 + 59, 1020)
    card_in(fr, t, gwt(17, "membiasakan"), E, item("Biasakan diri", EMER, "moon"), W / 2, 1230, -1.5)
    card_in(fr, t, gwt(17, "menyediakan"), E, item("Sedia tubuh & jiwa", GOLD_M, "heart"), W / 2, 1360, 1.5, (-1000, 0))
    tr = gwt(17, "ramadan")
    confetti(fr, t, tr, W / 2, 1100, 40, 8, 1.8)


def scene_istighfar(fr, t):
    a, E = CUTS[3], CUTS[4] + .05
    header(fr, t, "04", a + .15, E, "ISTIGHFAR", gwt(18, "keempat") + .1, 140, "BERSIHKAN HATI", gwt(18, "bersihkan"))
    th = gwt(18, "memperbanyakkan")
    pulse = 1 + .05 * math.sin(t * 5)
    show(fr, heart(300), t, th, E, W / 2, 1010, .6, 0)
    if t >= th:
        for k in range(3):
            ripple(fr, t, th + .3 + k * 1.2 + ((t - th) // 3.6) * 3.6 * 0, W / 2, 1010, (255, 160, 185), 260)
    # "Astaghfirullah" floats up from the heart while asking for forgiveness
    tm = gwt(19, "mohon")
    if tm <= t < E:
        for k in range(4):
            p = ((t - tm - k * .55) % 2.4) / 2.4
            if t < tm + k * .55:
                continue
            x = W / 2 + (-230 + k * 150) + math.sin(p * 6 + k) * 40
            y = 1100 - p * 200
            put2(fr, txt("Astaghfirullah", 40, GOLD_L, SEMI), x, y, 1, math.sin(math.pi * clamp(p)) ** .6 * .95, 0)
    card_in(fr, t, gwt(20, "kurangkan"), E, item("Kurangkan yang sia-sia", ROSE, "x"), W / 2, 1250, -1.5)
    card_in(fr, t, gwt(21, "gantikan"), E, item("Ganti dengan manfaat", EMER, "check"), W / 2, 1385, 1.5, (-1000, 0))


def scene_istiqamah(fr, t):
    a, E = CUTS[4], CUTS[5] + .05
    header(fr, t, "05", a + .15, E, "ISTIQAMAH", gwt(22, "kelima") + .1, 140, "SATU AMALAN BAIK", gwt(23, "pilih"))
    tk = 76.2
    card_in(fr, t, gwt(24, "jangan"), tk, item("Bukan banyaknya amalan", ROSE, "x"), W / 2, 1010, -1.5)
    card_in(fr, t, gwt(24, "istiqamah"), tk, item("Tapi konsisten", EMER, "check"), W / 2, 1160, 1.5, (-1000, 0))
    # INGAT!
    ti = PH[25][0]
    if ti <= t < 77.4:
        rays(fr, t, W / 2, 1000, ease_out((t - ti) / .2), GOLD_L, 700, 22, 40)
    show(fr, gb("INGAT!", 210), t, ti, 77.4, W / 2, 1000, .35, -3, .2)
    ts = gwt(26, "perubahan")
    if t >= ts:
        # little steps -> big change: five stairs rise, a star climbs them
        d = ImageDraw.Draw(fr, "RGBA")
        for i in range(5):
            t0 = ts + i * .42
            if t < t0:
                continue
            p = ease_out_back((t - t0) / .35)
            hh = (70 + i * 62) * cr(p, 0, 1.1)
            x0 = W / 2 - 400 + i * 160
            d.rounded_rectangle((x0, 1380 - hh, x0 + 150, 1380), radius=18, fill=GOLD_L + (255,) if i == 4 else GOLD + (255,),
                                outline=GOLD_D + (255,), width=4)
        k = clamp((t - ts) / 2.2) * 4
        i0 = min(int(k), 3)
        f = k - i0
        hop = abs(math.sin(f * math.pi)) * 90
        sx = W / 2 - 400 + (i0 + f) * 160 + 75
        sy = 1380 - (70 + (i0 + f) * 62) - 60 - hop
        put2(fr, star5(110), sx, sy, 1, 1, t * 80)
        show(fr, txt("LANGKAH KECIL", 56), t, ts + .2, E, W / 2, 880, .4, -3)
        show(fr, gb("PERUBAHAN BESAR", 70), t, ts + 1.4, E, W / 2, 975, .45, -2)


def scene_close(fr, t):
    a = CUTS[5]
    sky_boost = clamp((t - a) / 1.0)
    # A: Ramadan belum tiba...
    show(fr, crescent(380), t, 80.2, 85.4, W / 2, 620, .7, 8)
    show(fr, txt("RAMADAN", 92), t, gwt(27, "ramadan"), 81.6, W / 2, 940, .45)
    show(fr, txt("BELUM TIBA...", 92), t, gwt(27, "belum"), 81.6, W / 2, 1050, .45)
    tp = gwt(28, "pahala")
    if tp <= t < 85.4:
        rays(fr, t, W / 2, 1000, ease_out((t - tp) / .3), GOLD_L, 560)
    show(fr, gb("PAHALA", 190), t, tp, 85.4, W / 2, 950, .5)
    show(fr, pillg("BOLEH BERMULA SEKARANG", 48, GOLD, padx=44, pady=24), t, gwt(28, "usahakan"), 85.4, W / 2, 1150, .45, -2)
    confetti(fr, t, gwt(28, "usahakan"), W / 2, 1000, 50, 12, 2.2)
    # B: jangan tunggu esok
    te = gwt(29, "jangan")
    show(fr, wb("JANGAN", 150), t, te, 88.7, W / 2, 740, .45)
    show(fr, wb("TUNGGU", 150), t, gwt(29, "tunggu"), 88.7, W / 2, 890, .45)
    tsk = gwt(29, "esok")
    if tsk <= t < 88.7:
        show(fr, item("ESOK", ROSE, "x", 520, 130), t, tsk, 88.7, W / 2, 1090, .45, -2)
    show(fr, txt("untuk menjadi lebih baik", 56, GOLD_L, XBOLD), t, gwt(29, "menjadi"), 88.7, W / 2, 1250, .4)
    # C: mulakan hari ini + progress bar
    tm = PH[30][0]
    if tm <= t < 91.7:
        rays(fr, t, W / 2, 800, ease_out((t - tm) / .3), GOLD_L, 620, 20, 30)
    sc = 1 + .04 * math.sin((t - tm) * 7)
    show(fr, pillg("MULAKAN HARI INI", 84, GOLD, padx=64, pady=40), t, tm, 91.75, W / 2, 800, .45, -2)
    tb0, tb1 = PH[31][0], PH[31][1]
    if tb0 <= t < 91.75:
        p = ease_out(clamp((t - tb0 + .05) / (tb1 - tb0 + .2)))
        d = OD(fr)
        d.rounded_rectangle((W / 2 - 400, 1040, W / 2 + 400, 1096), radius=28, fill=(255, 255, 255, 50), outline=(255, 255, 255, 120), width=3)
        d.rounded_rectangle((W / 2 - 400, 1040, W / 2 - 400 + 800 * p, 1096), radius=28, fill=GOLD + (255,))
        d.text((W / 2, 1150), "sedikit demi sedikit", font=font(XBOLD, 52), fill=GOLD_L, anchor="mm")
        d.done()
    # E: semoga Allah ... bertemu Ramadan
    t92 = PH[32][0]
    if t92 <= t < 97.6:
        for k, (x, y, w2, h2) in enumerate([(150, 1000, 130, 240), (930, 1040, 130, 240)]):
            show(fr, lantern(w2, h2), t, t92 + k * .3, 97.6, x, y + math.sin(t * 2 + k) * 14, .6, math.sin(t * 1.6 + k) * 5)
    show(fr, txt("SEMOGA ALLAH", 86), t, t92 + .1, 97.6, W / 2, 700, .5)
    show(fr, txt("SAMPAIKAN KITA", 86), t, gwt(32, "memberikan"), 97.6, W / 2, 810, .5)
    show(fr, txt("KE", 70, GOLD_L), t, gwt(32, "bertemu"), 97.6, W / 2, 920, .4)
    show(fr, gb("RAMADAN", 190), t, gwt(32, "ramadan"), 97.6, W / 2, 1090 + math.sin(t * 2.5) * 7, .55)
    show(fr, crescent(160), t, gwt(32, "menjalaninya"), 97.6, W / 2, 440, .5, 8)
    # F: finale
    t33 = PH[33][0]
    show(fr, txt("RAMADAN BELUM TIBA,", 72), t, t33, 101.9, W / 2, 640, .45)
    show(fr, gb("TAPI", 110), t, PH[34][0] - .05, 101.9, W / 2 - 250, 800, .4)
    show(fr, gb("PERSEDIAAN KITA", 100), t, gwt(34, "persediaan"), 101.9, W / 2, 930, .5)
    th = gwt(34, "bermula")
    if th <= t:
        rays(fr, t, W / 2, 1180, ease_out((t - th) / .3), GOLD_L, 620, 20, 30)
    show(fr, pillg("BOLEH BERMULA HARI INI!", 56, GOLD, padx=48, pady=30), t, th, 101.9, W / 2, 1180, .5, -2)
    confetti(fr, t, gwt(34, "hari"), W / 2, 1180, 90, 21, 3.5)


SCENES = [(0, scene_hook), (CUTS[0], scene_solat), (CUTS[1], scene_quran), (CUTS[2], scene_puasa),
          (CUTS[3], scene_istighfar), (CUTS[4], scene_istiqamah), (CUTS[5], scene_close)]
WIN = .3


def transition(fr, t):
    for k, c in enumerate(CUTS):
        p = (t - (c - WIN)) / (2 * WIN)
        if not 0 <= p <= 1:
            continue
        env = min(1.0, math.sin(math.pi * p) ** .55)
        kind = k % 4
        if kind == 0:
            fr.alpha_composite(Image.new("RGBA", (W, H), GOLD + (int(255 * env),)))
        elif kind == 1:
            layer = Image.new("RGBA", (W, H), EMER + (int(255 * env),))
            d = ImageDraw.Draw(layer)
            for i in range(24):
                a0 = math.radians(40 * t) + i * 2 * math.pi / 24
                a1 = a0 + math.pi / 24 * .9
                d.polygon([(W / 2, H * .45), (W / 2 + 2600 * math.cos(a0), H * .45 + 2600 * math.sin(a0)),
                           (W / 2 + 2600 * math.cos(a1), H * .45 + 2600 * math.sin(a1))], fill=GOLD_L + (int(255 * env * .9),))
            fr.alpha_composite(layer)
        elif kind == 2:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            r = 2200 * ease_in_out(min(1, env * 1.15))
            ImageDraw.Draw(layer).ellipse((W / 2 - r, H * .45 - r, W / 2 + r, H * .45 + r), fill=(14, 100, 96, 255))
            fr.alpha_composite(layer)
        else:
            shift = math.sin(math.pi * p) * 260
            arr = np.asarray(fr.convert("RGB"), np.float32)
            acc = np.zeros_like(arr)
            for i in range(9):
                acc += np.roll(arr, int(shift * (i / 8 - .5)), 1)
            out = Image.fromarray((acc / 9).astype(np.uint8)).convert("RGBA")
            out.alpha_composite(Image.new("RGBA", (W, H), GOLD_L + (int(200 * env ** 2),)))
            fr.paste(out)


def chrome(fr, t, total):
    d = ImageDraw.Draw(fr)
    d.rectangle((0, 0, int(W * t / total), 12), fill=GOLD)
    d.text((W / 2, 200), "BELUM RAMADAN, TAPI BOLEH MULA!", font=font(BOLD, 32), fill=GOLD_L, anchor="mm")
    if CUTS[0] <= t < CUTS[5]:
        step = sum(t >= c for c in CUTS[:5]) - 1
        for i in range(5):
            x = W / 2 + (i - 2) * 100
            on, done = i == step, i < step
            col = GOLD if on else (EMER if done else (90, 110, 150))
            w = 80 if on else 50
            d.rounded_rectangle((x - w / 2, 250, x + w / 2, 262), radius=6, fill=col)


@lru_cache(maxsize=None)
def layout(gi):
    f = font(XBOLD, 56)
    sp = f.getlength(" ")
    words = [w for w in WORDS if w["seg"] in CAPTION_GROUPS[gi]]
    lines, cur, cw = [], [], 0
    for w in words:
        ww = f.getlength(w["t"])
        if cur and cw + sp + ww > 940:
            lines.append((cur, cw))
            cur, cw = [], 0
        cw += (sp if cur else 0) + ww
        cur.append((w, ww))
    if cur:
        lines.append((cur, cw))
    return lines


def caption(fr, t):
    gi = None
    for i, g in enumerate(CAPTION_GROUPS):
        start = PH[g[0]][0] - .1
        end = PH[CAPTION_GROUPS[i + 1][0]][0] - .12 if i + 1 < len(CAPTION_GROUPS) else 99
        end = min([end] + [c for c in CUTS if start < c < end])
        if start <= t < end:
            gi = i
    if gi is None:
        return
    f = font(XBOLD, 56)
    sp = f.getlength(" ")
    lines = layout(gi)
    lh = 80
    y0 = 1580 - (len(lines) - 1) * lh / 2
    app = ease_out((t - (PH[CAPTION_GROUPS[gi][0]][0] - .1)) / .2)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for li, (ws, lw) in enumerate(lines):
        x = W / 2 - lw / 2
        y = y0 + li * lh + (1 - app) * 30
        for w, ww in ws:
            spoken = t >= w["s"]
            if norm(w["t"]) in HIGHLIGHT and spoken:
                k = ease_out_back((t - w["s"]) / .25)
                pad = 11 * k
                d.rounded_rectangle((x - pad, y - 40 - pad * .4, x + ww + pad, y + 36 + pad * .4), radius=16, fill=GOLD)
                d.text((x, y), w["t"], font=f, fill=INKN, anchor="lm")
            else:
                d.text((x, y), w["t"], font=f, fill=CREAMT + ((255,) if spoken else (100,)), anchor="lm",
                       stroke_width=5, stroke_fill=NIGHT + (230 if spoken else 90,))
            x += ww + sp
    if app < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * app)))
    fr.alpha_composite(layer)


def render_frame(t, total=101.8):
    bg = background()
    ox, oy = 120 + 70 * math.sin(t * .3), 160 + 90 * math.sin(t * .2 + 1)
    fr = bg.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
    sky(fr, t)
    fr.alpha_composite(skyline(), (0, H - 250))
    hang(fr, t)
    [fn for start, fn in SCENES if t >= start][-1](fr, t)
    transition(fr, t)
    chrome(fr, t, total)
    caption(fr, t)
    return finish(fr, t)


@lru_cache(maxsize=None)
def vig():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H * .45) / (H / 2)) ** 2)
    return (np.clip(d - .6, 0, 1) ** 1.6 * 90).astype(np.float32)[:, :, None]


@lru_cache(maxsize=None)
def grain(k):
    return np.random.default_rng(300 + k).normal(0, 2.6, (H, W, 1)).astype(np.float32)


def finish(fr, t):
    rgb = fr.convert("RGB")
    arr = np.asarray(rgb, np.float32)
    small = rgb.resize((W // 8, H // 8), Image.BILINEAR).point(lambda v: max(0, v - 225) * 6)
    bloom = np.asarray(small.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR), np.float32)
    arr = arr + bloom * .3 - vig() * np.array([.9, .8, .6], np.float32) + grain(int(t * FPS) % 3)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ audio
def build_audio(path_out):
    with wave.open(AUDIO) as w:
        sr = w.getframerate()
        voice = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = len(voice)
    mix = voice.copy()
    tt = np.arange(n) / sr
    pad = (np.sin(2 * np.pi * 110 * tt) * .012 + np.sin(2 * np.pi * 164.8 * tt) * .008 + np.sin(2 * np.pi * 220 * tt) * .006)
    pad *= (.6 + .4 * np.sin(2 * np.pi * tt / 9)) * np.clip(tt / 3, 0, 1) * np.clip((n / sr - tt) / 3, 0, 1)
    mix += pad.astype(np.float32)
    rng = np.random.default_rng(9)

    def add(sig, at):
        i = int(at * sr)
        j = min(n, i + len(sig))
        if j > i:
            mix[i:j] += sig[: j - i]

    m = int(.55 * sr)
    for c in CUTS:
        noise = rng.standard_normal(m).astype(np.float32)
        out = np.zeros(m, np.float32)
        y = 0.0
        for k in range(m):
            a = .02 + .5 * math.sin(math.pi * k / m) ** 2
            y += a * (noise[k] - y)
            out[k] = y
        add(out * np.sin(np.pi * np.arange(m) / m) ** 2 * .16, c - .3)
    cm = int(.9 * sr)
    ct = np.arange(cm) / sr
    chime = ((np.sin(2 * np.pi * 1318.5 * ct) + .5 * np.sin(2 * np.pi * 1976 * ct) + .25 * np.sin(2 * np.pi * 2637 * ct)) * np.exp(-ct * 5)).astype(np.float32) * .045
    for i in (1, 3, 6, 7, 10, 14, 18, 22, 25, 28, 30, 33, 34):
        add(chime, PH[i][0])
    mix = np.clip(mix, -1, 1)
    with wave.open(path_out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return n / sr


_TOTAL = [101.8]


def _job(i):
    return render_frame(i / FPS, _TOTAL[0]).tobytes()


def main():
    if "--preview" in sys.argv:
        for arg in sys.argv[sys.argv.index("--preview") + 1:]:
            render_frame(float(arg)).save(f"output/prev_r_{arg}.png")
        return
    mixed = "output/_mix_r.wav"
    total = build_audio(mixed)
    _TOTAL[0] = total
    frames = int(math.ceil(total * FPS))
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", mixed, "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)
    with Pool(4) as pool:
        for i, raw in enumerate(pool.imap(_job, range(frames), chunksize=3)):
            ff.stdin.write(raw)
            if i % 150 == 0:
                print(f"frame {i}/{frames}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
