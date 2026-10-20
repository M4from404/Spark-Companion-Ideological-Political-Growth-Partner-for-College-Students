# -*- coding: utf-8 -*-
"""Join the reference scene and the new character/feature chapter, then mux the master audio."""
import os
import subprocess

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
REF = "C:/Users/liuso/Desktop/WeChat_20261017191432.mp4"
CHAPTER = "assets/chapter.mp4"
AUDIO = "assets/audio/master.wav"
OUT = "楚晚晴_角色PV_2min.mp4"

cmd = [
    FF, "-y", "-hide_banner", "-loglevel", "error",
    "-i", REF, "-i", CHAPTER, "-i", AUDIO,
    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
    "-map", "[v]", "-map", "2:a",
    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
    "-profile:v", "high", "-r", "24",
    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
    "-shortest", "-movflags", "+faststart", OUT,
]
subprocess.run(cmd, check=True)
print("output", OUT, os.path.getsize(OUT) / 1e6, "MB")
