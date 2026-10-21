# 星火同行 Xinghuo Tongxing

AI 角色伴侣便携应用 + 楚晚晴角色 PV 自动化制作流水线。

## 项目构成

### 1. `星火同行_优化版_便携版(1)/` — 便携版 AI 应用

- 本地 Qwen 对话（Ollama 运行时驱动）
- 角色互动 / 知识闯关等玩法
- 免安装，解压即用；内置 TTS 语音包与浏览器运行时组件
- **模型权重（约 3.1GB）随发行包单独提供，未入库**（见 .gitignore）

### 2. `chuwangqing_pv/` — 楚晚晴角色 PV 制作

- 角色设定、剧本提示词、作品集描述
- 自动化流水线脚本：立绘 → TTS → 音频 → 渲染 → 封装
- 素材库：音频 / 实拍 / 背景 / 立绘 / 关键帧，共 913 个文件

### 3. 方案文档（根目录）

- `星火同行_短视频三段式方案.md`
- `星火同行_角色PV_思政创新赛道方案.md`

## Git LFS

本仓库使用 **Git LFS** 管理媒体与二进制文件（`*.jpg` `*.png` `*.wav` `*.mp3` `*.mp4` `*.dll` `*.exe` `*.msix` `*.zip` `*.db` 等）。

克隆前请先安装 git-lfs（https://git-lfs.com/），否则媒体文件将显示为指针文本。

```bash
git clone https://github.com/M4from404/agent.git
cd agent
git lfs pull   # 如克隆时未自动拉取
```

## 大文件说明

| 文件 | 大小 | 处理方式 |
|---|---|---|
| 模型权重 `runtime/models/` | 约 3.1GB | 随便携版发行包提供，不入库 |
| 双端版成片 `楚晚晴_角色PV_2min_1080p_双端版.mp4` | 103MB | 超过 GitHub 单文件上限，通过 Release 附件分发 |

## 技术栈

Python 3.12 便携运行时 · Ollama 本地模型服务 · TTS 语音合成 · 自动化视频渲染流水线
