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
CUTS = [17.95, 28.75, 40.45, 54.45, 66.95, 79.90]  # mid-gaps right before each "Yang pertama/kedua/..."


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
@lru_cache(maxsize=None)
def mosque_big(w=640):
    h = int(w * .72)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c1, c2 = (250, 240, 215), (222, 200, 150)
    gy = h - 20
    d.rectangle((w * .18, h * .55, w * .82, gy), fill=c1)
    d.pieslice((w * .28, h * .12, w * .72, h * .98), 180, 360, fill=GOLD)
    d.pieslice((w * .33, h * .17, w * .67, h * .93), 180, 360, fill=GOLD_L)
    d.rectangle((w * .49, h * .02, w * .51, h * .14), fill=GOLD_D)
    d.ellipse((w * .465, h * -.02, w * .535, h * .06), fill=GOLD)
    for mx in (.1, .9):
        x = w * mx
        d.rectangle((x - w * .035, h * .3, x + w * .035, gy), fill=c2)
        d.polygon([(x - w * .05, h * .3), (x + w * .05, h * .3), (x, h * .12)], fill=GOLD)
        d.rectangle((x - 2, h * .04, x + 2, h * .13), fill=GOLD_D)
        d.ellipse((x - 9, h * .0, x + 9, h * .06), fill=GOLD_L)
    d.rounded_rectangle((w * .44, h * .62, w * .56, gy), radius=int(w * .06), fill=(10, 60, 80))
    for x in (.24, .32, .68, .76):
        d.rounded_rectangle((w * x - 12, h * .66, w * x + 12, h * .78), radius=12, fill=(255, 214, 110))
    return bake_shadow(im, (0, 10), 26, 170, (255, 200, 90))


def slot(fr, t, sp, t0, t1, y=1300, rot=0.0):
    """One-at-a-time keyword card in the lower slot."""
    card_in(fr, t, t0, t1, sp, W / 2, y, rot, (1000 if rot >= 0 else -1000, 0), .45, .2)


def scene_hook(fr, t):
    E = CUTS[0] + .05
    # title (spoken first in the audio)
    show(fr, crescent(420), t, .2, 2.95, W / 2, 620, .7, 8)
    show(fr, wb("BELUM", 130), t, 0.0, 2.95, W / 2, 830, .45)
    show(fr, gb("RAMADAN", 190), t, .54, 2.95, W / 2, 1000, .5)
    show(fr, pillg("TAPI BOLEH MULA!", 62), t, 1.26, 2.95, W / 2, 1200, .5, -3)
    if 1.2 <= t < 2.95:
        rays(fr, t, W / 2, 1000, ease_out((t - 1.2) / .4), GOLD_L, 520)
    # salam
    show(fr, gb("ASSALAMUALAIKUM", 82), t, 3.14, 5.95, W / 2, 800, .5)
    show(fr, txt("WARAHMATULLAHI", 64), t, 3.90, 5.95, W / 2, 920, .45)
    show(fr, txt("WABARAKATUH", 64), t, 4.66, 5.95, W / 2, 1010, .45)
    show(fr, crescent(300), t, 3.3, 5.95, W / 2, 1230, .6, 8)
    # Ramadan semakin dekat
    if 6.56 <= t < 8.3:
        rays(fr, t, W / 2, 760, ease_out((t - 6.56) / .3), GOLD_L)
    show(fr, crescent(300), t, 6.56, 8.3, W / 2, 520, .6, 10)
    show(fr, gb("RAMADAN", 170), t, 6.56, 8.3, W / 2, 800, .5)
    show(fr, pillg("SEMAKIN DEKAT!", 62), t, 6.94, 8.3, W / 2, 1000, .45, -3)
    confetti(fr, t, 7.44, W / 2, 800, 40, 2, 1.6)
    # dah bersedia?
    show(fr, txt("PERSOALANNYA...", 78), t, 8.58, 11.1, W / 2, 600, .4)
    if 9.2 <= t < 11.1:
        shake = math.sin((t - 10.02) * 40) * 10 * (1 - clamp((t - 10.02) / .5)) if t >= 10.02 else 0
        show(fr, wb("DAH", 230), t, 9.2, 11.1, W / 2 + shake, 820, .5)
        show(fr, gb("BERSEDIA?", 150), t, 10.02, 11.1, W / 2 + shake, 1030, .5)
    # tak perlu tunggu Ramadan
    show(fr, txt("TAK PERLU TUNGGU", 100), t, 12.26, E, W / 2, 640, .45)
    show(fr, gb("RAMADAN", 190), t, 13.10, E, W / 2, 830 + math.sin(t * 3) * 7, .5)
    show(fr, pillg("MULA BUAT KEBAIKAN", 52, EMER, (255, 255, 255), 44, 24), t, 13.82, E, W / 2, 1010, .45, -2)
    # persediaan bermula hari ini
    if 16.46 <= t < E:
        rays(fr, t, W / 2, 1230, ease_out((t - 16.46) / .3), GOLD_L, 480)
    show(fr, pillg("BERMULA HARI INI!", 74), t, 16.46, E, W / 2, 1230, .5, -2)
    confetti(fr, t, 16.92, W / 2, 1230, 60, 4, 1.8)


def scene_solat(fr, t):
    a, E = CUTS[0], CUTS[1] + .05
    if 19.66 <= t < E:
        rays(fr, t, W / 2, 1010, ease_out((t - 19.66) / .5), GOLD_L, 600, 20, 12)
    show(fr, gb("01", 120), t, 18.24, E, W / 2, 440, .5)
    show(fr, gb("SOLAT", 230), t, 19.66, E, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    show(fr, pillg("LIMA WAKTU", 46, EMER, (255, 255, 255), 44, 20), t, 19.98, E, W / 2, 790, .45, -2)
    show(fr, mosque_big(), t, 19.98, E, W / 2, 1060 + math.sin(t * 2) * 8, .7)
    slot(fr, t, item("Solat di awal waktu", GOLD_M, "clock"), 22.40, 23.62, 1400, -1.5)
    slot(fr, t, item("Khusyuk", EMER, "heart"), 23.68, 26.0, 1400, 1.5)
    slot(fr, t, item("Jadikan keutamaan", (80, 110, 220), "star"), 26.06, E, 1400, -1.5)
    ripple(fr, t, 26.06, W / 2 - 340, 1400)


def scene_quran(fr, t):
    a, E = CUTS[1], CUTS[2] + .05
    show(fr, gb("02", 120), t, 29.12, E, W / 2, 440, .5)
    show(fr, gb("AL-QURAN", 170), t, 30.98, E, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    show(fr, pillg("BACA SETIAP HARI", 46, EMER, (255, 255, 255), 44, 20), t, 30.60, E, W / 2, 790, .45, -2)
    show(fr, quran(), t, 30.60, E, W / 2, 1020 + math.sin(t * 2) * 8, .6, math.sin(t * 1.4) * 2)
    if 30.6 <= t < E:
        rays(fr, t, W / 2, 1000, ease_out((t - 30.6) / .5) * .8, GOLD_L, 440, 16, 10)
    t0, t1 = 34.34, 36.30
    if t >= t0 - .1:
        n = clamp((t - t0) / (t1 - t0)) * 7
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
            ripple(fr, t, t1 + .1, W / 2, 1290, GOLD_L, 220)
    show(fr, txt("beberapa ayat sehari", 54, GOLD_L, XBOLD), t, 34.34, 36.2, W / 2, 1400, .4)
    show(fr, pillg("ISTIQAMAH", 56, GOLD), t, 36.30, 37.6, W / 2, 1400, .45, -2)
    show(fr, pillg("SEDIKIT, ASALKAN BERTERUSAN", 44, GOLD, padx=40, pady=24), t, 37.72, E, W / 2, 1400, .45, -2)


def scene_puasa(fr, t):
    a, E = CUTS[2], CUTS[3] + .05
    show(fr, gb("03", 120), t, 40.94, E, W / 2, 440, .5)
    show(fr, gb("PUASA SUNAT", 125), t, 42.54, E, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    show(fr, pillg("IKUT KEMAMPUAN", 46, EMER, (255, 255, 255), 44, 20), t, 44.98, E, W / 2, 790, .45, -2)
    days = ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Aha"]
    tc, ti, tk = 44.12, 46.74, 47.26
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
    show(fr, item("Biasakan diri", EMER, "moon"), t, 49.64, E, W / 2, 1230, .45, -1.5)
    show(fr, item("Sedia tubuh & jiwa", GOLD_M, "heart"), t, 50.90, E, W / 2, 1360, .45, 1.5)
    show(fr, gb("RAMADAN", 110), t, 53.66, E, W / 2, 1500, .5)
    confetti(fr, t, 53.66, W / 2, 1400, 40, 8, 1.8)


def scene_istighfar(fr, t):
    a, E = CUTS[3], CUTS[4] + .05
    show(fr, gb("04", 120), t, 55.10, E, W / 2, 440, .5)
    show(fr, pillg("BERSIHKAN HATI", 46, EMER, (255, 255, 255), 44, 20), t, 55.82, E, W / 2, 790, .45, -2)
    show(fr, heart(300), t, 56.34, E, W / 2, 1010, .6, 0)
    show(fr, gb("ISTIGHFAR", 140), t, 57.46, E, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    if t >= 56.5:
        for k in range(3):
            ripple(fr, t, 56.8 + k * 1.2, W / 2, 1010, (255, 160, 185), 260)
    if 58.44 <= t < E:
        for k in range(4):
            if t < 58.44 + k * .55:
                continue
            p = ((t - 58.44 - k * .55) % 2.4) / 2.4
            x = W / 2 + (-230 + k * 150) + math.sin(p * 6 + k) * 40
            y = 1100 - p * 200
            put2(fr, txt("Astaghfirullah", 40, GOLD_L, SEMI), x, y, 1, math.sin(math.pi * clamp(p)) ** .6 * .95, 0)
    show(fr, pillg("KEAMPUNAN", 52, GOLD), t, 59.42, 62.4, W / 2, 1300, .45, -2)
    show(fr, item("Kurangkan yang sia-sia", ROSE, "x"), t, 62.72, E, W / 2, 1250, .45, -1.5)
    show(fr, item("Ganti dengan manfaat", EMER, "check"), t, 64.58, E, W / 2, 1385, .45, 1.5)


def scene_istiqamah(fr, t):
    a, E = CUTS[4], CUTS[5] + .05
    show(fr, gb("05", 120), t, 67.64, E, W / 2, 440, .5)
    show(fr, gb("ISTIQAMAH", 140), t, 68.54, E, W / 2, 620 + math.sin(t * 2.6) * 6, .5)
    show(fr, pillg("SATU AMALAN BAIK", 46, EMER, (255, 255, 255), 44, 20), t, 68.84, E, W / 2, 790, .45, -2)
    show(fr, item("Konsisten", EMER, "check"), t, 70.62, 72.5, W / 2, 1100, .45, 1.5)
    show(fr, item("Bukan banyaknya amalan", ROSE, "x"), t, 72.96, 74.8, W / 2, 1100, .45, -1.5)
    show(fr, item("Tapi istiqamah", EMER, "check"), t, 74.90, 76.0, W / 2, 1100, .45, 1.5)
    ti = 76.12
    if ti <= t < 77.0:
        rays(fr, t, W / 2, 1000, ease_out((t - ti) / .2), GOLD_L, 700, 22, 40)
    show(fr, gb("INGAT!", 210), t, ti, 77.0, W / 2, 1000, .35, -3, .2)
    ts = 77.44
    if t >= ts:
        d = OD(fr)
        for i in range(5):
            t0 = ts + i * .42
            if t < t0:
                continue
            p = ease_out_back((t - t0) / .35)
            hh = (70 + i * 62) * cr(p, 0, 1.1)
            x0 = W / 2 - 400 + i * 160
            d.rounded_rectangle((x0, 1480 - hh, x0 + 150, 1480), radius=18, fill=GOLD_L + (255,) if i == 4 else GOLD + (255,),
                                outline=GOLD_D + (255,), width=4)
        d.done()
        k = clamp((t - ts) / 2.2) * 4
        i0 = min(int(k), 3)
        f = k - i0
        hop = abs(math.sin(f * math.pi)) * 90
        put2(fr, star5(110), W / 2 - 400 + (i0 + f) * 160 + 75, 1480 - (70 + (i0 + f) * 62) - 60 - hop, 1, 1, t * 80)
    show(fr, gb("PERUBAHAN BESAR", 70), t, 77.04, E, W / 2, 900, .45, -2)
    show(fr, txt("LANGKAH KECIL", 60), t, 78.72, E, W / 2, 1010, .4, -3)


def scene_close(fr, t):
    show(fr, crescent(380), t, 80.2, 85.3, W / 2, 620, .7, 8)
    show(fr, txt("RAMADAN", 92), t, 80.20, 81.9, W / 2, 940, .45)
    show(fr, txt("BELUM TIBA...", 92), t, 80.74, 81.9, W / 2, 1050, .45)
    if 82.04 <= t < 85.3:
        rays(fr, t, W / 2, 1000, ease_out((t - 82.04) / .3), GOLD_L, 560)
    show(fr, gb("PAHALA", 190), t, 82.04, 85.3, W / 2, 950, .5)
    show(fr, pillg("BOLEH MULA SEKARANG", 48, GOLD, padx=44, pady=24), t, 83.92, 85.3, W / 2, 1150, .45, -2)
    confetti(fr, t, 83.92, W / 2, 1000, 50, 12, 1.8)
    show(fr, wb("JANGAN", 150), t, 85.34, 87.2, W / 2, 740, .45)
    show(fr, wb("TUNGGU", 150), t, 85.78, 87.2, W / 2, 890, .45)
    show(fr, item("ESOK", ROSE, "x", 520, 130), t, 86.04, 87.2, W / 2, 1090, .45, -2)
    if 87.34 <= t < 91.55:
        rays(fr, t, W / 2, 800, ease_out((t - 87.34) / .3), GOLD_L, 620, 20, 30)
    show(fr, pillg("MULAKAN HARI INI", 84, GOLD, padx=64, pady=40), t, 87.34, 91.55, W / 2, 800, .45, -2)
    if 89.14 <= t < 91.55:
        p = ease_out(clamp((t - 89.14) / (90.9 - 89.14)))
        d = OD(fr)
        d.rounded_rectangle((W / 2 - 400, 1040, W / 2 + 400, 1096), radius=28, fill=(255, 255, 255, 50), outline=(255, 255, 255, 120), width=3)
        d.rounded_rectangle((W / 2 - 400, 1040, W / 2 - 400 + 800 * p, 1096), radius=28, fill=GOLD + (255,))
        d.text((W / 2, 1150), "sedikit demi sedikit", font=font(XBOLD, 52), fill=GOLD_L, anchor="mm")
        d.done()
    if 91.64 <= t < 97.3:
        for k, (x, y, w2, h2) in enumerate([(150, 1000, 130, 240), (930, 1040, 130, 240)]):
            show(fr, lantern(w2, h2), t, 91.64 + k * .3, 97.3, x, y + math.sin(t * 2 + k) * 14, .6, math.sin(t * 1.6 + k) * 5)
    show(fr, txt("SEMOGA ALLAH", 86), t, 91.64, 97.3, W / 2, 700, .5)
    show(fr, txt("SAMPAIKAN KITA", 86), t, 92.42, 97.3, W / 2, 810, .5)
    show(fr, txt("KE", 70, GOLD_L), t, 93.92, 97.3, W / 2, 920, .4)
    show(fr, gb("RAMADAN", 190), t, 94.32, 97.3, W / 2, 1090 + math.sin(t * 2.5) * 7, .55)
    show(fr, crescent(160), t, 95.10, 97.3, W / 2, 440, .5, 8)
    show(fr, txt("RAMADAN BELUM TIBA,", 72), t, 97.42, 101.9, W / 2, 640, .45)
    show(fr, gb("TAPI PERSEDIAAN KITA", 90), t, 99.18, 101.9, W / 2, 860, .5)
    if t >= 100.32:
        rays(fr, t, W / 2, 1180, ease_out((t - 100.32) / .3), GOLD_L, 620, 20, 30)
    show(fr, pillg("BOLEH BERMULA HARI INI!", 56, GOLD, padx=48, pady=30), t, 100.32, 101.9, W / 2, 1180, .5, -2)
    confetti(fr, t, 100.70, W / 2, 1180, 90, 21, 3.5)

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
    for at in (.54, 3.14, 6.56, 10.02, 16.46, 19.66, 30.98, 42.54, 57.46, 70.62, 76.12, 82.04, 87.34, 94.32, 100.32):
        add(chime, at)
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
