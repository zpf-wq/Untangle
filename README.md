# 🎵 Untangle

本地音频**分轨** + **转 MIDI** 工具,专为 macOS(Apple Silicon)优化。

- **分轨**:用 Meta 开源的 [Demucs](https://github.com/facebookresearch/demucs)(`htdemucs` 模型)把一首歌分成 4 轨:`drums / bass / vocals / other`
- **转 MIDI**:用 Spotify 开源的 [basic-pitch](https://github.com/spotify/basic-pitch) 把任意一轨(或整首)转成 `.mid`
- **全程本地运行**,不调用任何云端 API
- 自动检测并启用 Apple Silicon 的 **MPS 加速**,不可用时回退 CPU

---

## 1. 环境要求

- macOS,Apple Silicon(M1/M2/M3…)推荐
- **Python 3.10 或 3.11**(⚠️ 不要用 3.12+,basic-pitch 对版本敏感)
- 约 2~3 GB 磁盘空间(依赖 + 模型权重)

---

## 2. 安装

### 方式 A:venv(推荐,无需 conda)

```bash
# 进入项目目录
cd Untangle   # 或你的项目目录

# 用 Python 3.10/3.11 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 升级 pip 并安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 方式 B:conda

```bash
conda create -n noteclaw python=3.11 -y
conda activate noteclaw

pip install --upgrade pip
pip install -r requirements.txt
```

> **关于 basic-pitch 后端**:requirements 默认使用 **onnx** 后端
> (`basic-pitch[onnx]` + `onnxruntime`),在 Apple Silicon 上比 TensorFlow
> 更容易安装。如果你已经装好了 TensorFlow,basic-pitch 也能直接用 TF 后端,
> 无需改动代码——它会自动选择可用后端。

---

## 3. 首次运行会自动下载模型

第一次运行时会自动下载模型权重(之后会缓存,无需重复下载):

| 模型 | 用途 | 大致体积 | 缓存位置 |
|------|------|----------|----------|
| Demucs `htdemucs` | 分轨 | ~80 MB | `~/.cache/torch/hub/` |
| basic-pitch ICASSP 2022 | 转 MIDI | ~20 MB | 随 pip 包一起安装 |

> 如果下载失败,通常是网络问题。重试即可;Demucs 权重托管在 GitHub release 上,
> 必要时可配置代理。

---

## 4. 使用

### 4.1 命令行(CLI)

```bash
# 分轨,并对 other、bass 两轨转 MIDI,输出到 ./out
python cli.py song.mp3 --stems other,bass --output ./out

# 只分轨出全部 4 轨 + 对默认轨道(other)转 MIDI
python cli.py song.mp3 --output ./out

# 不分轨,直接对整首转 MIDI
python cli.py song.mp3 --no-separate --output ./out

# 调参示例:更保守的 onset、限制音高范围
python cli.py song.wav --stems vocals --onset-threshold 0.7 \
    --min-note 48 --max-note 96 --output ./out
```

常用参数:

| 参数 | 说明 | 默认 |
|------|------|------|
| `--stems` | 要转 MIDI 的轨道,逗号分隔 | `other` |
| `--no-separate` | 跳过分轨,直接整首转 MIDI | 关闭 |
| `--output` / `-o` | 输出目录 | `./out` |
| `--onset-threshold` | onset 阈值(0~1,越高越保守) | 0.5 |
| `--frame-threshold` | frame 阈值(0~1) | 0.3 |
| `--min-note` / `--max-note` | 音高范围(MIDI 编号,21=A0,108=C8) | 21 / 108 |

### 4.2 网页界面(Gradio)

```bash
python app.py
```

启动后浏览器打开终端提示的本地地址(默认 `http://127.0.0.1:7860`):

1. 上传音频(wav/mp3/flac/m4a)
2. 勾选「先分轨」并选择要转 MIDI 的轨道(可多选);或取消勾选直接整首转 MIDI
3. 点「开始处理」,等待进度完成
4. 在右侧下载生成的 `.mid` 和分轨 `.wav`

### 4.3 原生 Mac 应用(Swift / SwiftUI)

`macapp/` 下有一个原生 macOS 前端,界面比网页更顺手。它是一个轻量 GUI,
底层通过 `Process` 调用上面装好的 `.venv/bin/python cli.py --json`,
因此**必须先完成第 2 步的 venv 与依赖安装**。

构建(需要 Xcode 命令行工具,已随 Xcode 提供):

```bash
cd macapp
./build_app.sh        # 产出 macapp/Untangle.app
open Untangle.app      # 或在 Finder 里双击
```

使用:

1. 在「项目目录」里确认指向本仓库根目录(默认已填,首次运行会记住)
2. 选择音频文件、输出目录
3. 勾选是否分轨、选择要转 MIDI 的轨道(或关闭分轨整首转)
4. 「高级参数」可调 onset/frame 阈值与音高范围
5. 点「开始处理」,下方有进度条;完成后每个产物都能「在 Finder 中显示」

> 首次打开 .app 若被 Gatekeeper 拦截(因是本地 ad-hoc 签名),
> 在「系统设置 → 隐私与安全性」里点「仍要打开」,或右键 →「打开」。

### 4.4 作为库调用

```python
from pipeline import process

result = process(
    input_path="song.mp3",
    stems_to_convert=["other", "bass"],
    output_dir="./out",
    separate_first=True,
)
print(result["stems"])  # {"drums": "...", "bass": "...", ...}
print(result["midis"])  # {"other": "..._other.mid", "bass": "..._bass.mid"}
```

---

## 5. 项目结构

```
device_utils.py   # 设备检测(MPS / CUDA / CPU)
separate.py       # 分轨模块(Demucs:get_model + apply_model)
to_midi.py        # 转 MIDI 模块(basic-pitch)
pipeline.py       # 整合流程
cli.py            # 命令行入口(--json 供 GUI 调用)
app.py            # Gradio 网页界面
requirements.txt
README.md
macapp/           # 原生 Mac 前端(SwiftUI)
  Package.swift
  Sources/Untangle/*.swift
  build_app.sh    # 构建 Untangle.app
```

---

## 6. 性能与注意事项

- 分轨是计算密集型任务。一首 3~4 分钟的歌在 M3 Pro 上大约需要
  **几十秒到一两分钟**,属正常现象。
- Demucs 输出采样率为 44100Hz;basic-pitch 内部会自动重采样到 22050Hz,
  因此无需手动重采样。
- 生成的 `.mid` 可直接在 GarageBand / Logic / Ableton 等 DAW 中打开。

---

## 7. 常见问题

- **`torch` MPS 不可用**:确认是 Apple Silicon 且 torch ≥ 2.2;否则会自动回退 CPU(更慢但能用)。
- **basic-pitch 安装失败**:确认 Python 是 3.10/3.11;onnx 后端通常最易装。
- **找不到模型 / 下载超时**:多为网络问题,重试或配置代理。
- **MIDI 音符太多/太杂**:调高 `--onset-threshold` 和 `--frame-threshold`,或缩小音高范围。
