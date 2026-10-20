# -*- coding: utf-8 -*-
"""Clean the reference opening clip before it is joined to the chapter.

1) Remove the "星光同行" label above the chat bubble (2.54 - 9.12 s).
2) Replace the broken laptop screen with the back of the lid (37.36 - 43.08 s).
   The original cross-dissolve at 38.8-39.2 is rebuilt from two cleaned
   endpoint frames so no raw screen leaks through the blend.

Output: assets/ref_clean.mp4  (1280x720, 24 fps, no audio)
"""
import os
import subprocess
import sys

import cv2
import numpy as np

SRC = "C:/Users/liuso/Desktop/WeChat_20261017191432.mp4"
OUT = "assets/ref_clean.mp4"
W, H, FPS = 1280, 720, 24
N = 1623                    # 67.63 s * 24 fps
FF = "C:/Users/liuso/AppData/Roaming/Python/Python314/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"

# ---------------------------------------------------------------- textures
def lid_texture(w=520, h=820, logo=True):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h
    base = 50 - 27 * v
    d = u * 0.55 + v * 0.85
    sheen = np.exp(-((d - 0.92) ** 2) / (2 * 0.14 ** 2)) * 20
    rng = np.random.default_rng(4)
    noise = cv2.GaussianBlur(rng.normal(0, 1.1, (h, w)).astype(np.float32), (1, 5), 0)
    img = np.stack([base + sheen + noise * 1.3,
                    base + sheen * 0.98 + noise * 1.2,
                    base + sheen * 0.95 + noise * 1.1], -1)
    img[..., 2] += 3
    img[..., 1] += 1
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (92, 94, 99), 2)
    if logo:
        cx, cy = w // 2, int(h * 0.5)
        r = 30
        cv2.circle(img, (cx, cy), r, (60, 62, 67), 3, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), r - 4, (30, 31, 35), 2, cv2.LINE_AA)
        for ang in (0, 90):
            a = np.deg2rad(ang)
            dx, dy = np.cos(a) * 18, np.sin(a) * 18
            cv2.line(img, (int(cx - dx), int(cy - dy)), (int(cx + dx), int(cy + dy)),
                     (70, 72, 77), 3, cv2.LINE_AA)
    return np.clip(img, 0, 255).astype(np.uint8)


TEX_LOGO = lid_texture(logo=True)
TEX_PLAIN = lid_texture(logo=False)

# ---------------------------------------------------------------- laptop quads
# (time, [TL, TR, BR, BL]) in source pixels
WIDE = [
    (37.34, [(0, 392), (270, 400), (302, 640), (0, 620)]),
    (37.80, [(0, 398), (296, 424), (310, 636), (0, 618)]),
    (38.20, [(0, 402), (298, 428), (312, 638), (0, 620)]),
    (38.80, [(0, 408), (300, 434), (316, 642), (0, 624)]),
]
CLOSE = [
    (39.40, [(16, 306), (170, 312), (252, 718), (12, 718)]),
    (39.70, [(0, 306), (152, 314), (238, 720), (0, 720)]),
    (40.00, [(0, 306), (132, 316), (215, 720), (0, 720)]),
    (40.30, [(0, 312), (122, 322), (205, 720), (0, 720)]),
    (40.60, [(0, 320), (115, 328), (195, 720), (0, 720)]),
    (41.00, [(0, 335), (105, 342), (185, 720), (0, 720)]),
    (41.40, [(0, 370), (100, 375), (175, 720), (0, 720)]),
    (41.80, [(0, 385), (95, 390), (160, 720), (0, 720)]),
    (42.00, [(0, 415), (105, 425), (168, 720), (0, 720)]),
    (42.30, [(0, 440), (68, 450), (105, 720), (0, 720)]),
    (42.60, [(0, 480), (35, 490), (52, 720), (0, 720)]),
    (42.90, [(0, 665), (12, 672), (16, 720), (0, 720)]),
    (43.08, [(0, 700), (2, 700), (2, 720), (0, 720)]),
]


def quad_at(keys, t):
    if t <= keys[0][0]:
        return np.array(keys[0][1], np.float32)
    if t >= keys[-1][0]:
        return np.array(keys[-1][1], np.float32)
    for i in range(len(keys) - 1):
        t0, p0 = keys[i]
        t1, p1 = keys[i + 1]
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0)
            return (np.array(p0, np.float32) * (1 - k) +
                    np.array(p1, np.float32) * k)
    return np.array(keys[-1][1], np.float32)


def apply_cover(frame, pts, tex, alpha=1.0):
    th, tw = tex.shape[:2]
    src = np.float32([[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]])
    M = cv2.getPerspectiveTransform(src, pts.astype(np.float32))
    warp = cv2.warpPerspective(tex, M, (W, H), flags=cv2.INTER_LANCZOS4)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 255)
    mask = cv2.GaussianBlur(mask, (5, 5), 0).astype(np.float32)[..., None] / 255
    mask *= alpha
    out = frame.astype(np.float32) * (1 - mask) + warp.astype(np.float32) * mask
    return np.clip(out, 0, 255).astype(np.uint8)


def clean_laptop(frame, t):
    if t < 38.80:
        pts = quad_at(WIDE, t)
        return apply_cover(frame, pts, TEX_LOGO)
    if t < 39.40:
        return None                      # handled by the rebuilt dissolve
    pts = quad_at(CLOSE, t)
    alpha = 1.0
    if t > 42.96:
        alpha = max(0.0, 1.0 - (t - 42.96) / 0.14)
    return apply_cover(frame, pts, TEX_PLAIN, alpha)


# ---------------------------------------------------------------- label
def clean_label(frame, t):
    if not (2.54 <= t <= 9.12):
        return frame
    x0, y0, x1, y1 = 78, 546, 192, 587
    roi = frame[y0:y1, x0:x1].copy()
    mask = np.zeros(roi.shape[:2], np.uint8)
    mask[6:39, 4:114] = 255
    fixed = cv2.inpaint(roi, mask, 8, cv2.INPAINT_TELEA)
    frame = frame.copy()
    frame[y0:y1, x0:x1] = fixed
    return frame


def smooth(k):
    k = min(max(k, 0.0), 1.0)
    return k * k * (3 - 2 * k)


def process(frame, t):
    frame = clean_label(frame, t)
    if 37.34 <= t < 38.80:
        frame = clean_laptop(frame, t)
    elif 38.80 <= t < 39.40:
        a = smooth((t - 38.80) / 0.60)
        w = clean_laptop(frame, 38.799) if False else apply_cover(frame, quad_at(WIDE, 38.80), TEX_LOGO)
        c = apply_cover(frame, quad_at(CLOSE, 39.40), TEX_PLAIN)
        frame = cv2.addWeighted(w, 1 - a, c, a, 0)
    elif 39.40 <= t <= 43.10:
        frame = clean_laptop(frame, t)
    return frame


def stills(times):
    os.makedirs("qa/fix/clean", exist_ok=True)
    cap = cv2.VideoCapture(SRC)
    for t in times:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * FPS)))
        ok, fr = cap.read()
        if not ok:
            continue
        out = process(fr, t)
        cv2.imwrite(f"qa/fix/clean/c{t:06.2f}.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 95])
        print("saved", t, flush=True)


def render():
    cmd = [FF, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16",
           "-pix_fmt", "yuv420p", "-profile:v", "high", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cap = cv2.VideoCapture(SRC)
    for i in range(N):
        ok, fr = cap.read()
        if not ok:
            break
        t = i / FPS
        proc.stdin.write(process(fr, t).tobytes())
        if i % 120 == 0:
            print(f"frame {i}/{N}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("encoded", OUT, os.path.getsize(OUT) / 1e6, "MB")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stills":
        stills([1.0, 3.0, 5.0, 7.0, 9.0, 37.6, 38.0, 38.4, 38.7, 38.9,
                39.1, 39.3, 39.5, 39.9, 40.3, 40.7, 41.1, 41.5, 41.9,
                42.2, 42.5, 42.8, 43.0])
    else:
        render()
