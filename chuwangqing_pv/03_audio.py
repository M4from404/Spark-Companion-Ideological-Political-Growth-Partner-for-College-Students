# -*- coding: utf-8 -*-
"""Synthesize a soft piano/pad bed + build the master audio track."""
import json
import subprocess
import wave

import numpy as np
from scipy.signal import fftconvolve

SR = 44100
CHAPTER = 59.0
REF = 67.593
FF = __import__("imageio_ffmpeg").get_ffmpeg_exe()
rng = np.random.default_rng(7)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def piano(freq, dur, amp=0.06):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.exp(-t / 0.95) * np.minimum(1, t / 0.008)
    y = (np.sin(2 * np.pi * freq * t)
         + 0.32 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / 0.45)
         + 0.10 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / 0.25))
    return amp * env * y


def pad(freq, dur, amp=0.018):
    n = int(dur * SR)
    t = np.arange(n) / SR
    a = np.minimum(1, t / 2.2)
    r = np.minimum(1, np.maximum(0, (dur - t) / 2.4))
    env = a * r
    vib = 1 + 0.0015 * np.sin(2 * np.pi * 0.13 * t)
    y = (np.sin(2 * np.pi * freq * vib * t)
         + 0.4 * np.sin(2 * np.pi * freq * 2.001 * t)
         + 0.15 * np.sin(2 * np.pi * freq * 3.002 * t))
    return amp * env * y


def add(buf, sig, at, pan=0.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    l = np.sqrt((1 - pan) / 2)
    r = np.sqrt((1 + pan) / 2)
    buf[i:i + len(sig), 0] += sig * l
    buf[i:i + len(sig), 1] += sig * r


def build_music():
    dur = CHAPTER
    buf = np.zeros((int(dur * SR), 2), np.float32)
    # Fmaj7 | C/E | Dm7 | Bbmaj7
    chords = [
        [53, 57, 60, 64],   # F A C E
        [52, 55, 60, 64],   # E G C E
        [50, 53, 57, 60],   # D F A C
        [46, 50, 53, 57],   # Bb D F A
    ]
    chord_len = 4.0
    arp_step = 0.55
    t = 0.0
    ci = 0
    while t < dur - 2:
        ch = chords[ci % 4]
        # pad + bass
        for j, n in enumerate(ch):
            add(buf, pad(midi(n + 12), chord_len + 2.0, 0.010 if j else 0.013), t, pan=(-0.35 + 0.12 * j))
        add(buf, piano(midi(ch[0] - 12), 3.6, 0.055), t, pan=0.0)
        # arpeggio
        pattern = [0, 1, 2, 3, 2, 1]
        k = 0
        while k * arp_step < chord_len - 0.1:
            n = ch[pattern[k % len(pattern)]] + 12
            add(buf, piano(midi(n), 2.1, 0.048), t + k * arp_step,
                pan=-0.3 + 0.16 * (k % 3))
            k += 1
        # sparse melody
        if ci % 2 == 1:
            add(buf, piano(midi(ch[3] + 12), 2.8, 0.05), t + 1.7, pan=0.25)
        if ci % 4 == 3:
            add(buf, piano(midi(ch[2] + 24), 3.0, 0.032), t + 2.9, pan=0.35)
        t += chord_len
        ci += 1

    # airy reverb
    ir_len = int(1.6 * SR)
    tt = np.arange(ir_len) / SR
    ir = rng.normal(0, 1, ir_len) * np.exp(-tt / 0.55)
    ir[:400] *= np.linspace(0, 1, 400)
    ir /= np.sqrt((ir ** 2).sum())
    wet = np.stack([fftconvolve(buf[:, 0], ir)[: len(buf)],
                    fftconvolve(buf[:, 1], ir)[: len(buf)]], axis=1)
    music = buf + 0.38 * wet
    # gentle fades
    n = len(music)
    fade_in = int(1.4 * SR)
    music[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    fade_out = int(3.4 * SR)
    music[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    music /= max(1e-9, np.abs(music).max())
    music *= 0.26
    return music


def build_swell():
    dur = 2.2
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = np.exp(-((freqs - 900) ** 2) / (2 * 500 ** 2))
    noise = np.fft.irfft(spec * band, n)
    noise /= max(1e-9, np.abs(noise).max())
    env = (t / dur) ** 2.2 * np.minimum(1, (dur - t) / 0.25)
    swell = noise * env * 0.16
    return np.stack([swell, np.roll(swell, 37)], axis=1)


def read_ref():
    subprocess.run([FF, "-y", "-loglevel", "error", "-i",
                    "C:/Users/liuso/Desktop/WeChat_20261017191432.mp4",
                    "-vn", "-ar", "44100", "-ac", "2", "-sample_fmt", "s16",
                    "ref/ref_audio.wav"], check=True)
    with wave.open("ref/ref_audio.wav", "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        a = a.reshape(-1, 2)
    return a


def read_vo(key):
    with wave.open(f"assets/audio/vo/{key}.wav", "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def main():
    meta = json.load(open("assets/audio/vo/meta.json", encoding="utf-8"))
    starts = {"hook": 1.5, "intro": 6.0, "f1": 20.5, "f2": 31.7, "f3": 42.8, "outro": 54.4}

    music = build_music()
    n = len(music)
    voice = np.zeros((n, 2), np.float32)
    for key, s in starts.items():
        v = read_vo(key)
        i = int(s * SR)
        seg = v[: max(0, n - i)]
        voice[i:i + len(seg), 0] += seg
        voice[i:i + len(seg), 1] += seg
        print(f"{key}: {s:.2f} - {s + meta[key]['duration']:.2f}")

    # duck the music under the voice
    env = np.abs(voice).mean(axis=1)
    win = int(0.12 * SR)
    env = np.convolve(env, np.ones(win) / win, mode="same")
    duck = 1.0 - 0.5 * np.clip(env / 0.08, 0, 1)
    duck = np.convolve(duck, np.ones(int(0.3 * SR)) / int(0.3 * SR), mode="same")
    music *= duck[:, None]

    voice *= 1.35
    chapter = music + voice
    chapter = chapter[: int(CHAPTER * SR)]
    chapter *= 1.10
    swell = build_swell()
    chapter[: len(swell)] += swell
    # soften the very start
    chapter[: int(0.25 * SR)] *= np.linspace(0, 1, int(0.25 * SR))[:, None]

    ref = read_ref()
    ref_end = int(REF * SR)
    ref = ref[:ref_end]
    # fade the reference music tail so the chapter transition feels intentional
    fo = int(0.6 * SR)
    ref[-fo:] *= np.linspace(1, 0, fo)[:, None]
    # small breath before the chapter
    master = np.concatenate([ref, chapter], axis=0)
    # normalize to healthy peak, keep dynamics
    master = np.concatenate([master, np.zeros((int(CHAPTER * SR) - len(chapter), 2), np.float32)]) if len(chapter) < int(CHAPTER * SR) else master
    peak = np.abs(master).max()
    master = master / peak * 0.95
    print("master duration", len(master) / SR, "ref rms", float(np.sqrt((ref ** 2).mean())),
          "chapter rms", float(np.sqrt((chapter ** 2).mean())))
    with wave.open("assets/audio/master.wav", "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(master, -1, 1) * 32767).astype(np.int16).tobytes())
    # save chapter-only mix too (for reference)
    with wave.open("assets/audio/chapter.wav", "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(chapter / max(1e-9, np.abs(chapter).max()) * 0.9, -1, 1) * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    main()
