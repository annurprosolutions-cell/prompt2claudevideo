"""Render v2: same voiceover/timing as render.py, restyled to mimic the reference
"motion graphic" promo (peach/orange 3D-look): depth-of-field floaters, motion-blurred
whip entrances, glossy balloon text, marker highlight, 3D cursor, sticky notes, ribbon,
confetti, and four different transitions (amber flash, starburst, orange fill, whip blur).

Usage: python3 render_v2.py [--preview SEC ...]      (no args = full video)
Output: output/claude-3-cara-v2.mp4
"""
import math
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

import render as R
from render import (BLACK, BOLD, CAPTION_GROUPS, CUTS, FPS, H, SEGS, SEMI, W, XBOLD, WORDS,
                    build_audio, clamp, ease_in_out, ease_out, ease_out_back, font, norm, wt)

OUT = "output/claude-3-cara-v2.mp4"

# palette (sampled by eye from the reference)
OR = (242, 106, 27)
OR_L = (255, 160, 90)
OR_D = (176, 58, 10)
AMB = (243, 176, 30)
INK = (52, 30, 20)
CREAM = (255, 248, 240)
PEACH = (243, 196, 168)
PURPLE = (123, 87, 160)
GREEN2 = (60, 170, 110)
RED2 = (214, 70, 60)


# ------------------------------------------------------------ sprite effects
def fx(sp, blur=0.0, vx=0.0, vy=0.0):
    """Depth-of-field (gaussian) + directional motion blur on a premultiplied copy."""
    moving = abs(vx) + abs(vy) >= 2
    if blur < 0.5 and not moving:
        return sp
    pad = int(blur * 2.5 + abs(vx) + abs(vy)) + 3
    r, g, b, a = sp.split()
    chans = [ImageChops.multiply(c, a) for c in (r, g, b)] + [a]
    out = []
    for c in chans:
        c = ImageOps.expand(c, pad, 0)
        if blur >= 0.5:
            c = c.filter(ImageFilter.GaussianBlur(blur))
        if moving:
            arr = np.asarray(c, np.float32)
            acc = np.zeros_like(arr)
            n = 8
            for i in range(n):
                f = i / (n - 1) - 0.5
                acc += np.roll(np.roll(arr, int(vy * f), 0), int(vx * f), 1)
            c = Image.fromarray((acc / n).astype(np.uint8))
        out.append(np.asarray(c, np.float32))
    al = out[3]
    safe = np.maximum(al, 1)[:, :, None]
    rgb = np.clip(np.stack(out[:3], axis=2) * 255.0 / safe, 0, 255)
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")


def put2(fr, sp, cx, cy, scale=1.0, alpha=1.0, rot=0.0, vel=(0.0, 0.0), blur=0.0):
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        sp = sp.resize((max(1, int(sp.width * scale)), max(1, int(sp.height * scale))), Image.BILINEAR)
    if rot:
        sp = sp.rotate(rot, resample=Image.BICUBIC, expand=True)
    sp = fx(sp, blur, *vel)
    if alpha < 0.999:
        sp = sp.copy()
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    fr.paste(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)), sp)


def fly(t, t0, dur, p0, p1, ease=ease_out):
    """Position + per-frame velocity (for motion blur) of an element flying p0 -> p1."""
    def pos(tt):
        e = ease((tt - t0) / dur)
        return p0[0] + (p1[0] - p0[0]) * e, p0[1] + (p1[1] - p0[1]) * e
    x, y = pos(t)
    px, py = pos(t - 1 / FPS)
    return (x, y), (x - px, y - py)


def bake_shadow(sp, off=(16, 26), blur=20, alpha=85, color=(160, 80, 40)):
    pad = blur * 3 + max(off)
    big = Image.new("RGBA", (sp.width + 2 * pad, sp.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", big.size, color + (0,))
    sh.putalpha(ImageOps.expand(sp.getchannel("A"), pad, 0).point(lambda v: int(v * alpha / 255)))
    sh = ImageChops.offset(sh, off[0], off[1]).filter(ImageFilter.GaussianBlur(blur))
    big.alpha_composite(sh)
    big.alpha_composite(sp, (pad, pad))
    return big


def vgrad(w, h, top, bot):
    y = np.linspace(0, 1, h)[:, None, None]
    arr = np.array(top)[None, None, :] * (1 - y) + np.array(bot)[None, None, :] * y
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8), "RGB")


# ------------------------------------------------------------ cached sprites
@lru_cache(maxsize=None)
def balloon(text, size, top=OR_L, bot=OR, ext=OR_D):
    """Glossy extruded 'inflated' text like the 'code' letters in the reference."""
    f = font(BLACK, size)
    l, t_, r, b = f.getbbox(text)
    pad = size // 2
    w, h = r - l + 2 * pad, b - t_ + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - l, pad - t_), text, font=f, fill=255)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    depth = max(4, size // 11)
    dark = Image.new("RGBA", (w, h), ext + (255,))
    for i in range(depth, 0, -1):
        im.paste(dark, (i, i), mask)
    face = vgrad(w, h, top, bot).convert("RGBA")
    im.paste(face, (0, 0), mask)
    hl = ImageChops.subtract(mask, ImageChops.offset(mask, size // 14, size // 14))
    hl = hl.filter(ImageFilter.GaussianBlur(size / 60))
    white = Image.new("RGBA", (w, h), (255, 255, 255, 235))
    im.paste(white, (0, 0), ImageChops.multiply(hl, mask))
    gloss = Image.new("L", (w, h), 0)
    ImageDraw.Draw(gloss).ellipse((pad, pad - size * .2, w - pad, pad + size * .45), fill=70)
    im.paste(white, (0, 0), ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(size / 30)), mask))
    return bake_shadow(im, (size // 8, size // 5), size // 8, 110)


@lru_cache(maxsize=None)
def pill(text, size=64, fill=OR, fg=(255, 255, 255), padx=58, pady=30):
    f = font(XBOLD, size)
    l, t_, r, b = f.getbbox(text)
    w, h = r - l + 2 * padx, b - t_ + 2 * pady
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=255)
    lighter = tuple(min(255, int(c * 1.25 + 25)) for c in fill)
    darker = tuple(int(c * .78) for c in fill)
    im.paste(vgrad(w, h, lighter, fill).convert("RGBA"), (0, 0), mask)
    rim = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(9)))
    im.paste(Image.new("RGBA", (w, h), darker + (255,)), (0, 0), rim)
    hl = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hl).rounded_rectangle((h * .25, h * .08, w - h * .25, h * .46), radius=h // 4, fill=90)
    im.paste(Image.new("RGBA", (w, h), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(3)), mask))
    d = ImageDraw.Draw(im)
    d.text((padx - l + 2, pady - t_ + 3), text, font=f, fill=darker + (140,))
    d.text((padx - l, pady - t_), text, font=f, fill=fg)
    return bake_shadow(im, (6, 14), 14, 90)


@lru_cache(maxsize=None)
def cursor(size=210):
    s = size
    pts = [(.08, .02), (.08, .86), (.30, .66), (.46, 1.0), (.62, .92), (.46, .60), (.78, .58)]
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon([(x * s, y * s) for x, y in pts], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    for i in range(s // 14, 0, -1):
        im.paste(Image.new("RGBA", (s, s), OR_D + (255,)), (i, i), mask)
    im.paste(vgrad(s, s, OR_L, OR).convert("RGBA"), (0, 0), mask)
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, s // 30, s // 30)).filter(ImageFilter.GaussianBlur(1))
    im.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(rim, mask))
    return bake_shadow(im, (10, 18), 12, 100)


@lru_cache(maxsize=None)
def paper(w=360, h=470, accent=OR, lines=5, seed=0):
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=(255, 252, 247), outline=(240, 222, 205), width=3)
    d.rounded_rectangle((26, 26, w - 26, 150), radius=16, fill=accent)
    d.ellipse((w / 2 - 34, 56, w / 2 + 34, 124), fill=(255, 255, 255, 230))
    for i in range(lines):
        y = 190 + i * 48
        d.rounded_rectangle((28, y, 28 + int((w - 56) * rng.uniform(.5, 1)), y + 14), radius=7, fill=(225, 205, 190))
    return bake_shadow(im, (14, 24), 18, 80)


@lru_cache(maxsize=None)
def sticky(text, color=AMB, size=50, w=420, h=230, fg=INK):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, h - 1), fill=color)
    d.polygon([(w - 60, h - 1), (w - 1, h - 60), (w - 1, h - 1)], fill=tuple(int(c * .8) for c in color))
    d.rectangle((0, 0, w - 1, 22), fill=tuple(min(255, int(c * 1.1)) for c in color))
    d.text((w / 2, h / 2 + 8), text, font=font(XBOLD, size), fill=fg, anchor="mm")
    return bake_shadow(im, (10, 18), 14, 90)


@lru_cache(maxsize=None)
def card(w, h, accent=None, radius=40):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=(255, 253, 249), outline=(244, 226, 210), width=3)
    if accent:
        d.rounded_rectangle((0, 0, 16, h - 1), radius=8, fill=accent)
    return bake_shadow(im, (16, 28), 22, 80)


@lru_cache(maxsize=None)
def label(text, path, size, color):
    f = font(path, size)
    l, t_, r, b = f.getbbox(text)
    im = Image.new("RGBA", (r - l + 16, b - t_ + 16), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((8 - l, 8 - t_), text, font=f, fill=color)
    return im


def ptxt(fr, t, t0, text, path, size, color, cx, cy, d=0.4, rot=0.0, shadow=True):
    if t < t0:
        return
    sc, a = R.pop(t, t0, d)
    sp = label(text, path, size, color)
    if shadow:
        sp = bake_shadow(sp, (4, 8), 8, 50)
    # settle from a slight blur like the reference's soft text reveals
    put2(fr, sp, cx, cy, sc, a, rot, blur=max(0, (1 - clamp((t - t0) / d)) * 10))


@lru_cache(maxsize=None)
def marker():
    w, h = 300, 64
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((70, 4, w - 4, h - 4), radius=26, fill=AMB)
    d.rounded_rectangle((70, 4, w - 4, 26), radius=12, fill=(255, 205, 80))
    d.polygon([(70, 12), (8, 26), (8, 38), (70, h - 12)], fill=(60, 36, 24))
    d.rectangle((60, 4, 74, h - 4), fill=(250, 235, 210))
    return bake_shadow(im, (8, 14), 10, 80)


# ------------------------------------------------------------ background / fx layers
@lru_cache(maxsize=None)
def background():
    bw, bh = W + 240, H + 320
    yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    d = np.sqrt(((xx - bw * .42) / bw) ** 2 + ((yy - bh * .33) / bh) ** 2) / .75
    d = np.clip(d, 0, 1)[:, :, None] ** 1.3
    L, D = np.array(CREAM, np.float32), np.array(PEACH, np.float32)
    arr = L * (1 - d * .55) + D * d * .55
    bg = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    # long diagonal shadow band (as in the opening desk frames)
    sh = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(-100, 500), (900, 200), (bw + 100, 900), (bw + 100, 1500), (300, 1300)],
                               fill=(200, 110, 70, 38))
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(70)))
    # halftone corners
    ht = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    hd = ImageDraw.Draw(ht)
    for cx, cy in [(0, bh), (bw, 0)]:
        for gy in range(0, bh, 22):
            for gx in range(0, bw, 22):
                dist = math.hypot(gx - cx, gy - cy)
                r = 7.5 * (1 - dist / 620)
                if r > 0.8:
                    hd.ellipse((gx - r, gy - r, gx + r, gy + r), fill=OR + (70,))
    bg.alpha_composite(ht)
    return bg


@lru_cache(maxsize=None)
def halftone_full():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for gy in range(0, H, 26):
        for gx in range(0, W, 26):
            r = 10 * (0.25 + 0.75 * (gy / H)) * (0.6 + 0.4 * math.sin(gx / 140))
            d.ellipse((gx - r, gy - r, gx + r, gy + r), fill=OR_L + (150,))
    return im


@lru_cache(maxsize=None)
def vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H * .45) / (H / 2)) ** 2)
    return (np.clip(d - .55, 0, 1) ** 1.6 * 70).astype(np.float32)[:, :, None]


@lru_cache(maxsize=None)
def grain(k):
    rng = np.random.default_rng(100 + k)
    return rng.normal(0, 3.2, (H, W, 1)).astype(np.float32)


def post(fr, t):
    """Bloom + vignette + film grain on the finished frame."""
    rgb = fr.convert("RGB")
    arr = np.asarray(rgb, np.float32)
    small = rgb.resize((W // 8, H // 8), Image.BILINEAR)
    bright = small.point(lambda v: max(0, v - 238) * 6)
    bloom = np.asarray(bright.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR), np.float32)
    arr = arr + bloom * 0.22
    arr = arr - vignette() * np.array([.3, .5, .7], np.float32)
    arr = arr + grain(int(t * FPS) % 3)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


FLOATERS = [  # x, y, rotation, depth(blur), kind, drift
    (150, 470, -18, 1, "paper", 1.0), (930, 440, 14, 2, "paper", 1.3), (90, 1180, 22, 3, "sticky", .8),
    (980, 1150, -12, 1.5, "paper", 1.1), (880, 330, 30, 3.5, "sticky", .9), (230, 1330, -8, 2, "paper", 1.2),
]


def floaters(fr, t, alpha=1.0, t0=0.0, scale=.55):
    for i, (x, y, rot, depth, kind, dr) in enumerate(FLOATERS):
        e = clamp((t - t0 - i * .05) / .6)
        (px, py), vel = fly(t, t0 + i * .05, .6, (x + (900 if x > W / 2 else -900), y - 300), (x, y), ease_out)
        px += math.sin(t * dr + i) * 18
        py += math.cos(t * dr * .8 + i * 2) * 22
        sp = paper(seed=i) if kind == "paper" else sticky(["Tips", "Idea", "Brief"][i % 3], [AMB, OR_L][i % 2], 46, 300, 170)
        put2(fr, sp, px, py, scale * (1 - .04 * depth), alpha * e, rot + math.sin(t * dr + i) * 5,
             vel=(vel[0] * 1.2, vel[1] * 1.2), blur=depth * 4.5)


def ripple(fr, t, t0, cx, cy, color=OR):
    p = (t - t0) / .55
    if 0 <= p <= 1:
        d = ImageDraw.Draw(fr, "RGBA")
        r = 30 + 150 * ease_out(p)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color + (int(210 * (1 - p)),), width=int(10 * (1 - p)) + 2)


def confetti(fr, t, t0, cx, cy, n=70, seed=3, dur=2.6):
    if t < t0 or t > t0 + dur:
        return
    rng = np.random.default_rng(seed)
    d = ImageDraw.Draw(fr, "RGBA")
    tau = t - t0
    cols = [OR, AMB, PURPLE, OR_L, (255, 255, 255)]
    for i in range(n):
        ang = rng.uniform(-math.pi, 0) if i % 3 else rng.uniform(-math.pi, math.pi)
        sp_ = rng.uniform(450, 1300)
        x = cx + math.cos(ang) * sp_ * (1 - math.exp(-tau * 3)) / 3
        y = cy + math.sin(ang) * sp_ * (1 - math.exp(-tau * 3)) / 3 + 520 * tau * tau
        s = rng.uniform(12, 28)
        a = rng.uniform(0, 6.28) + tau * rng.uniform(-9, 9)
        col = cols[i % len(cols)]
        al = int(255 * clamp(1 - (tau - dur * .6) / (dur * .4)))
        kind = i % 3
        if kind == 0:
            pts = [(x + s * math.cos(a + k * 2.094), y + s * math.sin(a + k * 2.094)) for k in range(3)]
        elif kind == 1:
            sq = abs(math.cos(tau * 8 + i))
            pts = [(x + s * math.cos(a) * sq, y + s * math.sin(a)), (x + s * .6 * math.cos(a + 1.57), y + s * .6 * math.sin(a + 1.57)),
                   (x - s * math.cos(a) * sq, y - s * math.sin(a)), (x - s * .6 * math.cos(a + 1.57), y - s * .6 * math.sin(a + 1.57))]
        else:
            pts = [(x + s * .8 * math.cos(a + k * 1.571 + .785), y + s * .8 * math.sin(a + k * 1.571 + .785)) for k in range(4)]
        d.polygon(pts, fill=col + (al,))


def ribbon(fr, t, t0, dur=.9, width=34):
    """Orange ribbon swoosh across the frame, drawn progressively."""
    p = clamp((t - t0) / dur)
    if p <= 0:
        return
    P = [(-80, 1290), (330, 640), (620, 1250), (1180, 520)]
    d = ImageDraw.Draw(fr, "RGBA")
    steps = int(80 * p)
    for i in range(steps):
        s = i / 80
        x = (1 - s) ** 3 * P[0][0] + 3 * (1 - s) ** 2 * s * P[1][0] + 3 * (1 - s) * s * s * P[2][0] + s ** 3 * P[3][0]
        y = (1 - s) ** 3 * P[0][1] + 3 * (1 - s) ** 2 * s * P[1][1] + 3 * (1 - s) * s * s * P[2][1] + s ** 3 * P[3][1]
        w = width * (.35 + .65 * math.sin(math.pi * s))
        d.ellipse((x - w, y - w * .5, x + w, y + w * .5), fill=OR + (235,))
        d.ellipse((x - w * .5, y - w * .35, x + w * .3, y), fill=OR_L + (180,))


def starburst(fr, t, alpha, rot_speed=22, color=(255, 255, 255), cx=W / 2, cy=H / 2, n=22):
    d = ImageDraw.Draw(fr, "RGBA")
    R_ = 2600
    for i in range(n):
        a0 = math.radians(rot_speed * t) + i * 2 * math.pi / n
        a1 = a0 + math.pi / n * .9
        d.polygon([(cx, cy), (cx + R_ * math.cos(a0), cy + R_ * math.sin(a0)), (cx + R_ * math.cos(a1), cy + R_ * math.sin(a1))],
                  fill=color + (int(255 * alpha),))


# ------------------------------------------------------------ scenes
def scene_hook(fr, t):
    floaters(fr, t, alpha=.9 if t < 2.2 else .55, scale=.5)
    out = ease_in_out((t - 2.05) / .4)
    if out < 1:
        # big "Learn Prompt"-style card whips in from the right, pokes, then whips out
        (cx, cy), vel = fly(t, 0.0, .6, (1700, 820), (W / 2, 800), ease_out)
        cx -= out * 1500
        click = clamp((t - 1.75) / .12) - clamp((t - 1.87) / .2)
        sc = 1 - .05 * click
        host = Image.new("RGBA", (880, 540), (0, 0, 0, 0))
        host.alpha_composite(card(880, 540, OR))
        sp = card(880, 540, OR).copy()
        d = ImageDraw.Draw(sp)
        P = 94
        for txt, path, size, col, y, t0 in [("Nak guna AI", BLACK, 104, INK, 190, 0.24), ("dengan lebih", BLACK, 104, INK, 320, wt(0, "dengan")),
                                            ("berkesan?", BLACK, 130, OR, 460, wt(0, "berkesan"))]:
            if t >= t0:
                k = ease_out_back((t - t0) / .35)
                f = font(path, max(8, int(size * max(.01, min(1.15, k)))))
                d.text((sp.width / 2, y + P), txt, font=f, fill=col, anchor="mm")
        put2(fr, sp, cx, cy, sc, 1, -5 + out * -10, vel=(vel[0] - out * 40, vel[1]))
        # cursor flies in and clicks
        (kx, ky), kv = fly(t, .9, .9, (1000, 1500), (760, 1010), ease_out)
        kx -= out * 1500
        put2(fr, cursor(), kx, ky, 1 - .08 * click, ease_out((t - .9) / .2), 0, vel=kv)
        ripple(fr, t, 1.78, 760, 1000)
    if t >= 2.2:
        t3 = wt(1, "3")
        if t >= t3:
            a = ease_out((t - t3) / .3) * .5
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            starburst(ov, t, 1, 18, OR_L, W / 2, 860, 16)
            m = Image.new("L", (W, H), 0)
            ImageDraw.Draw(m).ellipse((W / 2 - 520, 340, W / 2 + 520, 1380), fill=255)
            m = m.filter(ImageFilter.GaussianBlur(150))
            ov.putalpha(ImageChops.multiply(ov.getchannel("A"), m).point(lambda v: int(v * a * .55)))
            fr.alpha_composite(ov)
        ptxt(fr, t, 2.2, "INI", BLACK, 78, OR_D, W / 2, 500, shadow=False)
        if t >= t3:
            sc, al = R.pop(t, t3, .55)
            put2(fr, balloon("3", 640), W / 2, 850 + math.sin(t * 3) * 10, sc, al, math.sin(t * 2) * 3 - (1 - clamp((t - t3) / .5)) * 40)
        ptxt(fr, t, wt(1, "penggunaan"), "CARA GUNA CLAUDE", BLACK, 90, INK, W / 2, 1180)
        tb = wt(1, "betul")
        if t >= tb:
            sc, al = R.pop(t, tb, .45)
            put2(fr, pill("YANG BETUL!", 64), W / 2, 1310, sc, al, -3)
            (kx, ky), kv = fly(t, tb + .1, .5, (1000, 1560), (W / 2 + 190, 1345), ease_out)
            put2(fr, cursor(150), kx, ky, 1, ease_out((t - tb - .1) / .2), 0, vel=kv)
            ripple(fr, t, tb + .6, W / 2 + 190, 1330)


def badge3d(fr, t, num, t0, cy=430):
    if t < t0:
        return
    sc, al = R.pop(t, t0, .5)
    put2(fr, balloon(num, 150), W / 2, cy, sc, al, (1 - clamp((t - t0) / .5)) * -60)


def scene_one(fr, t):
    floaters(fr, t, alpha=.45, t0=4.85, scale=.42)
    badge3d(fr, t, "01", 5.2)
    # "Learn"-style pill button with cursor click, carrying the keyword
    tj = wt(3, "arahan")
    if t >= tj:
        sc, al = R.pop(t, tj, .45)
        click = clamp((t - (tj + .75)) / .1) - clamp((t - (tj + .87)) / .2)
        put2(fr, pill("ARAHAN JELAS", 96, OR, padx=80, pady=44), W / 2, 680, sc * (1 - .06 * click), al, -2)
        (kx, ky), kv = fly(t, tj + .15, .7, (1100, 1000), (W / 2 + 400, 770), ease_out)
        put2(fr, cursor(190), kx, ky, 1 - .08 * click, ease_out((t - tj - .15) / .2), 0, vel=kv)
        ripple(fr, t, tj + .78, W / 2 + 400, 745)
    # marker highlighter sweeps "& SPESIFIK"
    ts = wt(3, "spesifik")
    if t >= ts - .1:
        txt = label("& SPESIFIK", BLACK, 112, INK)
        cx, cy = W / 2, 905
        p = ease_out((t - ts + .1) / .55)
        bar_w = int((txt.width + 40) * p)
        bar = Image.new("RGBA", (max(bar_w, 1), 100), AMB + (200,))
        fr.paste(bar, (int(cx - txt.width / 2 - 20), int(cy - 28)), bar)
        put2(fr, bake_shadow(txt, (3, 6), 6, 40), cx, cy, 1, ease_out((t - ts + .1) / .25))
        if p < 1:
            put2(fr, marker(), cx - txt.width / 2 - 20 + bar_w + 60, cy + 40, 1, 1, 24)
    # good / bad prompt cards fly in with motion blur
    for good, y, t0 in [(False, 1080, wt(3, "supaya")), (True, 1240, wt(3, "faham"))]:
        if t >= t0:
            (cx, cy), vel = fly(t, t0, .45, (W / 2 + 900, y), (W / 2, y), ease_out)
            sp = card(900, 128, GREEN2 if good else RED2).copy()
            d = ImageDraw.Draw(sp)
            d.ellipse((46 + 94, 30 + 94, 46 + 94 + 68, 30 + 94 + 68), fill=GREEN2 if good else RED2)
            d.text((80 + 94, 64 + 94), "✓" if good else "×", font=font(BLACK, 52), fill=(255, 255, 255), anchor="mm")
            d.text((140 + 94, 34 + 94), "SPESIFIK" if good else "KABUR", font=font(BOLD, 24), fill=GREEN2 if good else RED2, anchor="lm")
            d.text((140 + 94, 74 + 94), "“Poster A4 promosi kopi, tona hangat”" if good else "“Buat poster”", font=font(SEMI, 36), fill=INK, anchor="lm")
            put2(fr, sp, cx, cy, 1, ease_out((t - t0) / .2), 0, vel=vel)


def scene_two(fr, t):
    floaters(fr, t, alpha=.4, t0=10.25, scale=.4)
    badge3d(fr, t, "02", 10.5)
    tk = wt(5, "konteks")
    if t >= tk:
        # letters pop one by one like inflating balloons, then bob
        word = "KONTEKS"
        total = 0
        sprites = [balloon(ch, 150) for ch in word]
        widths = [font(BLACK, 150).getlength(ch) + 4 for ch in word]
        x = W / 2 - sum(widths) / 2
        for i, (ch, sp, wd) in enumerate(zip(word, sprites, widths)):
            t0 = tk + i * .06
            sc, al = R.pop(t, t0, .45)
            put2(fr, sp, x + wd / 2, 640 + math.sin(t * 3 + i * .7) * 9, sc, al, math.sin(t * 2.2 + i) * 4)
            x += wd
    ptxt(fr, t, wt(5, "mencukupi"), "YANG MENCUKUPI", BLACK, 70, INK, W / 2, 800)
    ribbon(fr, t, 11.3, 1.0)
    notes = [("Tujuan", AMB, wt(6, "tujuan"), (250, 1000), -8), ("Sasaran audiens", OR_L, wt(6, "sasaran"), (800, 1090), 6),
             ("Format jawapan", (255, 214, 120), wt(6, "format"), (450, 1260), -4)]
    for txt, col, t0, (tx, ty), rot in notes:
        if t >= t0:
            (cx, cy), vel = fly(t, t0, .5, (tx + 900, ty - 500), (tx, ty), ease_out)
            sc = 1 + .08 * math.sin(clamp((t - t0 - .45) / .25) * math.pi)
            put2(fr, sticky(txt, col, 46, 470, 210), cx, cy, sc, ease_out((t - t0) / .15), rot + (1 - clamp((t - t0) / .5)) * 25, vel=vel)


def doc_sprite(scan):
    sp = card(780, 400, OR).copy()
    d = ImageDraw.Draw(sp)
    d.text((70 + 94, 66 + 94), "JAWAPAN AI", font=font(BOLD, 30), fill=(150, 110, 90), anchor="lm")
    for i, frac in enumerate([.95, .8, .9, .6]):
        y = 120 + 94 + i * 62
        done = scan * 4 >= i + 1
        d.rounded_rectangle((70 + 94, y, 70 + 94 + int(520 * frac), y + 24), radius=12, fill=GREEN2 if done else (232, 214, 200))
        if done:
            d.line((640 + 94, y + 12, 656 + 94, y + 28, 686 + 94, y - 2), fill=GREEN2, width=9, joint="curve")
    return sp


def scene_three(fr, t):
    floaters(fr, t, alpha=.4, t0=17.5, scale=.4)
    badge3d(fr, t, "03", 17.84)
    ptxt(fr, t, wt(8, "semak"), "SEMAK FAKTA", BLACK, 118, INK, W / 2, 640)
    t_doc, t_warn = wt(8, "semak"), 21.46
    if t_doc <= t < t_warn + .3:
        (cx, cy), vel = fly(t, t_doc, .5, (W / 2 - 800, 1030), (W / 2, 1030), ease_out)
        scan = clamp((t - (t_doc + .3)) / 2.2)
        fade = 1 - ease_out((t - t_warn) / .25) if t >= t_warn else 1
        put2(fr, doc_sprite(scan), cx, cy, 1, fade, -2, vel=vel)
        if fade > 0:
            line = min(int(scan * 4), 3)
            within = scan * 4 - line
            put2(fr, lens(), W / 2 - 310 + 560 * within, 1030 - 200 + 120 + (line + 1) * 62, 1, fade, 0)
    if t >= t_warn:
        # flat orange fill + halftone, giant kinetic type sliding in with motion blur (the "Real" beat)
        e = ease_out((t - t_warn) / .35)
        ov = Image.new("RGBA", (W, H), OR + (0,))
        ov.putalpha(Image.new("L", (W, H), int(255 * min(1, e * 1.4))))
        fr.alpha_composite(ov)
        fr.alpha_composite(halftone_full())
        for txt, size, y, t0, side in [("JANGAN", 210, 760, t_warn + .05, 1), ("TERUS", 210, 960, t_warn + .15, -1), ("PERCAYA", 190, 1150, t_warn + .25, 1)]:
            if t >= t0:
                (cx, cy), vel = fly(t, t0, .4, (W / 2 + side * 1100, y), (W / 2, y), ease_out)
                sp = bake_shadow(label(txt, BLACK, size, (255, 255, 255)), (6, 12), 10, 90, OR_D)
                put2(fr, sp, cx, cy, 1, 1, 0, vel=(vel[0] * 1.3, 0))
        ptxt(fr, t, t_warn + .55, "tanpa pengesahan", XBOLD, 56, INK, W / 2, 1290, shadow=False)


@lru_cache(maxsize=None)
def lens(s=150):
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line((s * .58, s * .58, s * .92, s * .92), fill=OR_D, width=int(s * .16))
    d.ellipse((s * .08, s * .08, s * .64, s * .64), outline=OR, width=int(s * .1), fill=(255, 255, 255, 90))
    d.arc((s * .16, s * .16, s * .56, s * .56), 200, 260, fill=(255, 255, 255), width=int(s * .05))
    return bake_shadow(im, (6, 10), 8, 90)


def scene_recap(fr, t):
    floaters(fr, t, alpha=.5, t0=23.5, scale=.5)
    ptxt(fr, t, 23.76, "INGAT!", BLACK, 160, OR, W / 2, 470, d=.5)
    for txt, y, t0, col in [("Arahan jelas", 700, 24.36, AMB), ("Konteks tepat", 850, 25.48, OR_L), ("Semakan fakta", 1000, 26.66, (255, 214, 120))]:
        if t >= t0:
            (cx, cy), vel = fly(t, t0, .4, (W / 2 - 900, y), (W / 2, y), ease_out)
            sp = sticky(txt, col, 62, 720, 128)
            sp = sp.copy()
            if t >= t0 + .45:
                ImageDraw.Draw(sp).ellipse((sp.width - 190, sp.height / 2 - 48, sp.width - 94, sp.height / 2 + 48), fill=GREEN2)
                ImageDraw.Draw(sp).line((sp.width - 168, sp.height / 2, sp.width - 148, sp.height / 2 + 22, sp.width - 114, sp.height / 2 - 20),
                                        fill=(255, 255, 255), width=12, joint="curve")
            put2(fr, sp, cx, cy, 1, ease_out((t - t0) / .15), (-2 if y % 300 else 2), vel=vel)
    ptxt(fr, t, 27.86, "GUNA CLAUDE DENGAN", BLACK, 66, INK, W / 2, 1160)
    tb = wt(14, "lebih")
    if t >= tb:
        sc, al = R.pop(t, tb, .5)
        put2(fr, balloon("LEBIH BIJAK!", 118), W / 2, 1290, sc, al, -2)
        # underline stroke draws on (like "with Claude" in the reference)
        p = ease_out((t - tb - .35) / .5)
        if p > 0:
            d = ImageDraw.Draw(fr, "RGBA")
            x0, x1 = W / 2 - 440, W / 2 - 440 + 880 * p
            d.line((x0, 1400, x1, 1396), fill=OR + (255,), width=14)
        confetti(fr, t, tb, W / 2, 1290)


SCENES = [(0, scene_hook), (CUTS[0], scene_one), (CUTS[1], scene_two), (CUTS[2], scene_three), (CUTS[3], scene_recap)]
WIN = .3  # half-width of each transition


def transition(fr, t):
    for k, c in enumerate(CUTS):
        p = (t - (c - WIN)) / (2 * WIN)
        if not 0 <= p <= 1:
            continue
        env = min(1.0, math.sin(math.pi * p) ** .55)
        if k == 0:  # amber flash with radial glow
            layer = Image.new("RGBA", (W, H), AMB + (int(255 * env),))
            fr.alpha_composite(layer)
        elif k == 1:  # starburst on orange
            layer = Image.new("RGBA", (W, H), OR + (int(255 * env),))
            starburst(layer, t, env * .9, 40, (255, 240, 225), W / 2, H * .45)
            fr.alpha_composite(layer)
        elif k == 2:  # flat orange with radial grow
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            r = 2200 * ease_in_out(min(1, env * 1.15))
            ImageDraw.Draw(layer).ellipse((W / 2 - r, H * .45 - r, W / 2 + r, H * .45 + r), fill=OR + (255,))
            fr.alpha_composite(layer)
        else:  # whip pan: horizontal motion blur + cream flash
            shift = math.sin(math.pi * p) * 260
            arr = np.asarray(fr.convert("RGB"), np.float32)
            acc = np.zeros_like(arr)
            for i in range(9):
                acc += np.roll(arr, int(shift * (i / 8 - .5)), 1)
            out = Image.fromarray((acc / 9).astype(np.uint8)).convert("RGBA")
            out.alpha_composite(Image.new("RGBA", (W, H), CREAM + (int(210 * env ** 2),)))
            fr.paste(out)
    return fr


def draw_chrome(fr, t, total):
    d = ImageDraw.Draw(fr)
    d.rectangle((0, 0, int(W * t / total), 12), fill=OR)
    if CUTS[0] <= t < CUTS[3]:
        step = sum(t >= c for c in CUTS[:3]) - 1
        for i in range(3):
            x = W / 2 + (i - 1) * 120
            on, done = i == step, i < step
            col = OR if on else (GREEN2 if done else (222, 196, 176))
            w = 90 if on else 60
            d.rounded_rectangle((x - w / 2, 250, x + w / 2, 264), radius=7, fill=col)
        d.text((W / 2, 200), "3 TIPS GUNA CLAUDE", font=font(BOLD, 34), fill=(170, 105, 75), anchor="mm")


def draw_caption(fr, t):
    gi = None
    for i, g in enumerate(CAPTION_GROUPS):
        start = SEGS[g[0]][0] - .1
        end = SEGS[CAPTION_GROUPS[i + 1][0]][0] - .12 if i + 1 < len(CAPTION_GROUPS) else 99
        end = min([end] + [c for c in CUTS if start < c < end])
        if start <= t < end:
            gi = i
    if gi is None:
        return
    f = font(XBOLD, 60)
    space = f.getlength(" ")
    lines = R.LAYOUTS[gi]
    lh = 88
    y0 = 1560 - (len(lines) - 1) * lh / 2
    appear = ease_out((t - (SEGS[CAPTION_GROUPS[gi][0]][0] - .1)) / .2)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for li, (ws, lw) in enumerate(lines):
        x = W / 2 - lw / 2
        y = y0 + li * lh + (1 - appear) * 30
        for w, ww in ws:
            spoken = t >= w["s"]
            if norm(w["t"]) in R.HIGHLIGHT and spoken:
                k = ease_out_back((t - w["s"]) / .25)
                pad = 12 * k
                d.rounded_rectangle((x - pad, y - 42 - pad * .4, x + ww + pad, y + 38 + pad * .4), radius=18, fill=OR)
                d.text((x, y), w["t"], font=f, fill=(255, 255, 255), anchor="lm")
            else:
                d.text((x, y), w["t"], font=f, fill=INK + ((255,) if spoken else (90,)), anchor="lm",
                       stroke_width=5, stroke_fill=(255, 250, 244, 230 if spoken else 90))
            x += ww + space
    if appear < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * appear)))
    fr.alpha_composite(layer)


def render_frame(t, total=30.6):
    bg = background()
    ox, oy = 120 + 90 * math.sin(t * .35), 160 + 120 * math.sin(t * .22 + 1)
    fr = bg.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
    [fn for start, fn in SCENES if t >= start][-1](fr, t)
    transition(fr, t)
    draw_chrome(fr, t, total)
    draw_caption(fr, t)
    return post(fr, t)


_TOTAL = [30.6]


def _job(i):
    return render_frame(i / FPS, _TOTAL[0]).tobytes()


def main():
    if "--preview" in sys.argv:
        for arg in sys.argv[sys.argv.index("--preview") + 1:]:
            render_frame(float(arg)).save(f"output/preview_v2_{arg}.png")
        return
    mixed = "output/_mix.wav"
    total = build_audio(mixed)
    _TOTAL[0] = total
    frames = int(math.ceil(total * FPS))
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", mixed, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)
    with Pool(4) as pool:
        for i, raw in enumerate(pool.imap(_job, range(frames), chunksize=3)):
            ff.stdin.write(raw)
            if i % 90 == 0:
                print(f"frame {i}/{frames}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
