# -*- coding: utf-8 -*-
"""Render the replacement 'dual-end' segment (PC + mobile) at 1080p.

Keeps the existing title / character intro / feature 1-2 / outro, and swaps
the old feature-3 scene for a 40 s dual-end walkthrough with real screen
recordings embedded in a monitor and a phone frame.
"""
import importlib.util
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

spec = importlib.util.spec_from_file_location("base", "04_render.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

K, W, H, FPS = base.K, base.W, base.H, base.FPS
txt, paste, paste_px, sdraw = base.txt, base.paste, base.paste_px, base.sdraw
CREAM, GOLD, TEAL, MUTED = base.CREAM, base.GOLD, base.TEAL, base.MUTED
FF = base.FF

# ---------------------------------------------------------------- timeline
TITLE = (0.0, 5.4)
INTRO = (5.4, 20.2)
F1 = (20.2, 31.4)
F2 = (31.4, 42.5)
DUAL = (42.5, 82.5)
OUTRO = (82.5, 87.9)
DUR = OUTRO[1]
NFRAMES = int(DUR * FPS)

SCENES = [("title", *TITLE), ("intro", *INTRO), ("f1", *F1),
          ("f2", *F2), ("dual", *DUAL), ("outro", *OUTRO)]

# voice-over offsets inside the 40 s dual scene
VO = {"d1": 0.5, "d2": 4.2, "d3": 10.4, "d4": 14.7,
      "d5": 22.4, "d6": 26.3, "d7": 31.0, "d8": 36.6}

# footage windows (scene-local seconds)
PC1 = (3.7, 13.6)      # chat on desktop
PC2 = (13.6, 22.5)     # quiz + analysis on desktop
PH1 = (22.5, 29.2)     # chat + quiz entry on phone
PH2 = (29.2, 36.3)     # quiz + article on phone

FOOT = {
    "d1": ("assets/footage/d1", 262),
    "d2": ("assets/footage/d2", 223),
    "p1": ("assets/footage/p1", 169),
    "p2": ("assets/footage/p2", 178),
}
_foot_cache = {}


def foot_frame(name, idx):
    idx = max(0, min(FOOT[name][1] - 1, int(idx)))
    key = (name, idx)
    im = _foot_cache.get(key)
    if im is None:
        im = Image.open(f"{FOOT[name][0]}/{idx + 1:04d}.jpg").convert("RGB")
        if len(_foot_cache) > 60:
            _foot_cache.clear()
        _foot_cache[key] = im
    return im


def footage_pc(t):
    """Desktop screen: keep PC footage even while the phone is in focus."""
    if t < PC1[1]:
        idx = (t - PC1[0]) / (PC1[1] - PC1[0]) * (FOOT["d1"][1] - 1)
        return foot_frame("d1", idx)
    if t < PC2[0] + 0.3:
        k = (t - PC1[1]) / 0.3
        a = foot_frame("d1", FOOT["d1"][1] - 1)
        b = foot_frame("d2", 0)
        return Image.blend(a, b, base.smooth(k))
    idx = (t - PC2[0]) / (PC2[1] - PC2[0]) * (FOOT["d2"][1] - 1)
    return foot_frame("d2", idx)


def footage_ph(t):
    """Phone screen."""
    if t < PH1[1]:
        idx = (t - PH1[0]) / (PH1[1] - PH1[0]) * (FOOT["p1"][1] - 1)
        return foot_frame("p1", idx)
    if t < PH2[0] + 0.3:
        k = (t - PH1[1]) / 0.3
        a = foot_frame("p1", FOOT["p1"][1] - 1)
        b = foot_frame("p2", 0)
        return Image.blend(a, b, base.smooth(k))
    idx = (t - PH2[0]) / (PH2[1] - PH2[0]) * (FOOT["p2"][1] - 1)
    return foot_frame("p2", idx)


def focus_weights(t):
    """(pc, phone) focus weight, 0..1, with soft transitions."""
    if t < 3.6:
        return 0.0, 0.0
    if t < 4.2:
        k = base.smooth((t - 3.6) / 0.6)
        return k, 0.0
    if t < 22.2:
        return 1.0, 0.0
    if t < 22.9:
        k = base.smooth((t - 22.2) / 0.7)
        return 1.0 - k, k
    if t < 36.0:
        return 0.0, 1.0
    if t < 36.8:
        k = base.smooth((t - 36.0) / 0.8)
        return 0.0, 1.0 - k
    return 0.0, 0.0


# ---------------------------------------------------------------- devices
MS_W, MS_H = 420, 247          # monitor screen, design px
MS_X, MS_Y = 28, 216           # bezel top-left
BEZ, CHIN = 14, 22
MON_W, MON_H = MS_W + 2 * BEZ, MS_H + 2 * BEZ + CHIN + 34
MON_CX, MON_CY = MS_X + MON_W / 2, MS_Y + MON_H / 2

PH_W, PH_H = 176, 392
PH_X, PH_Y = 996, 164
PBEZ, PTOP, PBOT = 10, 15, 17
PHN_W, PHN_H = PH_W + 2 * PBEZ, PH_H + PTOP + PBOT
PHN_CX, PHN_CY = PH_X + PHN_W / 2, PH_Y + PHN_H / 2


def grade_screen(im, size, bright, sat):
    im = im.resize(size, Image.LANCZOS)
    if bright < 0.995:
        im = ImageEnhance.Brightness(im).enhance(bright)
    if sat < 0.995:
        im = ImageEnhance.Color(im).enhance(sat)
    return im


def build_monitor(foot, bright, sat, active):
    w, h = int(MS_W * K), int(MS_H * K)
    bw, bh = int(BEZ * K), int(CHIN * K)
    Wd, Hd = w + 2 * bw, int(MON_H * K)
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, Wd - 1, Hd - 1], radius=int(13 * K),
                        fill=(22, 22, 24, 255), outline=(255, 255, 255, 26),
                        width=max(1, int(K)))
    sc = grade_screen(foot, (w, h), bright, sat)
    if bright < 0.995:
        ov = Image.new("RGBA", (w, h), (6, 8, 10, int((1 - bright) * 120)))
        sc = sc.convert("RGBA")
        sc.alpha_composite(ov)
    mask = base.rounded_mask((w, h), int(4 * K))
    im.paste(sc, (bw, bw), mask)
    # inner shadow line + subtle glass reflection
    d.rounded_rectangle([bw - 1, bw - 1, bw + w, bw + h], radius=int(5 * K),
                        outline=(0, 0, 0, 110), width=max(1, int(1.5 * K)))
    # chin + stand
    cy = bw + h
    d.rounded_rectangle([Wd / 2 - int(52 * K), cy + int(2 * K), Wd / 2 + int(52 * K), cy + int(8 * K)],
                        radius=int(3 * K), fill=(38, 38, 40, 255))
    d.rectangle([Wd / 2 - int(15 * K), cy + int(6 * K), Wd / 2 + int(15 * K), cy + int(24 * K)],
                fill=(30, 30, 32, 255))
    d.rounded_rectangle([Wd / 2 - int(80 * K), cy + int(22 * K), Wd / 2 + int(80 * K), cy + int(30 * K)],
                        radius=int(4 * K), fill=(36, 36, 38, 255))
    if active > 0.01:
        d.rounded_rectangle([1, 1, Wd - 2, Hd - 2], radius=int(13 * K),
                            outline=(232, 168, 124, int(110 * active)), width=max(1, int(2 * K)))
        d.ellipse([int(10 * K), int(10 * K), int(16 * K), int(16 * K)],
                  fill=(127, 220, 180, int(220 * active)))
    return im


def build_phone(foot, bright, sat, active):
    w, h = int(PH_W * K), int(PH_H * K)
    l, t, b = int(PBEZ * K), int(PTOP * K), int(PBOT * K)
    Wd, Hd = w + 2 * l, h + t + b
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, Wd - 1, Hd - 1], radius=int(28 * K),
                        fill=(26, 26, 28, 255), outline=(232, 168, 124, 70),
                        width=max(1, int(1.5 * K)))
    sc = grade_screen(foot, (w, h), bright, sat)
    if bright < 0.995:
        ov = Image.new("RGBA", (w, h), (6, 8, 10, int((1 - bright) * 120)))
        sc = sc.convert("RGBA")
        sc.alpha_composite(ov)
    mask = base.rounded_mask((w, h), int(16 * K))
    im.paste(sc, (l, t), mask)
    d.rounded_rectangle([l - 1, t - 1, l + w, t + h], radius=int(17 * K),
                        outline=(0, 0, 0, 120), width=max(1, int(1.2 * K)))
    # notch
    d.rounded_rectangle([Wd / 2 - int(24 * K), t + int(5 * K), Wd / 2 + int(24 * K), t + int(11 * K)],
                        radius=int(3 * K), fill=(10, 10, 12, 255))
    # side button
    d.rounded_rectangle([Wd - int(2 * K), int(96 * K), Wd, int(128 * K)],
                        radius=int(1.5 * K), fill=(60, 60, 64, 255))
    if active > 0.01:
        d.rounded_rectangle([1, 1, Wd - 2, Hd - 2], radius=int(28 * K),
                            outline=(232, 168, 124, int(120 * active)), width=max(1, int(2.2 * K)))
    return im


def paste_device(canvas, dev, cx, cy, scale, alpha):
    if alpha <= 0.003:
        return
    if abs(scale - 1.0) > 0.002:
        dw, dh = int(dev.width * scale), int(dev.height * scale)
        dev = dev.resize((dw, dh), Image.LANCZOS)
    x = cx * K - dev.width / 2
    y = cy * K - dev.height / 2
    paste_px(canvas, dev, (x, y), alpha)


# pre-built glows / shadows
GLOW_PC = base.radial(int(720 * K), (255, 192, 130, 70), 2.0)
GLOW_PH = base.radial(int(560 * K), (255, 192, 130, 70), 2.0)
HALO = base.radial(int(760 * K), (255, 196, 140, 62), 2.2)
SHADOW_PC = base.shadow_ellipse(430, 34)
SHADOW_PH = base.shadow_ellipse(190, 24)


def label_pill(text, active, icon_kind):
    size = 15
    im_t = txt(text, size, CREAM if active else (214, 208, 197, 200), True, 0.5)
    h = int(30 * K)
    w = im_t.width + int(46 * K)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if active:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(15 * K),
                            fill=(232, 168, 124, 34), outline=(232, 168, 124, 170),
                            width=max(1, int(1.2 * K)))
    else:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(15 * K),
                            fill=(14, 14, 13, 150), outline=(255, 255, 255, 40),
                            width=max(1, int(1.2 * K)))
    # icon
    ix, iy = int(13 * K), h // 2
    col = GOLD if active else (150, 148, 142, 220)
    if icon_kind == "pc":
        d.rounded_rectangle([ix - int(7 * K), iy - int(6 * K), ix + int(7 * K), iy + int(4 * K)],
                            radius=int(2 * K), outline=col, width=max(1, int(1.2 * K)))
        d.line([(ix, iy + int(4 * K)), (ix, iy + int(7 * K))], fill=col, width=max(1, int(1.2 * K)))
        d.line([(ix - int(4 * K), iy + int(7 * K)), (ix + int(4 * K), iy + int(7 * K))],
               fill=col, width=max(1, int(1.2 * K)))
    else:
        d.rounded_rectangle([ix - int(5 * K), iy - int(8 * K), ix + int(5 * K), iy + int(8 * K)],
                            radius=int(3 * K), outline=col, width=max(1, int(1.2 * K)))
        d.line([(ix, iy + int(5 * K)), (ix, iy + int(6 * K))], fill=col, width=max(1, int(1.2 * K)))
    im.alpha_composite(im_t, (int(28 * K), (h - im_t.height) // 2 + int(1 * K)))
    return im


def callout(kind, lt):
    """Glass callout under the monitor."""
    w, h = int(318 * K), int(60 * K)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(16 * K),
                        fill=(16, 18, 17, 178), outline=(255, 255, 255, 40),
                        width=max(1, int(1.2 * K)))
    ic = base.ICONS["speaker" if kind == "voice" else "quiz"]
    ic = ic.resize((int(30 * K), int(30 * K)), Image.LANCZOS)
    im.alpha_composite(ic, (int(13 * K), int(15 * K)))
    if kind == "voice":
        t1 = "自动朗读 · 晓伊"
        t2 = "逐句读给你听"
    else:
        t1 = "思政闯关 · 5 题/关"
        t2 = "答错展开权威解析"
    im.alpha_composite(txt(t1, 15, CREAM, True, 0.5), (int(54 * K), int(9 * K)))
    im.alpha_composite(txt(t2, 11, (196, 214, 206, 215), False, 0.4), (int(54 * K), int(34 * K)))
    # right side: waveform or progress
    rx = int(250 * K)
    if kind == "voice":
        for i in range(4):
            hh = int((7 + 9 * abs(math.sin(lt * 5.2 + i * 1.3))) * K)
            xx = rx + int(i * 14 * K)
            d.rounded_rectangle([xx, int(30 * K) - hh, xx + int(5 * K), int(30 * K) + hh],
                                radius=int(2.5 * K), fill=(232, 168, 124, 220))
    else:
        for i in range(5):
            on = i < 2
            xx = rx + int(i * 12 * K)
            d.rounded_rectangle([xx, int(26 * K), xx + int(8 * K), int(30 * K)],
                                radius=int(2 * K),
                                fill=(232, 168, 124, 235) if on else (255, 255, 255, 60))
        d.text((rx, int(35 * K)), "01—05", font=base.font(False, 8), fill=(220, 214, 202, 170))
    return im


# ---------------------------------------------------------------- subtitles
DUAL_SUBS = [
    (0.5, 3.8, "电脑端 · 手机端 · 同一个晚晴"),
    (4.2, 6.8, "双击打开，不用装环境"),
    (6.8, 9.6, "不用填密钥，直接开聊"),
    (10.4, 13.5, "回答会一字一句读给你听"),
    (14.7, 17.4, "点开思政闯关，五题一关"),
    (17.4, 20.5, "答错也有解析和权威出处"),
    (22.5, 25.8, "掏出手机，也能找到她"),
    (26.3, 28.3, "课间、排队、通勤，随时问"),
    (28.3, 30.6, "随时答，学习记录同步"),
    (31.0, 34.9, "记录在本机，走到哪学到哪"),
    (36.6, 38.8, "两个端，一个晚晴"),
]


def all_subs():
    subs = [s for s in base.SUBS if s[1] < 42.6 or s[0] > 54.0]
    out = []
    for a, b, text in subs:
        if a >= 54.0:
            a += DUAL[1] - 53.6
            b += DUAL[1] - 53.6
        out.append((a, b, text))
    for a, b, text in DUAL_SUBS:
        out.append((DUAL[0] + a, DUAL[0] + b, text))
    return out


SUBS = all_subs()


def draw_subs(base_im, t):
    active = [s for s in SUBS if s[0] - 0.06 <= t <= s[1]]
    if not active:
        return
    a, b, text = max(active, key=lambda s: s[0])
    k = min(base.smooth((t - a + 0.06) / 0.14), base.smooth((b - t + 0.04) / 0.14), 1.0)
    im = base.sub_img(text)
    paste_px(base_im, im, ((W - im.width) / 2, 638 * K - im.height / 2), k)


# ---------------------------------------------------------------- scene
def scene_dual(lt):
    k = base.clamp(lt / 40.0)
    im = base.bg_frame("classroom", zoom=base.lerp(1.04, 1.10, k), fx=0.5, fy=0.42, blur=6)
    base.darken(im, 0.42)
    im.alpha_composite(base.TOP_GRAD)
    im.alpha_composite(base.BOTTOM_GRAD, (0, H - base.BOTTOM_GRAD.height))

    # warm halo behind the character
    paste(im, HALO, (470, 20), 0.9)

    pcw, phw = focus_weights(lt)
    foot_pc, foot_ph = footage_pc(lt), footage_ph(lt)
    enter = base.ease_out(base.clamp(lt / 0.9))
    alpha = enter

    # focus glows behind devices
    g = GLOW_PC.copy()
    paste(im, g, (MON_CX - 720 / 2, MON_CY - 720 / 2), 0.15 + 0.55 * pcw)
    g = GLOW_PH.copy()
    paste(im, g, (PHN_CX - 560 / 2, PHN_CY - 560 / 2), 0.12 + 0.55 * phw)

    # device shadows
    paste(im, SHADOW_PC, (MON_CX - 215, MON_CY + 164), 0.35 * alpha)
    paste(im, SHADOW_PH, (PHN_CX - 95, PHN_CY + 208), 0.35 * alpha)

    # build screens
    mon = build_monitor(foot_pc, 1.0 - 0.34 * phw, 1.0 - 0.22 * phw, pcw)
    phn = build_phone(foot_ph, 1.0 - 0.32 * pcw, 1.0 - 0.20 * pcw, phw)

    pcs = 1.0 + 0.14 * pcw - 0.08 * phw
    phs = 1.0 + 0.20 * phw - 0.10 * pcw
    paste_device(im, mon, MON_CX + (1 - enter) * -28, MON_CY, pcs, alpha)
    paste_device(im, phn, PHN_CX + (1 - enter) * 30, PHN_CY, phs, alpha)

    # character
    bob = math.sin(lt * 1.5) * 2.2
    shift = 8 * pcw - 6 * phw
    paste(im, base.shadow_ellipse(320, 40), (510 + shift, 688), 0.52 * enter)
    if lt < 36.2:
        base.sprite("talk", 590, 454 + shift, 704, enter, bob, im)
    elif lt < 36.7:
        kk = base.smooth((lt - 36.2) / 0.5)
        base.sprite("talk", 590, 454 + shift, 704, enter * (1 - kk), bob, im)
        base.sprite("wave", 590, 454 + shift, 704, enter * kk, bob, im)
    else:
        base.sprite("wave", 590, 454 + shift, 704, enter, math.sin(lt * 1.8) * 2.0, im)

    base.top_brand(im, 0.86)
    base.part_tag(im, "PART 02 · 双端体验", 0.72)

    # device labels follow the scaled device tops
    outro_a = base.smooth(base.clamp((lt - 36.2) / 0.5))
    lab_a = 0.55 + 0.45 * alpha
    lab_pc = label_pill("电脑端 · 大屏沉浸", pcw, "pc")
    lab_ph = label_pill("手机端 · 随手可用", phw, "ph")
    top_pc = MON_CY - MON_H * pcs / 2
    top_ph = PHN_CY - PHN_H * phs / 2
    paste(im, lab_pc, (MON_CX - lab_pc.width / (2 * K), top_pc - 36), lab_a * (1 - outro_a))
    paste(im, lab_ph, (PHN_CX - lab_ph.width / (2 * K), top_ph - 34), lab_a * (1 - outro_a))

    # voice / quiz callouts
    if 9.8 <= lt <= 13.5:
        a = min(base.smooth((lt - 9.8) / 0.3), base.smooth((13.5 - lt) / 0.3))
        paste(im, callout("voice", lt), (44, 550), a)
    if 14.2 <= lt <= 22.2:
        a = min(base.smooth((lt - 14.2) / 0.3), base.smooth((22.2 - lt) / 0.3))
        paste(im, callout("quiz", lt), (44, 550), a)

    # outro copy, top-left above the monitor
    if lt >= 36.2:
        a2 = base.smooth((lt - 36.2) / 0.5)
        a3 = base.smooth((lt - 36.6) / 0.6)
        paste(im, txt("两个端，一个晚晴", 30, CREAM, True, 1, shadow=2), (76, 114), a2)
        d = sdraw(im)
        if a3 > 0.02:
            d.line([(80, 170), (80 + int(56 * a3), 170)], fill=GOLD, width=3)
        paste(im, txt("电脑端 × 手机端 · 记录同步", 13, (206, 220, 211, 215), False, 0.8),
              (80, 182), a3)
    return base.finish(im)


BASE_RENDERERS = {
    "title": base.scene_title,
    "intro": base.scene_intro,
    "f1": lambda lt: base.scene_feature(lt, base.FEATURES[0]),
    "f2": lambda lt: base.scene_feature(lt, base.FEATURES[1]),
    "outro": base.scene_outro,
}
RENDERERS = dict(BASE_RENDERERS, dual=scene_dual)


def render_frame(t):
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
        kk = base.smooth((t - (start - half)) / (2 * half))
        im = Image.blend(prev, im, kk)
    if idx < len(SCENES) - 1 and end - t < half:
        nname, ns, ne = SCENES[idx + 1]
        nxt = RENDERERS[nname](t - ns)
        kk = base.smooth((t - (end - half)) / (2 * half))
        im = Image.blend(im, nxt, kk)
    draw_subs(im, t)
    if t < 0.45:
        im = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), im, base.smooth(t / 0.45))
    if t > DUR - 0.85:
        im = Image.blend(im, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                         base.smooth((t - (DUR - 0.85)) / 0.85))
    return base.grain(im)


def stills(times):
    os.makedirs("qa/dual", exist_ok=True)
    for t in times:
        render_frame(t).convert("RGB").save(f"qa/dual/t{t:06.2f}.jpg", quality=92)
        print("saved", t, flush=True)


def render_video():
    out = "assets/chapter_v2.mp4"
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
        stills([1.0, 8.0, 25.0, 33.0, 44.6, 48.5, 54.4, 58.0, 61.5, 66.0,
               69.5, 73.0, 76.0, 79.5, 81.5, 84.0])
    else:
        render_video()
