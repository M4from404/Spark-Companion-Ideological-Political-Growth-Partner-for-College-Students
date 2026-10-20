# -*- coding: utf-8 -*-
"""Render the appended 'character & features' chapter (1920x1080, 24fps, 59s).

Layout is authored in a 1280x720 design space; K scales every coordinate,
font and asset up to the native 1080p canvas, so nothing is upscaled after
compositing.
"""
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

K = 1.5                       # design 1280x720 -> output 1920x1080
W, H, FPS = 1280 * K, 720 * K, 24
W, H = int(W), int(H)
DUR = 59.0
NFRAMES = int(DUR * FPS)
HEAD = "C:/Windows/Fonts/msyhbd.ttc"
BODY = "C:/Windows/Fonts/msyh.ttc"
FF = __import__("imageio_ffmpeg").get_ffmpeg_exe()

CREAM = (246, 240, 228, 255)
WHITE = (255, 255, 255, 255)
GOLD = (232, 168, 124, 255)
TEAL = (127, 179, 165, 255)
MUTED = (208, 200, 187, 235)
DARK = (16, 15, 14)

VO_STARTS = {"hook": 1.5, "intro": 6.0, "f1": 20.5, "f2": 31.7, "f3": 42.8, "outro": 54.4}
SCENES = [("title", 0.0, 5.4), ("intro", 5.4, 20.2), ("f1", 20.2, 31.4),
          ("f2", 31.4, 42.5), ("f3", 42.5, 53.6), ("outro", 53.6, 59.0)]

_fonts = {}


def font(bold, size):
    key = (bold, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(HEAD if bold else BODY, int(round(size * K)))
    return _fonts[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def lerp(a, b, k):
    return a + (b - a) * k


_txt_cache = {}


def txt(text, size, color, bold=True, spacing=0, stroke=0, stroke_color=(0, 0, 0, 0), shadow=None):
    key = (text, size, color, bold, spacing, stroke, stroke_color, shadow)
    if key in _txt_cache:
        return _txt_cache[key]
    f = font(bold, size)
    spacing = spacing * K
    stroke = int(round(stroke * K))
    shadow = int(round(shadow * K)) if shadow else 0
    widths = [f.getlength(ch) for ch in text]
    tw = int(math.ceil(sum(widths) + spacing * max(0, len(text) - 1)))
    asc, desc = f.getmetrics()
    pad = max(int(round(4 * K)), stroke + int(round(3 * K)))
    img = Image.new("RGBA", (tw + pad * 2 + (shadow or 0), asc + desc + pad * 2 + (shadow or 0)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if shadow:
        x = pad + shadow
        for ch, wd in zip(text, widths):
            d.text((x, pad + shadow), ch, font=f, fill=(0, 0, 0, 130))
            x += wd + spacing
    x = pad
    for ch, wd in zip(text, widths):
        d.text((x, pad), ch, font=f, fill=color, stroke_width=stroke, stroke_fill=stroke_color)
        x += wd + spacing
    _txt_cache[key] = img
    return img


def paste(base, im, xy, alpha=1.0):
    """xy is in design (1280x720) coordinates."""
    paste_px(base, im, (xy[0] * K, xy[1] * K), alpha)


def paste_px(base, im, xy, alpha=1.0):
    """xy is in output pixels."""
    if alpha <= 0.003:
        return
    if alpha >= 0.996:
        base.alpha_composite(im, (int(xy[0]), int(xy[1])))
        return
    a = im.getchannel("A").point(lambda v: int(v * alpha))
    layer = im.copy()
    layer.putalpha(a)
    base.alpha_composite(layer, (int(xy[0]), int(xy[1])))


def paste_center(base, im, cx, y, alpha=1.0):
    paste(base, im, (cx - im.width / (2 * K), y), alpha)


class SDraw:
    """ImageDraw proxy that accepts design-space geometry and scales it to 1080p."""

    def __init__(self, im):
        self._d = ImageDraw.Draw(im)

    @staticmethod
    def _xy(xy):
        if len(xy) == 4 and not isinstance(xy[0], (tuple, list)):
            return [xy[0] * K, xy[1] * K, xy[2] * K, xy[3] * K]
        return [(p[0] * K, p[1] * K) for p in xy]

    def line(self, xy, fill=None, width=1, joint=None):
        self._d.line(self._xy(xy), fill=fill, width=max(1, int(round(width * K))), joint=joint)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self._d.rectangle(self._xy(xy), fill=fill, outline=outline,
                          width=max(1, int(round(width * K))))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1):
        self._d.rounded_rectangle(self._xy(xy), radius=int(round(radius * K)), fill=fill,
                                  outline=outline, width=max(1, int(round(width * K))))

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self._d.ellipse(self._xy(xy), fill=fill, outline=outline,
                        width=max(1, int(round(width * K))))

    def polygon(self, xy, fill=None, outline=None):
        self._d.polygon(self._xy(xy), fill=fill, outline=outline)

    def arc(self, xy, start, end, fill=None, width=1):
        self._d.arc(self._xy(xy), start, end, fill=fill, width=max(1, int(round(width * K))))


def sdraw(im):
    return SDraw(im)


_bg_cache = {}


def load_bg(name):
    if name not in _bg_cache:
        im = Image.open(f"assets/bg/{name}.png").convert("RGB")
        _bg_cache[name] = im
    return _bg_cache[name]


def bg_frame(name, zoom=1.0, fx=0.5, fy=0.5, blur=0.0):
    src = load_bg(name)
    sw, sh = src.size
    tw, th = W * zoom, H * zoom
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    im = src.resize((nw, nh), Image.LANCZOS)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * K))
    x = (nw - tw) * clamp(fx)
    y = (nh - th) * clamp(fy)
    im = im.crop((int(x), int(y), int(x + tw), int(y + th))).resize((W, H), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=45, threshold=2))
    out = im.convert("RGBA")
    return out


def vgrad(w, h, top, bottom):
    g = Image.new("RGBA", (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(lerp(top[i], bottom[i], k)) for i in range(4)))
    return g.resize((w, h))


def hgrad(w, h, left, right):
    g = Image.new("RGBA", (w, 1))
    for x in range(w):
        k = x / max(1, w - 1)
        g.putpixel((x, 0), tuple(int(lerp(left[i], right[i], k)) for i in range(4)))
    return g.resize((w, h))


def radial(size, color, power=2.0):
    s = size
    y, x = np.mgrid[0:s, 0:s]
    cx = cy = (s - 1) / 2
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (s / 2)
    a = np.clip(1 - r, 0, 1) ** power
    arr = np.zeros((s, s, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color[:3]
    arr[..., 3] = (a * color[3]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


_mw, _mh = int(260 * K), int(130 * K)
VIGNETTE = radial(int(1600 * K), (0, 0, 0, 158), 2.6).resize((W + 2 * _mw, H + 2 * _mh), Image.LANCZOS)
VIGNETTE = VIGNETTE.crop((_mw, _mh, _mw + W, _mh + H))
BOTTOM_GRAD = vgrad(W, int(260 * K), (8, 7, 6, 0), (8, 7, 6, 215))
TOP_GRAD = vgrad(W, int(170 * K), (8, 7, 6, 150), (8, 7, 6, 0))
TITLE_LEFT = hgrad(int(900 * K), H, (13, 12, 11, 225), (13, 12, 11, 0))
FEATURE_LEFT = hgrad(W, H, (11, 11, 10, 215), (11, 11, 10, 35))
GRAIN = (np.random.default_rng(3).normal(0, 1, (H, W)) * 5.0).astype(np.int16)


def darken(im, amount):
    if amount <= 0:
        return im
    ov = Image.new("RGBA", (W, H), (8, 8, 8, int(amount * 255)))
    im.alpha_composite(ov)
    return im


def grain(im):
    arr = np.array(im.convert("RGB")).astype(np.int16)
    arr += GRAIN[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def finish(im):
    im.alpha_composite(VIGNETTE)
    return im


# ---------------------------------------------------------------- icons
def icon_chat(size=160):
    s = size * 4
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    col = TEAL
    d.rounded_rectangle([s * 0.12, s * 0.2, s * 0.88, s * 0.7], radius=int(s * 0.16), outline=col, width=int(s * 0.045))
    d.polygon([(s * 0.3, s * 0.7), (s * 0.3, s * 0.86), (s * 0.46, s * 0.7)], fill=col)
    for i in range(3):
        cx = s * (0.34 + i * 0.16)
        d.ellipse([cx - s * 0.026, s * 0.425, cx + s * 0.026, s * 0.477], fill=col)
    return im.resize((size, size), Image.LANCZOS)


def icon_quiz(size=160):
    s = size * 4
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    col = TEAL
    d.ellipse([s * 0.18, s * 0.12, s * 0.82, s * 0.76], outline=col, width=int(s * 0.045))
    d.polygon([(s * 0.34, s * 0.72), (s * 0.28, s * 0.9), (s * 0.48, s * 0.8)], fill=col)
    d.line([(s * 0.34, s * 0.44), (s * 0.45, s * 0.56), (s * 0.66, s * 0.32)], fill=col, width=int(s * 0.05), joint="curve")
    return im.resize((size, size), Image.LANCZOS)


def icon_speaker(size=160):
    s = size * 4
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    col = TEAL
    d.rounded_rectangle([s * 0.12, s * 0.4, s * 0.28, s * 0.6], radius=int(s * 0.03), outline=col, width=int(s * 0.035))
    d.polygon([(s * 0.26, s * 0.4), (s * 0.46, s * 0.24), (s * 0.46, s * 0.76), (s * 0.26, s * 0.6)], outline=col, width=int(s * 0.035))
    for i, r in enumerate((0.12, 0.2, 0.28)):
        d.arc([s * (0.42 - r), s * (0.5 - r), s * (0.42 + r), s * (0.5 + r)], -55, 55, fill=col, width=int(s * 0.035))
    return im.resize((size, size), Image.LANCZOS)


ICONS = {"chat": icon_chat(int(96 * K)), "quiz": icon_quiz(int(96 * K)),
         "speaker": icon_speaker(int(96 * K))}


def logo_mark(size=44):
    im = Image.new("RGBA", (size * 4, size * 4))
    d = ImageDraw.Draw(im)
    s = size * 4
    d.ellipse([2, 2, s - 2, s - 2], outline=TEAL, width=int(s * 0.035))
    cx = cy = s / 2
    for rx, ry in ((0.11, 0.3), (0.3, 0.11)):
        d.ellipse([cx - s * rx, cy - s * ry, cx + s * rx, cy + s * ry], fill=CREAM)
    d.ellipse([cx - s * 0.045, cy - s * 0.045, cx + s * 0.045, cy + s * 0.045], fill=GOLD)
    return im.resize((size, size), Image.LANCZOS)


LOGO = logo_mark(int(44 * K))


def shadow_ellipse(w, h):
    w, h = int(w * K), int(h * K)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, w - 1, h - 1], fill=(0, 0, 0, 150))
    return im.filter(ImageFilter.GaussianBlur(9 * K))


def vivid(im):
    """Lift the artwork out of the muted scene grade without shifting skin tones."""
    im = ImageEnhance.Color(im).enhance(1.52)
    im = ImageEnhance.Brightness(im).enhance(1.16)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    return im


def vivid_sprite(im):
    """Strong, clean colour for the character sprites.

    Chroma is stretched in Lab space (with a light median pass so the
    pleats do not turn into rainbow banding), then brightness is lifted a
    little so the figure stays warm against the dark classroom plate.
    """
    arr = np.array(im)
    lab = cv2.cvtColor(arr[..., [2, 1, 0]].copy(), cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    a = cv2.medianBlur(a, 5)
    b = cv2.medianBlur(b, 5)
    a = np.clip((a.astype(np.float32) - 128) * 2.25 + 128, 0, 255).astype(np.uint8)
    b = np.clip((b.astype(np.float32) - 128) * 2.25 + 128, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    out = np.dstack([bgr[..., 2], bgr[..., 1], bgr[..., 0], arr[..., 3]])
    im = Image.fromarray(out, "RGBA")
    im = ImageEnhance.Brightness(im).enhance(1.27)
    im = ImageEnhance.Contrast(im).enhance(1.03)
    return im


SPRITES = {n: vivid_sprite(Image.open(f"assets/sprites/{n}.png"))
           for n in ("stand", "wave", "think", "talk")}


def sprite(name, height, x, bottom, alpha=1.0, bob=0.0, base=None):
    sp = SPRITES[name]
    height = int(height * K)
    w = int(sp.width * height / sp.height)
    s = sp.resize((w, height), Image.LANCZOS).filter(
        ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=2))
    if base is not None:
        base.alpha_composite(s, (int(x * K), int((bottom - height / K + bob) * K)))


# ---------------------------------------------------------------- text blocks
def top_brand(base, alpha=0.9):
    paste(base, LOGO, (64, 44), alpha)
    paste(base, txt("星火同行", 17, CREAM, True, 2), (120, 51), alpha)
    lab = txt("AI 思政辅导员 · 角色 PV", 12, (230, 224, 212, 190), False, 1)
    paste_px(base, lab, (W - 74 * K - lab.width, 56 * K), alpha * 0.9)


def part_tag(base, text, alpha=1.0):
    dot = Image.new("RGBA", (int(7 * K), int(7 * K)), GOLD)
    paste(base, dot, (66, 91), alpha)
    paste(base, txt(text, 12, (236, 230, 218, 200), False, 1), (80, 84), alpha)


# ---------------------------------------------------------------- subtitles
def load_meta():
    meta = json.load(open("assets/audio/vo/meta.json", encoding="utf-8"))
    return meta


def build_subs():
    meta = load_meta()
    subs = []
    for key, start in VO_STARTS.items():
        info = meta[key]
        dur = info["duration"]
        text = info["text"]
        sentences = [x for x in re.split(r"(?<=[。！？])", text) if x.strip()]
        bounds = [w["t"] for w in info["words"] if "t" in w]
        starts = [bounds[i] if i < len(bounds) else dur * i / len(sentences) for i in range(len(sentences))]
        for i, sent in enumerate(sentences):
            s0 = start + starts[i]
            s1 = start + (starts[i + 1] if i + 1 < len(sentences) else dur + 0.12)
            parts = [x for x in re.split(r"(?<=[，；、])", sent) if x.strip()]
            groups = []
            cur = ""
            for part in parts:
                if cur and len(cur) + len(part) > 17:
                    groups.append(cur)
                    cur = part
                else:
                    cur += part
            if cur:
                groups.append(cur)
            # merge a very short trailing group into the previous one
            if len(groups) > 1 and len(groups[-1]) < 6:
                groups[-2] += groups[-1]
                groups.pop()
            total = sum(len(g) for g in groups) or 1
            acc = 0
            for j, g in enumerate(groups):
                a = s0 + (s1 - s0) * acc / total
                acc += len(g)
                b = s0 + (s1 - s0) * acc / total
                if j == 0:
                    a = max(s0, start + (starts[i] if i < len(bounds) else 0) - 0.02)
                if j == len(groups) - 1:
                    if i + 1 < len(sentences):
                        b = min(b, start + starts[i + 1] - 0.04)
                    else:
                        b = max(b, min(start + dur + 0.22, s1 + 0.2))
                subs.append((a, b, g.strip("，；、")))
    return subs


SUB_IMGS = {}


def sub_img(text):
    if text not in SUB_IMGS:
        SUB_IMGS[text] = txt(text, 29, (255, 255, 255, 245), True, 0, 1, (0, 0, 0, 120), shadow=2)
    return SUB_IMGS[text]


def draw_subs(base, t, subs):
    active = [s for s in subs if s[0] - 0.06 <= t <= s[1]]
    if not active:
        return
    a, b, text = max(active, key=lambda s: s[0])
    k = min(smooth((t - a + 0.06) / 0.14), smooth((b - t + 0.04) / 0.14), 1.0)
    im = sub_img(text)
    paste_px(base, im, ((W - im.width) / 2, 638 * K - im.height / 2), k)


# ---------------------------------------------------------------- scenes
def scene_title(lt):
    k = clamp(lt / 5.4)
    im = bg_frame("classroom", zoom=lerp(1.03, 1.09, k), fx=0.55, fy=0.45)
    im.alpha_composite(TITLE_LEFT)
    im.alpha_composite(TOP_GRAD)
    # warm glow behind character
    glow = radial(int(760 * K), (255, 196, 130, 90), 2.2)
    paste(im, glow, (690, 40), 0.75)
    # sprite
    enter = ease_out(clamp((lt - 0.7) / 1.1))
    bob = math.sin(lt * 1.6) * 2.5
    shadow = shadow_ellipse(320, 44)
    paste(im, shadow, (820, 676), 0.55 * enter)
    sprite("stand", 620, 815 + (1 - enter) * 40, 700, enter, bob, im)
    top_brand(im, 0.95)
    part_tag(im, "PART 02 · 认识楚晚晴", 0.0)
    # left copy
    a = smooth(clamp((lt - 0.45) / 0.7))
    paste(im, txt("CHARACTER  &  FEATURES", 12, GOLD, True, 4), (100, 168), a)
    a2 = smooth(clamp((lt - 0.75) / 0.8))
    paste(im, txt("认识楚晚晴", 54, CREAM, True, 2, shadow=2), (96, 196), a2)
    a3 = smooth(clamp((lt - 1.1) / 0.8))
    d = sdraw(im)
    if a3 > 0:
        d.line([(100, 300), (100 + int(64 * a3), 300)], fill=GOLD, width=3)
    paste(im, txt("她是谁？她能为青年做什么？", 21, (236, 230, 219, 225), False, 1), (100, 320), a3)
    a4 = smooth(clamp((lt - 1.8) / 1.0))
    paste(im, txt("从一次对话开始，陪你走过学业、迷茫与低谷。", 15, (224, 218, 207, 200), False, 0.5), (100, 366), a4)
    # bottom brand line
    a5 = smooth(clamp((lt - 2.3) / 1.0))
    paste(im, txt("星火同行 · 青年成长伙伴", 15, (236, 230, 218, 200), False, 2), (100, 602), a5)
    return finish(im)


def load_portrait():
    p = Image.open("assets/portrait.jpg").convert("RGB")
    # 4:5 crop from the top
    target = 4 / 5
    w, h = p.size
    if w / h > target:
        nw = int(h * target)
        p = p.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    else:
        nh = int(w / target)
        p = p.crop((0, 0, w, nh))
    return p


PORTRAIT = vivid(load_portrait())


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def portrait_card(size=(360 * K, 450 * K), zoom=1.0):
    size = (int(size[0]), int(size[1]))
    w, h = size
    sw, sh = PORTRAIT.size
    scale = max(w / sw, h / sh) * zoom
    im = PORTRAIT.resize((int(sw * scale), int(sh * scale)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int((im.height - h) * 0.15)
    im = im.crop((x, y, x + w, y + h)).convert("RGBA")
    tint = Image.new("RGBA", size, (255, 194, 146, 26))
    im.alpha_composite(tint)
    im.putalpha(rounded_mask(size, int(20 * K)))
    # bottom shading
    sh_grad = vgrad(w, int(h * 0.45), (0, 0, 0, 0), (0, 0, 0, 90))
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    base.alpha_composite(im)
    base.alpha_composite(sh_grad, (0, h - int(h * 0.45)))
    return base


def scene_intro(lt):
    k = clamp(lt / 14.8)
    im = bg_frame("classroom", zoom=lerp(1.04, 1.08, k), fx=0.5, fy=0.4, blur=7)
    darken(im, 0.36)
    im.alpha_composite(FEATURE_LEFT)
    im.alpha_composite(BOTTOM_GRAD, (0, H - BOTTOM_GRAD.height))
    top_brand(im, 0.8)
    part_tag(im, "PART 02 · 角色介绍", 0.75)

    enter = ease_out(clamp(lt / 0.8))
    # portrait card
    card = portrait_card(zoom=1.0 + 0.035 * k)
    paste(im, shadow_ellipse(380, 60), (86, 596), 0.55 * enter)
    paste(im, Image.new("RGBA", (10, 10)), (0, 0), 0)
    x = 104 - (1 - enter) * 24
    paste(im, card, (x, 140), enter)
    d = sdraw(im)
    if enter > 0.1:
        ov = Image.new("RGBA", card.size, (0, 0, 0, 0))
        dd = ImageDraw.Draw(ov)
        dd.rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=int(20 * K), outline=(255, 255, 255, 55), width=max(1, int(K)))
        paste(im, ov, (x, 140), enter)

    # text block
    a = smooth(clamp((lt - 0.5) / 0.7))
    paste(im, txt("ABOUT  HER", 12, GOLD, True, 4), (520, 150), a)
    paste(im, txt("楚晚晴", 58, CREAM, True, 3, shadow=2), (516, 174), smooth(clamp((lt - 0.65) / 0.8)))
    paste(im, txt("CHU  WANQING", 11, (222, 216, 204, 165), True, 4), (522, 252), a)
    paste(im, txt("22 岁 · 大学思政辅导员", 19, (190, 220, 210, 240), False, 0.5), (520, 282), smooth(clamp((lt - 0.85) / 0.8)))
    d.line([(520, 326), (520 + int(470 * smooth(clamp((lt - 1.0) / 0.9))), 326)], fill=(255, 255, 255, 45), width=1)

    q1 = smooth(clamp((lt - 1.5) / 0.7))
    paste(im, txt("比起给你标准答案，", 24, (250, 246, 238, 250), False, 0.5), (520, 350), q1)
    q2 = smooth(clamp((lt - 2.1) / 0.7))
    paste(im, txt("我更想先听你把话说完。", 24, (250, 246, 238, 250), False, 0.5), (520, 386), q2)
    # quote accent
    if q1 > 0:
        dv = sdraw(im)
        dv.rectangle([500, 352, 503, 456], fill=(232, 168, 124, 170))

    tags = ["知性温柔", "耐心倾听", "随时在线"]
    for i, tg in enumerate(tags):
        ta = smooth(clamp((lt - 3.2 - i * 0.55) / 0.6))
        if ta <= 0:
            continue
        im_t = txt(tg, 15, (238, 233, 223, 235), False, 1)
        w = im_t.width + int(30 * K)
        h = int(34 * K)
        pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(17 * K), fill=(127, 179, 165, 30), outline=(127, 179, 165, 120), width=max(1, int(K)))
        pill.alpha_composite(im_t, (int(15 * K), (h - im_t.height) // 2 + int(2 * K)))
        paste(im, pill, (520 + i * 128, 476), ta)
    a6 = smooth(clamp((lt - 5.2) / 0.8))
    paste(im, txt("学业 · 情感 · 成长，都可以来找我聊", 14, (214, 208, 197, 200), False, 0.5), (520, 546), a6)
    return finish(im)


FEATURES = [
    dict(key="f1", bg="study", num="01", icon="chat", title="随时在线的对话陪伴",
         sub="不用预约，也不必斟酌措辞",
         desc=["学业压力、科研卡壳、人际烦恼，", "都可以慢慢说，我陪你找到下一步。"],
         badge="24 小时在线",
         rows=["学业压力 · 科研卡壳", "人际相处 · 情感困惑", "多轮对话，不急着给结论"]),
    dict(key="f2", bg="campus", num="02", icon="quiz", title="思政知识闯关",
         sub="三关十五题，边闯边学",
         desc=["每关五题，答对四题解锁下一关。", "让理论学习，也变成一场闯关。"],
         badge="3 关 × 15 题",
         rows=["三个关卡，循序渐进", "答对 4 题解锁下一关", "思政知识，边闯边学"]),
    dict(key="f3", bg="balcony", num="03", icon="speaker", title="甜声语音朗读",
         sub="晓伊音色，像学姐在耳边说话",
         desc=["把回答温柔地读给你听，", "不打扰，也不敷衍。"],
         badge="离线运行 · 数据不出本机",
         rows=["晓伊音色 · 甜声朗读", "像学姐在耳边说话", "完全离线 · 数据不出本机"]),
]


def glass_panel(w, h):
    r = int(18 * K)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=(255, 255, 255, 20))
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=(255, 255, 255, 38), width=max(1, int(K)))
    top = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = vgrad(w, h, (255, 255, 255, 18), (255, 255, 255, 0))
    top.alpha_composite(g)
    mask = rounded_mask((w, h), r)
    top.putalpha(Image.composite(top.getchannel("A"), Image.new("L", (w, h), 0), mask))
    im.alpha_composite(top)
    return im


PANEL = glass_panel(int(500 * K), int(392 * K))


def scene_feature(lt, feat):
    dur = {"f1": 11.2, "f2": 11.1, "f3": 11.1}[feat["key"]]
    k = clamp(lt / dur)
    im = bg_frame(feat["bg"], zoom=lerp(1.05, 1.11, k), fx=0.55, fy=0.5)
    darken(im, 0.26)
    im.alpha_composite(FEATURE_LEFT)
    im.alpha_composite(BOTTOM_GRAD, (0, H - BOTTOM_GRAD.height))
    im.alpha_composite(TOP_GRAD)
    top_brand(im, 0.8)
    part_tag(im, "PART 02 · 功能介绍", 0.75)

    e = ease_out(clamp((lt - 0.1) / 0.7))
    # big index
    num = txt(feat["num"], 126, (255, 255, 255, 62), True, 0, 2, (255, 255, 255, 62))
    paste(im, num, (90, 62 + (1 - e) * 12), e)
    paste(im, txt(f"FEATURE {feat['num']} / 03", 12, GOLD, True, 4), (98, 128), e)
    paste(im, txt(feat["title"], 40, CREAM, True, 1, shadow=2), (96, 156 + (1 - e) * 16), e)
    paste(im, txt(feat["sub"], 20, (184, 216, 206, 245), False, 0.5), (98, 212), ease_out(clamp((lt - 0.3) / 0.7)))
    dy = ease_out(clamp((lt - 0.45) / 0.8))
    for i, line in enumerate(feat["desc"]):
        paste(im, txt(line, 17, (224, 218, 208, 225), False, 0.5), (98, 258 + i * 29), dy)

    # icon badge
    ib = ease_out(clamp((lt - 0.7) / 0.7))
    bw = int(76 * K)
    badge = Image.new("RGBA", (bw, bw), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle([0, 0, bw - 1, bw - 1], radius=int(18 * K), fill=(127, 179, 165, 26), outline=(127, 179, 165, 110), width=max(1, int(K)))
    ic = ICONS[feat["icon"]].resize((int(52 * K), int(52 * K)), Image.LANCZOS)
    badge.alpha_composite(ic, (int(12 * K), int(12 * K)))
    paste(im, badge, (96, 352), ib)
    paste(im, txt(feat["badge"], 14, (236, 230, 219, 220), False, 0.5), (188, 374), ib)
    idx_now = int(feat["num"]) - 1
    dprog = sdraw(im)
    for i in range(3):
        on = i == idx_now
        col = (232, 168, 124, 230) if on else (255, 255, 255, 50)
        dprog.rectangle([98 + i * 46, 452, 98 + i * 46 + (34 if on else 26), 454], fill=col)

    # glass panel
    d = sdraw(im)
    px, py = 688, 158
    pe = ease_out(clamp((lt - 0.25) / 0.8))
    paste(im, PANEL, (px + (1 - pe) * 26, py), pe)
    paste(im, txt("核心能力", 12, GOLD, True, 4), (px + 40, py + 34), pe)
    paste(im, txt(feat["num"] + " / 03", 12, (235, 230, 220, 150), True, 2), (px + 400, py + 34), pe)
    d.line([(px + 40, py + 70), (px + 460, py + 70)], fill=(255, 255, 255, 34), width=1)
    for i, row in enumerate(feat["rows"]):
        ra = smooth(clamp((lt - 0.75 - i * 0.55) / 0.55))
        y = py + 96 + i * 88
        if ra <= 0:
            continue
        ds = int(26 * K)
        dot = Image.new("RGBA", (ds, ds), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot)
        dd.ellipse([int(K), int(K), ds - int(K), ds - int(K)], fill=(127, 179, 165, 36), outline=(127, 179, 165, 180), width=max(1, int(K)))
        dd.line([(int(8 * K), int(13 * K)), (int(12 * K), int(17 * K)), (int(19 * K), int(9 * K))], fill=(232, 240, 234, 235), width=int(2 * K))
        paste(im, dot, (px + 40, y + 3), ra)
        paste(im, txt(row, 18, (247, 243, 235, 240), False, 0.3), (px + 80, y), ra)
        if i < 2:
            d.line([(px + 40, y + 48), (px + 460, y + 48)], fill=(255, 255, 255, 22), width=1)
    # bottom hint
    paste(im, txt("★", 10, (232, 168, 124, 200), True), (px + 40, py + 356), 0.8)
    paste(im, txt("星火同行 · 楚晚晴", 13, (231, 225, 214, 178), False, 1), (px + 60, py + 350), 0.85)
    return finish(im)


def scene_outro(lt):
    k = clamp(lt / 5.4)
    d = None
    im = bg_frame("balcony", zoom=lerp(1.04, 1.10, k), fx=0.55, fy=0.45)
    darken(im, 0.16)
    im.alpha_composite(TITLE_LEFT)
    im.alpha_composite(BOTTOM_GRAD, (0, H - BOTTOM_GRAD.height))
    glow = radial(int(720 * K), (255, 190, 130, 110), 2.0)
    paste(im, glow, (560, 20), 0.85)
    enter = ease_out(clamp(lt / 0.9))
    paste(im, shadow_ellipse(330, 44), (806, 686), 0.5 * enter)
    sprite("wave", 620, 806 + (1 - enter) * 34, 716, enter, math.sin(lt * 1.8) * 2.0, im)
    # outro keeps a single brand lockup on the left
    part_tag(im, "PART 02 · 写在最后", 0.75)
    a = smooth(clamp((lt - 0.3) / 0.8))
    paste(im, LOGO, (100, 150), a)
    paste(im, txt("星火同行", 19, GOLD, True, 4), (160, 156), a)
    a2 = smooth(clamp((lt - 0.55) / 0.9))
    paste(im, txt("青年成长伙伴", 46, CREAM, True, 2, shadow=2), (96, 206), a2)
    a3 = smooth(clamp((lt - 1.0) / 0.9))
    d = sdraw(im)
    d.line([(100, 288), (100 + int(60 * a3), 288)], fill=GOLD, width=3)
    paste(im, txt("陪伴青年成长，为青春领航", 22, (196, 224, 213, 245), False, 0.8), (100, 308), a3)
    a4 = smooth(clamp((lt - 1.6) / 1.0))
    paste(im, txt("AI 思政辅导员 · 楚晚晴", 15, (234, 228, 216, 238), False, 1, shadow=1), (100, 360), a4)
    a5 = smooth(clamp((lt - 2.2) / 1.0))
    paste(im, txt("完全离线 · 数据不出本机", 13, (230, 224, 212, 200), False, 1, shadow=1), (100, 396), a5)
    return finish(im)


RENDERERS = {
    "title": scene_title,
    "intro": scene_intro,
    "f1": lambda lt: scene_feature(lt, FEATURES[0]),
    "f2": lambda lt: scene_feature(lt, FEATURES[1]),
    "f3": lambda lt: scene_feature(lt, FEATURES[2]),
    "outro": scene_outro,
}
SUBS = build_subs()


def render_frame(t):
    # find active scene with crossfade
    idx = 0
    for i, (_, s, e) in enumerate(SCENES):
        if s <= t < e:
            idx = i
            break
    else:
        idx = len(SCENES) - 1
    name, start, end = SCENES[idx]
    im = RENDERERS[name](t - start)
    half = 0.34
    if idx > 0 and t - start < half:
        pname, ps, pe = SCENES[idx - 1]
        prev = RENDERERS[pname](t - ps)
        k = smooth((t - (start - half)) / (2 * half))
        im = Image.blend(prev, im, k)
    if idx < len(SCENES) - 1 and end - t < half:
        nname, ns, ne = SCENES[idx + 1]
        nxt = RENDERERS[nname](t - ns)
        k = smooth((t - (end - half)) / (2 * half))
        im = Image.blend(im, nxt, k)
    draw_subs(im, t, SUBS)
    # fades
    if t < 0.45:
        im = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), im, smooth(t / 0.45))
    if t > DUR - 0.85:
        im = Image.blend(im, Image.new("RGBA", (W, H), (0, 0, 0, 255)), smooth((t - (DUR - 0.85)) / 0.85))
    return grain(im)


def stills(times):
    os.makedirs("qa/stills", exist_ok=True)
    for t in times:
        im = render_frame(t).convert("RGB")
        im.save(f"qa/stills/t{t:05.1f}.jpg", quality=92)
        print("saved", t)


def render_video():
    out = "assets/chapter.mp4"
    cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(NFRAMES):
        t = f / FPS
        im = render_frame(t).convert("RGB")
        proc.stdin.write(im.tobytes())
        if f % 120 == 0:
            print(f"frame {f}/{NFRAMES}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("encoded", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stills":
        stills([1.2, 3.0, 6.5, 9.0, 13.0, 19.0, 22.0, 27.0, 33.5, 38.0, 44.5, 49.0, 55.5, 57.5])
    else:
        render_video()
