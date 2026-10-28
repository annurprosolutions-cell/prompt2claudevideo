"""Edit a talking-head clip into a 9:16 TikTok video: alternating motion-graphic scenes,
word-by-word subtitles, and a face punch-in on every emphasised word.

Usage:
  python3 render_talking.py SRC.mp4 [--out output/vibe-coding-3-tip.mp4] [--preview 3.0 8.5 ...]

Needs: Python 3, Pillow, numpy, opencv-python-headless (4.x, for the Haar face cascade), ffmpeg.
The spoken text lives in SCRIPT below: edit it (wording, *emphasis* markers) and re-render.
Phrase times are measured from pauses in the audio; words inside a phrase are spread over the
voiced part of that phrase.
"""
import argparse
import math
import re
import subprocess
import sys
import wave
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FONT_DIR = "/usr/share/fonts/opentype/inter/"
BLACK = FONT_DIR + "InterDisplay-Black.otf"
XBOLD = FONT_DIR + "Inter-ExtraBold.otf"
BOLD = FONT_DIR + "Inter-Bold.otf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

WHITE = (255, 255, 255)
YELLOW = (255, 196, 46)
RED = (255, 82, 82)
GREEN = (66, 214, 140)
GREY = (132, 146, 174)
CARD = (28, 40, 68)
CARD2 = (40, 58, 96)
DARK = (10, 16, 30)

# (start, end, text) per phrase, in source seconds. *word* = important word (face zoom + pop).
SCRIPT = [
    (0.00, 6.90, "Okey, *3* benda ni jangan korang buat sewaktu *vibe coding* lah. "
                 "Yang *pertama*, janganlah korang terus suruh AI bina"),
    (6.90, 10.90, "sistem tanpa *perancangan*. Masa ni korang kena ada *flow* dia"),
    (10.90, 13.10, "macam mana *instruction* dan sebagainya"),
    (13.10, 19.46, "baru korang suruh AI teruskan. Jadi korang boleh *bincang* dahulu dengan AI tu dulu, okey"),
    (19.46, 21.00, "Yang *kedua*, jangan minta"),
    (21.00, 22.90, "banyak benda dalam *satu prompt* lah"),
    (22.90, 23.80, "Maksudnya,"),
    (23.80, 27.97, "macam-macam *feature* kita minta ada, tapi dalam satu mesej prompt lah"),
    (27.97, 32.46, "Jadi kita kena buat *berperingkat*. Mula-mula kita nak settlekan bahagian *front end* dulu"),
    (32.46, 36.58, "Pada bahagian *user experience* dulu dan sebagainya"),
    (36.58, 39.58, "Baru seterusnya, dan seterusnya lah"),
    (39.58, 46.40, "Jadi berperingkat, jangan semua letak dalam satu prompt. "
                   "Okey, yang *ketiga* adalah jangan terus *percaya* pada kod yang AI bagi"),
    (46.40, 49.92, "Maksudnya korang kena *cross-check* dulu, betul ke apa yang dia bagi"),
    (49.92, 50.95, "dan juga boleh"),
    (50.95, 52.86, "*brainstorm* dulu dengan AI"),
    (52.86, 54.36, "Jadi itulah *3 tip*"),
    (54.36, 57.88, "jangan buat sewaktu *vibe coding*"),
    (57.88, 59.50, "*Selamat mencuba*"),
]

# Scene plan: ("F", start, end) = talking head, ("M", name, start, end) = motion graphic.
SCENES = [
    ("F", 0.0, 5.6), ("M", "flow", 5.6, 11.0), ("F", 11.0, 13.1),
    ("M", "chat", 13.1, 16.3), ("F", 16.3, 21.0), ("M", "prompt", 21.0, 28.0), ("F", 28.0, 32.5),
    ("M", "steps", 32.5, 39.6), ("F", 39.6, 46.4), ("M", "check", 46.4, 49.9), ("F", 49.9, 54.4),
    ("M", "recap", 54.4, 57.9), ("F", 57.9, 99.0),
]
TRANS = 0.18


def norm(s):
    return re.sub(r"[^\w]", "", s.lower())


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def e_out(x):
    return 1 - (1 - clamp(x)) ** 3


def e_back(x):
    x = clamp(x)
    c1, c3 = 1.9, 2.9
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def e_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ audio / word timing
def load_mono(path):
    w = wave.open(path)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x, w.getframerate()


def voiced_mask(x, sr, thr_db=-38.0):
    hop = sr // 100
    n = len(x) // hop
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    m = 20 * np.log10(rms) > thr_db
    # close pauses shorter than 120 ms so consonants don't split a word
    idx = np.nonzero(m)[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= 12:
            m[a:b] = True
    return m


def build_words(mask):
    words = []
    for a, b, text in SCRIPT:
        toks = []
        for m in re.finditer(r"\*(.+?)\*|(\S+)", text):
            if m.group(1):
                toks += [(t, True) for t in m.group(1).split()]
            else:
                toks.append((m.group(2), False))
        v = np.nonzero(mask[int(a * 100): int(b * 100)])[0] + int(a * 100)
        times = v / 100.0 if len(v) > 5 else np.linspace(a, b, 50)
        wts = [len(norm(t)) + 1.5 for t, _ in toks]
        tot, acc = sum(wts), 0.0
        for (t, em), wgt in zip(toks, wts):
            f0, f1 = acc / tot, (acc + wgt) / tot
            acc += wgt
            n = len(times)
            s = times[min(n - 1, int(f0 * n))]
            e = times[min(n - 1, max(int(f1 * n) - 1, 0))] + 0.01
            words.append({"t": t, "s": float(s), "e": float(max(e, s + 0.08)), "em": em})
    return words


def build_groups(words):
    groups, cur = [], []
    for w in words:
        cur.append(w)
        chars = sum(len(x["t"]) for x in cur) + len(cur)
        if re.search(r"[,.!?]$", w["t"]) or len(cur) >= 4 or (len(cur) >= 3 and chars > 17) or chars > 24:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for i, g in enumerate(groups):
        s = g[0]["s"]
        nxt = groups[i + 1][0]["s"] if i + 1 < len(groups) else 1e9
        e = nxt if nxt - g[-1]["e"] < 0.45 else g[-1]["e"] + 0.25
        out.append({"w": g, "s": s, "e": e})
    return out


def emphasis_spans(words):
    spans = []
    for w in words:
        if not w["em"]:
            continue
        s, e = w["s"] - 0.04, max(w["e"], w["s"] + 0.45)
        if spans and s <= spans[-1][1] + 0.05:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    return spans


def env(spans, t):
    v = 0.0
    for s, e in spans:
        if s <= t < e:
            v = max(v, e_out((t - s) / 0.09))
        elif e <= t < e + 0.28:
            v = max(v, 1 - e_io((t - e) / 0.28))
    return v


# ------------------------------------------------------------------ canvas
@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, max(4, int(size)))


class Canvas:
    def __init__(self, ss=2):
        self.ss = ss
        self.im = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def _b(self, box):
        s = self.ss
        return [v * s for v in box]

    def rrect(self, box, r, fill=None, outline=None, width=0):
        self.d.rounded_rectangle(self._b(box), radius=r * self.ss, fill=fill, outline=outline,
                                 width=int(width * self.ss))

    def circle(self, cx, cy, r, fill=None, outline=None, width=0):
        self.d.ellipse(self._b([cx - r, cy - r, cx + r, cy + r]), fill=fill, outline=outline,
                       width=int(width * self.ss))

    def line(self, pts, fill, width):
        s = self.ss
        flat = [(x * s, y * s) for x, y in pts]
        self.d.line(flat, fill=fill, width=int(width * s), joint="curve")
        for p in (flat[0], flat[-1]):
            r = width * s / 2
            self.d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)

    def _blit(self, tmp, x, y):
        x, y = int(x), int(y)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.im.width, x + tmp.width), min(self.im.height, y + tmp.height)
        if x1 <= x0 or y1 <= y0:
            return
        part = tmp.crop((x0 - x, y0 - y, x1 - x, y1 - y))
        region = self.im.crop((x0, y0, x1, y1))
        self.im.paste(Image.alpha_composite(region, part), (x0, y0))

    def text_size(self, s, path, size):
        f = font(path, size * self.ss)
        b = self.d.textbbox((0, 0), s, font=f)
        return (b[2] - b[0]) / self.ss, (b[3] - b[1]) / self.ss

    def text(self, x, y, s, path, size, fill=WHITE, scale=1.0, alpha=1.0, rot=0, stroke=0,
             stroke_fill=(0, 0, 0), shadow=0):
        if scale <= 0.02 or alpha <= 0.01:
            return
        ss = self.ss
        f = font(path, size * ss * scale)
        sw = int(stroke * ss * scale)
        d0 = ImageDraw.Draw(self.im)
        b = d0.textbbox((0, 0), s, font=f, stroke_width=sw)
        pad = 8 + int(shadow * ss)
        tmp = Image.new("RGBA", (b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad), (0, 0, 0, 0))
        td = ImageDraw.Draw(tmp)
        ox, oy = pad - b[0], pad - b[1]
        if shadow:
            td.text((ox, oy + shadow * ss), s, font=f, fill=(0, 0, 0, 150), stroke_width=sw,
                    stroke_fill=(0, 0, 0, 150))
        td.text((ox, oy), s, font=f, fill=tuple(fill) + (255,), stroke_width=sw,
                stroke_fill=tuple(stroke_fill) + (255,))
        if rot:
            tmp = tmp.rotate(rot, expand=True, resample=Image.BICUBIC)
        if alpha < 0.999:
            a = tmp.getchannel("A").point(lambda v: int(v * alpha))
            tmp.putalpha(a)
        self._blit(tmp, x * ss - tmp.width / 2, y * ss - tmp.height / 2)

    def done(self):
        return self.im.reduce(self.ss)


# ------------------------------------------------------------------ background
def make_bg():
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    top, bot = np.array([16, 26, 48], np.float32), np.array([7, 11, 22], np.float32)
    g = top[None, None, :] * (1 - y[..., None]) + bot[None, None, :] * y[..., None]
    g = np.repeat(g, W, axis=1)
    return Image.fromarray(g.astype(np.uint8), "RGB").convert("RGBA")


BG = make_bg()


def draw_dots(c, t):
    off = (t * 24) % 90
    for gy in range(-1, 23):
        for gx in range(0, 13):
            c.circle(gx * 90 + 20, gy * 90 + off, 3, fill=(255, 255, 255, 22))


# ------------------------------------------------------------------ motion scenes
def title(c, lt, txt, y=655):
    sc = e_back((lt - 0.05) / 0.35)
    c.text(540, y, txt, BLACK, 78, WHITE, scale=sc, stroke=0, shadow=4)
    w, _ = c.text_size(txt, BLACK, 78)
    c.rrect([540 - w * sc / 2, y + 52, 540 + w * sc / 2, y + 62], 5, fill=YELLOW + (255,))


def check_mark(c, cx, cy, r, p, col=GREEN):
    c.circle(cx, cy, r * e_back(p), fill=col + (255,))
    if p > 0.3:
        q = e_out((p - 0.3) / 0.5)
        a, b, d = (cx - r * 0.45, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.36), (cx + r * 0.5, cy - r * 0.32)

        def lerp(p0, p1, k):
            return (p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k)
        seg = [a, lerp(a, b, q * 2)] if q < 0.5 else [a, b, lerp(b, d, (q - 0.5) * 2)]
        c.line(seg, WHITE + (255,), r * 0.2)


def cross_mark(c, cx, cy, r, p, col=RED):
    c.circle(cx, cy, r * e_back(p), fill=col + (255,))
    if p > 0.3:
        k = r * 0.38
        c.line([(cx - k, cy - k), (cx + k, cy + k)], WHITE + (255,), r * 0.2)
        c.line([(cx + k, cy - k), (cx - k, cy + k)], WHITE + (255,), r * 0.2)


def sc_flow(c, lt, D, when, s0):
    title(c, lt, "PLAN DULU")
    p = e_back((lt - 0.1) / 0.3)
    c.rrect([540 - 380 * p, 750, 540 + 380 * p, 830], 28, fill=RED + (230,))
    c.text(540, 790, "TERUS SURUH AI BINA", XBOLD, 48, WHITE, scale=p)
    if lt > 0.5:
        q = e_out((lt - 0.5) / 0.35)
        c.line([(190, 790), (190 + 700 * q, 790)], WHITE + (255,), 9)
    if lt > 1.0:
        cross_mark(c, 905, 750, 38, (lt - 1.0) / 0.3)
    names = ["PLAN", "FLOW", "BINA"]
    tfl = clamp(when("flow", s0) - s0, 2.0, 3.6)
    times = [1.0, tfl - 0.3, tfl + 0.9]
    for i, (n, t0) in enumerate(zip(names, times)):
        x = 75 + i * 330
        pp = e_back((lt - t0) / 0.35)
        if pp <= 0:
            continue
        hot = n == "FLOW" and lt >= tfl - 0.1
        cx = x + 135
        w = 135 * pp
        pulse = 1 + (0.06 * math.sin((lt - tfl) * 10) if hot else 0)
        c.rrect([cx - w * pulse, 980 - 100 * pp * pulse, cx + w * pulse, 980 + 100 * pp * pulse], 30,
                fill=(YELLOW if hot else CARD2) + (255,), outline=(YELLOW if hot else GREY) + (255,), width=4)
        c.text(cx, 980, n, BLACK, 70, DARK if hot else WHITE, scale=pp)
        if i < 2:
            a = e_out((lt - t0 - 0.2) / 0.25)
            if a > 0:
                ax = x + 270
                c.line([(ax + 8, 980), (ax + 8 + 44 * a, 980)], WHITE + (255,), 10)
                if a > 0.9:
                    c.line([(ax + 38, 958), (ax + 56, 980), (ax + 38, 1002)], WHITE + (255,), 10)


def sc_chat(c, lt, D, when, s0):
    title(c, lt, "BINCANG DULU")
    p = e_back((lt - 0.15) / 0.3)
    c.rrect([1000 - 700 * p, 740, 1000, 860], 40, fill=YELLOW + (255,))
    c.text(650, 800, "Jom bincang flow app ni dulu", XBOLD, 40, DARK, scale=p)
    q = e_back((lt - 0.9) / 0.3)
    c.rrect([80, 900, 80 + 780 * q, 1020], 40, fill=CARD2 + (255,), outline=GREY + (255,), width=3)
    if 0.9 < lt < 1.7:
        for i in range(3):
            r = 9 + 5 * max(0, math.sin(lt * 12 - i * 1.2))
            c.circle(150 + i * 44, 960, r, fill=WHITE + (255,))
    elif lt >= 1.7:
        c.text(470, 960, "Boleh! Kita rancang step-by-step", XBOLD, 40, WHITE, scale=e_back((lt - 1.7) / 0.25))
    if lt > 2.2:
        check_mark(c, 900, 1080, 44, (lt - 2.2) / 0.4)


CHIPS = [("LOGIN", RED), ("PAYMENT", YELLOW), ("DASHBOARD", GREEN), ("CHAT", (120, 160, 255)),
         ("ADMIN", RED), ("NOTIFIKASI", YELLOW), ("LAPORAN", GREEN)]


def sc_prompt(c, lt, D, when, s0):
    title(c, lt, "JANGAN SEMUA SEKALI")
    n = sum(1 for i in range(len(CHIPS)) if lt > 0.7 + i * 0.55)
    shake = math.sin(lt * 45) * n * 1.4 if lt < 5.0 else 0
    ox = shake
    c.rrect([140 + ox, 730, 940 + ox, 1100], 36, fill=CARD + (255,), outline=WHITE + (255,), width=6)
    c.text(250 + ox, 775, "1 PROMPT", BLACK, 40, GREY)
    cols, rows = [300, 540, 780], [850, 940, 1030]
    for i, (name, col) in enumerate(CHIPS):
        t0 = 0.7 + i * 0.55
        if lt < t0:
            continue
        cx = cols[i % 3] + ox + (14 if i >= 6 else 0)
        cy = rows[(i // 3) % 3] + (14 if i >= 6 else 0)
        drop = (1 - e_out((lt - t0) / 0.3)) * -260
        c.rrect([cx - 108, cy - 33 + drop, cx + 108, cy + 33 + drop], 22, fill=col + (255,))
        c.text(cx, cy + drop, name, BLACK, 32, DARK)
    if lt > 5.0:
        s = e_back((lt - 5.0) / 0.3)
        c.rrect([540 - 330 * s, 1105 - 62 * s, 540 + 330 * s, 1105 + 62 * s], 20, fill=RED + (255,))
        c.text(540, 1105, "TERLALU BANYAK", BLACK, 62, WHITE, scale=s, rot=-4)


def sc_steps(c, lt, D, when, s0):
    title(c, lt, "BERPERINGKAT")
    t_next = clamp(when("seterusnya", s0) - s0, 3.5, 5.5)
    rows = [("1", "FRONT END", 0.3, 0.9), ("2", "USER EXPERIENCE", 0.6, 3.4), ("3", "SETERUSNYA...", t_next, 99)]
    c.rrect([116, 790, 124, 1090], 4, fill=GREY + (120,))
    prog = clamp((lt - 0.4) / 5.0)
    c.rrect([116, 790, 124, 790 + 300 * prog], 4, fill=GREEN + (255,))
    for i, (num, label, t0, tdone) in enumerate(rows):
        y = 830 + i * 120
        p = e_back((lt - t0) / 0.3)
        if p <= 0:
            continue
        done = lt >= tdone
        w = 820 * min(p, 1.0)
        c.rrect([150, y - 48, 150 + w, y + 48], 26, fill=(CARD2 if not done else (30, 72, 70)) + (255,),
                outline=(GREEN if done else GREY) + (255,), width=4)
        c.circle(210, y, 30 * min(p, 1.0), fill=(GREEN if done else YELLOW) + (255,))
        c.text(210, y, num, BLACK, 36, DARK, scale=min(p, 1.0))
        wl, _ = c.text_size(label, BLACK, 44)
        c.text(262 + wl / 2, y, label, BLACK, 44, WHITE, alpha=min(1, p))
        if done:
            check_mark(c, 900, y, 30, (lt - tdone) / 0.35)


def sc_check(c, lt, D, when, s0):
    title(c, lt, "CROSS-CHECK")
    p = e_back((lt - 0.05) / 0.3)
    c.rrect([540 - 400 * p, 760, 540 + 400 * p, 1100], 30, fill=DARK + (255,), outline=GREY + (255,), width=4)
    for i, col in enumerate([RED, YELLOW, GREEN]):
        c.circle(190 + i * 40, 795, 11, fill=col + (255,))
    lens = [420, 560, 300, 640, 480, 380]
    for i, L in enumerate(lens):
        y = 850 + i * 38
        bad = i == 3
        col = (RED if bad and 1.0 <= lt < 2.3 else GREEN if bad and lt >= 2.3 else (70, 90, 130))
        if bad and 1.0 <= lt < 2.3:
            c.rrect([170, y - 16, 910, y + 16], 8, fill=RED + (70,))
        c.rrect([200, y - 9, 200 + L, y + 9], 8, fill=col + (255,))
    mx = 360 + 200 * e_io((lt - 0.2) / 1.4)
    my = 850 + 38 * 3 * e_io((lt - 0.2) / 1.4)
    if lt < 2.3:
        c.circle(mx, my, 62, fill=(255, 255, 255, 25), outline=YELLOW + (255,), width=9)
        c.line([(mx + 44, my + 44), (mx + 100, my + 100)], YELLOW + (255,), 14)
    if lt >= 2.3:
        check_mark(c, 800, 1010, 56, (lt - 2.3) / 0.4)


def sc_recap(c, lt, D, when, s0):
    title(c, lt, "3 TIP VIBE CODING")
    rows = [("1", "PLAN & FLOW DULU", 0.4), ("2", "BUAT BERPERINGKAT", 1.0), ("3", "CROSS-CHECK KOD AI", 1.6)]
    for i, (num, label, t0) in enumerate(rows):
        y = 800 + i * 125
        p = e_back((lt - t0) / 0.3)
        if p <= 0:
            continue
        w = 860 * min(p, 1.0)
        c.rrect([110, y - 52, 110 + w, y + 52], 28, fill=CARD2 + (255,), outline=YELLOW + (255,), width=4)
        c.circle(185, y, 36 * min(p, 1.0), fill=YELLOW + (255,))
        c.text(185, y, num, BLACK, 44, DARK, scale=min(p, 1.0))
        wl, _ = c.text_size(label, BLACK, 46)
        c.text(250 + wl / 2, y, label, BLACK, 46, WHITE, alpha=min(1, p))


MOTION = {"flow": sc_flow, "chat": sc_chat, "prompt": sc_prompt, "steps": sc_steps,
          "check": sc_check, "recap": sc_recap}


# ------------------------------------------------------------------ face
def track_faces(path, n):
    cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(path)
    pts = np.full((n, 3), np.nan, np.float32)
    for i in range(n):
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, (360, 640)), cv2.COLOR_BGR2GRAY)
        r = cc.detectMultiScale(g, 1.1, 5, minSize=(70, 70))
        if len(r):
            x, y, w, h = max(r, key=lambda b: b[2])
            pts[i] = (2 * (x + w / 2), 2 * (y + h / 2), 2 * w)  # back to 720x1280 coords
    cap.release()
    ok = ~np.isnan(pts[:, 0])
    med = np.nanmedian(pts, axis=0)
    bad = ok & ((np.abs(pts[:, 0] - med[0]) > 160) | (np.abs(pts[:, 1] - med[1]) > 200))
    pts[bad] = np.nan
    ok = ~np.isnan(pts[:, 0])
    idx = np.arange(n)
    for k in range(3):
        pts[:, k] = np.interp(idx, idx[ok], pts[ok, k])
    ker = np.exp(-0.5 * (np.arange(-12, 13) / 5.0) ** 2)
    ker /= ker.sum()
    for k in range(3):
        padded = np.pad(pts[:, k], 12, mode="edge")
        pts[:, k] = np.convolve(padded, ker, mode="valid")
    return pts


class Source:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(path)
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.pos, self.last = 0, None

    def get(self, i):
        i = min(i, self.n - 1)
        if i == self.pos - 1 and self.last is not None:
            return self.last
        if i != self.pos:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = self.cap.read()
        if ok:
            self.last, self.pos = f, i + 1
        return self.last


def face_frame(src, i, face, z, boost):
    """Crop the 720x1280 source around the face with zoom z and resample straight to 1080x1920."""
    f = src.get(i)
    cx, cy, _ = face
    ch, cw = 1280 / z, 720 / z
    x0 = clamp(cx - cw / 2, 0, 720 - cw)
    y0 = clamp(cy - 0.40 * ch, 0, 1280 - ch)
    s = W / cw
    M = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    out = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if boost > 0.02:
        out = cv2.convertScaleAbs(out, alpha=1 + 0.10 * boost, beta=10 * boost)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB)).convert("RGBA")


def pip_image(src, i, face, zp, size=330):
    f = src.get(i)
    cx, cy, fw = face
    side = fw * 1.55 / zp
    x0 = clamp(cx - side / 2, 0, 720 - side)
    y0 = clamp(cy - side / 2 - side * 0.02, 0, 1280 - side)
    s = size / side
    M = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    out = cv2.warpAffine(f, M, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    im = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB)).convert("RGBA")
    mask = Image.new("L", (size * 3, size * 3), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 3 - 1, size * 3 - 1], fill=255)
    im.putalpha(mask.resize((size, size), Image.LANCZOS))
    return im


# ------------------------------------------------------------------ captions
def draw_captions(c, t, groups):
    g = next((g for g in groups if g["s"] - 0.02 <= t < g["e"]), None)
    if not g:
        return
    ws = g["w"]
    toks = [w["t"].upper() for w in ws]
    size = 92
    for _ in range(6):
        widths = [c.text_size(tk, BLACK, size)[0] * (1.12 if w["em"] else 1.0) for tk, w in zip(toks, ws)]
        gap = size * 0.28
        total = sum(widths) + gap * (len(toks) - 1)
        if total <= 960:
            break
        size *= 0.88
    x = 540 - total / 2
    cy = 1330
    for w, tk, wd in zip(ws, toks, widths):
        age = t - w["s"]
        if age < -0.02:
            x += wd + gap
            continue
        pop = e_back(age / 0.16)
        cur = w["s"] <= t < w["e"] + 0.05
        if w["em"]:
            sc = 1.06 + 0.12 * (1 - e_out(age / 0.3)) if age >= 0 else 1.0
            col = YELLOW
        else:
            sc = 1.0 + 0.07 * pop * (1 if cur else 0)
            col = WHITE if not cur else (255, 244, 200)
        c.text(x + wd / 2, cy, tk, BLACK, size, col, scale=sc, stroke=9, stroke_fill=(8, 10, 20),
               shadow=6)
        x += wd + gap


def hook_overlay(c, t):
    if t > 3.2:
        return
    a = 1 - clamp((t - 2.7) / 0.5)
    c.text(540, 285, "3 BENDA JANGAN BUAT", BLACK, 64, WHITE, scale=e_back((t - 0.1) / 0.3), alpha=a, stroke=7,
           stroke_fill=(8, 10, 20), shadow=5)
    k = e_back((t - 0.4) / 0.3)
    if a > 0.05 and k > 0:
        al = int(255 * a)
        c.rrect([540 - 250 * k, 335, 540 + 250 * k, 435], 30, fill=RED + (al,))
        c.text(540, 385, "VIBE CODING", BLACK, 66, WHITE, scale=k, alpha=a)


def tip_pill(c, t, marks):
    cur = None
    for s, e, n in marks:
        if s <= t < e:
            cur = (s, n)
    if not cur:
        return
    s, n = cur
    p = e_back((t - s) / 0.3)
    w = 200 * min(p, 1)
    c.rrect([60, 235 - 38 * min(p, 1), 60 + w, 235 + 38 * min(p, 1)], 38, fill=YELLOW + (255,))
    c.text(60 + w / 2, 235, f"TIP {n}", BLACK, 40, DARK, scale=min(p, 1))


# ------------------------------------------------------------------ sfx
def make_sfx(dur, sr, events):
    out = np.zeros((int(dur * sr) + sr, 2), np.float32)
    rng = np.random.default_rng(3)

    def add(t, sig, gain):
        i = int(t * sr)
        n = min(len(sig), len(out) - i)
        if i >= 0 and n > 0:
            out[i: i + n] += (sig[:n, None] * gain).astype(np.float32)

    for kind, t in events:
        if kind == "whoosh":
            n = int(0.32 * sr)
            x = np.linspace(0, 1, n)
            lp = np.cumsum(rng.standard_normal(n))
            lp = lp - np.concatenate([np.zeros(60), lp[:-60]])  # crude band-pass
            lp /= np.abs(lp).max() + 1e-9
            add(t - 0.12, lp * np.sin(np.pi * x) ** 2, 0.20)
        elif kind == "pop":
            n = int(0.14 * sr)
            x = np.arange(n) / sr
            sig = np.sin(2 * np.pi * (170 - 600 * x) * x) * np.exp(-x * 30)
            add(t, sig, 0.30)
        elif kind == "hit":
            n = int(0.5 * sr)
            x = np.arange(n) / sr
            sig = np.sin(2 * np.pi * (90 - 60 * x) * x) * np.exp(-x * 9) + 0.2 * rng.standard_normal(n) * np.exp(-x * 40)
            add(t, sig, 0.55)
    return out


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default="output/vibe-coding-3-tip.mp4")
    ap.add_argument("--preview", type=float, nargs="*")
    ap.add_argument("--work", default="/tmp/vc_work")
    a = ap.parse_args()
    import os
    os.makedirs(a.work, exist_ok=True)

    voice16 = f"{a.work}/voice16.wav"
    voice48 = f"{a.work}/voice48.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-ac", "1", "-ar", "16000", voice16], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-ac", "2", "-ar", "48000", voice48], check=True)
    x, sr = load_mono(voice16)
    dur = len(x) / sr
    n_frames = int(dur * FPS)

    words = build_words(voiced_mask(x, sr))
    groups = build_groups(words)
    spans = emphasis_spans(words)

    def when(word, after):
        for w in words:
            if w["s"] >= after - 0.5 and norm(w["t"]) == word:
                return w["s"]
        return after + 1.0

    marks = []
    for key, n in (("pertama", 1), ("kedua", 2), ("ketiga", 3)):
        marks.append([when(key, 0) - 0.05, 0, n])
    marks[0][1], marks[1][1], marks[2][1] = marks[1][0], marks[2][0], 52.86
    marks = [tuple(m) for m in marks]

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(os.path.splitext(a.out)[0] + ".srt", "w") as f:
        def ts(t):
            return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t % 1 * 1000):03d}"
        for i, g in enumerate(groups, 1):
            f.write(f"{i}\n{ts(g['s'])} --> {ts(g['e'])}\n{' '.join(w['t'] for w in g['w'])}\n\n")

    pts = track_faces(a.src, int(cv2.VideoCapture(a.src).get(cv2.CAP_PROP_FRAME_COUNT)))
    src = Source(a.src)
    scenes = [(s[0], s[1] if s[0] == "M" else None, s[-2], s[-1]) for s in SCENES]
    face_idx = [i for i, s in enumerate(scenes) if s[0] == "F"]

    def scene_at(t):
        for i, s in enumerate(scenes):
            if s[2] <= t < s[3]:
                return i
        return len(scenes) - 1

    def scene_img(t, i):
        kind, name, s0, s1 = scenes[i]
        fi = min(int(round(t * FPS)), len(pts) - 1)
        e = env(spans, t)
        if kind == "F":
            k = face_idx.index(i)
            u = clamp((t - s0) / max(0.5, min(s1, dur) - s0))
            base = (1.08 + 0.07 * u) if k % 2 == 0 else (1.20 - 0.08 * u)
            if k == 0:
                base += 0.25 * (1 - e_out((t - s0) / 0.45))
            z = base * (1 + 0.20 * e)
            img = face_frame(src, fi, pts[fi], z, e)
            c = Canvas()
        else:
            img = BG.copy()
            c = Canvas()
            draw_dots(c, t)
            lt = t - s0
            MOTION[name](c, lt, s1 - s0, when, s0)
        return img, c, kind, name

    def render(t):
        i = scene_at(t)
        img, c, kind, name = scene_img(t, i)
        fi = min(int(round(t * FPS)), len(pts) - 1)
        if name != "recap":
            tip_pill(c, t, marks)
        hook_overlay(c, t)
        draw_captions(c, t, groups)
        layer = c.done()
        img = Image.alpha_composite(img, layer)
        if kind == "M":
            zp = 1 + 0.35 * env(spans, t)
            pip = pip_image(src, fi, pts[fi], zp)
            cc = Canvas()
            ring = 1 + 0.05 * env(spans, t)
            cc.circle(840, 360, 171 * ring, fill=YELLOW + (255,))
            img = Image.alpha_composite(img, cc.done())
            img.alpha_composite(pip, (840 - 165, 360 - 165))
        # wipe transition from the previous scene
        s0 = scenes[i][2]
        if i > 0 and t - s0 < TRANS:
            prog = e_io((t - s0) / TRANS)
            pi = i - 1
            pimg, pc, pk, pn = scene_img(t, pi)
            pimg = Image.alpha_composite(pimg, pc.done())
            xs = np.arange(W)[None, :] + np.arange(H)[:, None] * 0.25
            edge = prog * (W + H * 0.25)
            mask = (xs < edge).astype(np.uint8) * 255
            band = ((xs >= edge - 14) & (xs < edge)).astype(np.uint8)
            new = np.array(img.convert("RGB"))
            old = np.array(pimg.convert("RGB"))
            res = np.where(mask[..., None] > 0, new, old)
            res[band > 0] = YELLOW
            img = Image.fromarray(res).convert("RGBA")
        return img.convert("RGB")

    if a.preview:
        for t in a.preview:
            render(t).save(f"{a.work}/preview_{t:06.2f}.png")
            print("saved", f"{a.work}/preview_{t:06.2f}.png")
        return

    # audio: voice + sfx
    events = [("hit", 0.15)]
    for s in scenes[1:]:
        if s[2] < dur:
            events.append(("whoosh", s[2]))
    for s, e in spans:
        if any(sc[0] == "F" and sc[2] <= s < sc[3] for sc in scenes):
            events.append(("pop", s + 0.04))
    sfx = make_sfx(dur, 48000, events)
    w = wave.open(voice48)
    v = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768
    mix = sfx[: len(v)] + 0 if len(sfx) >= len(v) else np.pad(sfx, ((0, len(v) - len(sfx)), (0, 0)))
    mix = mix[: len(v)] + v
    mix = np.clip(mix, -1, 1)
    mixpath = f"{a.work}/mix.wav"
    with wave.open(mixpath, "wb") as ow:
        ow.setnchannels(2)
        ow.setsampwidth(2)
        ow.setframerate(48000)
        ow.writeframes((mix * 32767).astype(np.int16).tobytes())

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", mixpath, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium",
         "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
         a.out], stdin=subprocess.PIPE)
    for n in range(n_frames):
        ff.stdin.write(render(n / FPS).tobytes())
        if n % 60 == 0:
            print(f"{n}/{n_frames}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", a.out)


if __name__ == "__main__":
    main()
