# -*- coding: utf-8 -*-
"""Voice-over for the new dual-end (PC + mobile) segment, same Xiaoyi voice."""
import asyncio
import json
import os
import subprocess
import wave

import edge_tts
import imageio_ffmpeg
import numpy as np

VOICE = "zh-CN-XiaoyiNeural"
RATE = "-6%"
PITCH = "-2Hz"

LINES = {
    "d1": "电脑端，手机端，都是同一个晚晴。",
    "d2": "在电脑上，双击就能打开。不用装环境，也不用填密钥。",
    "d3": "她会把回答，一字一句读给你听。",
    "d4": "点开思政闯关，五道题一关。答错也有解析和权威出处。",
    "d5": "出门在外，掏出手机，也能找到她。",
    "d6": "课间、排队、通勤，随时问，随时答。",
    "d7": "学习记录保存在本机，走到哪，学到哪。",
    "d8": "两个端，一个晚晴。",
}

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = "assets/audio/vo_dual"
os.makedirs(OUT, exist_ok=True)


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return sr, a


def write_wav(path, sr, a):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())


async def synth(key, text):
    mp3 = f"{OUT}/{key}.mp3"
    raw = f"{OUT}/{key}_raw.wav"
    wav = f"{OUT}/{key}.wav"
    words = []
    with open(mp3, "wb") as f:
        async for chunk in edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH).stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                words.append({
                    "t": chunk["offset"] / 1e7,
                    "d": chunk["duration"] / 1e7,
                    "text": chunk["text"],
                })
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "1",
                    "-sample_fmt", "s16", raw], check=True)
    sr, a = read_wav(raw)
    env = np.abs(a)
    live = np.where(env > 0.012)[0]
    if len(live):
        start = max(0, live[0] - int(0.06 * sr))
        end = min(len(a), live[-1] + int(0.10 * sr))
    else:
        start, end = 0, len(a)
    trimmed = a[start:end]
    write_wav(wav, sr, trimmed)
    t0 = start / sr
    for w in words:
        w["t"] = round(max(0.0, w["t"] - t0), 3)
    info = {"duration": round(len(trimmed) / sr, 3), "words": words, "text": text}
    with open(f"{OUT}/{key}.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return info


async def main():
    meta = {}
    for key, text in LINES.items():
        info = await synth(key, text)
        meta[key] = info
        print(key, info["duration"], len(info["words"]))
    with open(f"{OUT}/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
