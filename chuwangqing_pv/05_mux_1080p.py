# -*- coding: utf-8 -*-
"""Join the reference scene (upscaled to 1080p) and the native 1080p chapter, then mux audio."""
import os
import subprocess

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
REF = "C:/Users/liuso/Desktop/WeChat_20261017191432.mp4"
CHAPTER = "assets/chapter.mp4"
AUDIO = "assets/audio/master.wav"
OUT = "楚晚晴_角色PV_2min_1080p.mp4"

cmd = [
    FF, "-y", "-hide_banner", "-loglevel", "error",
    "-i", REF, "-i", CHAPTER, "-i", AUDIO,
    "-filter_complex",
    # Part 1 is only available at 720p: lanczos + light sharpen, then unify timing.
    "[0:v]scale=1920:1080:flags=lanczos+accurate_rnd+full_chroma_int,"
    "setsar=1,fps=24,unsharp=5:5:0.35:5:5:0.0[v0];"
    "[1:v]scale=1920:1080:flags=lanczos,setsar=1,fps=24[v1];"
    "[v0][v1]concat=n=2:v=1:a=0[v]",
    "-map", "[v]", "-map", "2:a",
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
    "-profile:v", "high", "-level", "4.1", "-r", "24",
    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
    "-shortest", "-movflags", "+faststart", OUT,
]
subprocess.run(cmd, check=True)
print("output", OUT, os.path.getsize(OUT) / 1e6, "MB")
