# -*- coding: utf-8 -*-
"""Generate 楚晚晴 voice-over with the product's 晓伊 (Xiaoyi) voice,
trim silence, and capture word-level timings for subtitles."""
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
    "hook": "那么，楚晚晴，是谁？",
    "intro": "你好，我是楚晚晴，二十二岁，你的大学思政辅导员。比起给你标准答案，我更想先听你把话说完。学业、情感、成长，都可以来找我聊。",
    "f1": "第一，随时在线的对话陪伴。学业、科研、人际的烦恼，都可以慢慢说，我会陪你一起找到下一步。",
    "f2": "第二，思政知识闯关。三关十五题，答对四题解锁下一关，让理论学习，也变成一场闯关。",
    "f3": "第三，甜声语音朗读。晓伊的声音，像学姐在耳边说话。完全离线运行，数据不出本机。",
    "outro": "星火同行，陪你一起长大。",
}

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = "assets/audio/vo"
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
    # trim leading/trailing silence
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
