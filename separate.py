"""分轨模块。

使用 Demucs 的 htdemucs 模型,把输入音频分成 4 轨:
drums / bass / vocals / other,并把每一轨存成独立的 WAV 文件。
"""

from __future__ import annotations

import os
from pathlib import Path

from device_utils import get_torch_device

# Demucs 默认输出采样率
DEMUCS_SAMPLE_RATE = 44100

# htdemucs 模型输出的 4 个轨道名
STEM_NAMES = ("drums", "bass", "vocals", "other")

# 支持的输入音频后缀
SUPPORTED_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff", ".aif"}


def separate(
    input_path: str,
    output_dir: str,
    model_name: str = "htdemucs",
    progress=None,
) -> dict[str, str]:
    """对输入音频做乐器分轨。

    Args:
        input_path: 输入音频文件路径(wav/mp3/flac/m4a 等)。
        output_dir: 输出目录,分轨后的 WAV 会写入此目录下的子文件夹。
        model_name: Demucs 模型名,默认 ``htdemucs``(4 轨)。
        progress: 可选的进度回调,签名为 ``progress(fraction, desc)``,
            兼容 gradio 的 ``gr.Progress``。

    Returns:
        dict[str, str]: ``{轨道名: wav 文件路径}``,例如
            ``{"drums": ".../drums.wav", "bass": ".../bass.wav", ...}``。

    Raises:
        FileNotFoundError: 输入文件不存在。
        ValueError: 输入文件格式不受支持。
        RuntimeError: 模型加载或分轨过程出错(含模型下载失败)。
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"输入音频文件不存在:{input_path}")
    if src.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的音频格式:{src.suffix}。"
            f"支持的格式:{', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    out_root = Path(output_dir)
    # 每个输入单独建一个以文件名命名的子目录,避免多次运行互相覆盖
    stem_dir = out_root / f"{src.stem}_stems"
    stem_dir.mkdir(parents=True, exist_ok=True)

    device = get_torch_device()
    if progress is not None:
        progress(0.0, desc=f"加载 Demucs 模型({model_name},设备:{device})…")

    # 延迟导入,避免未装依赖时 import 整个模块即报错。
    # 注意:PyPI 上的 demucs 4.0.1 不含 demucs.api 便捷封装,
    # 这里直接用更底层、跨版本更稳定的 get_model + apply_model。
    try:
        import librosa
        import numpy as np
        import soundfile as sf
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
    except ImportError as exc:
        raise RuntimeError(
            "未检测到 demucs(或 torch),请先安装依赖:pip install -r requirements.txt"
        ) from exc

    try:
        # 首次运行会自动下载模型权重(htdemucs 约 ~80MB),之后走本地缓存
        model = get_model(model_name)
        model.eval()
    except Exception as exc:  # noqa: BLE001 - 统一包装成清晰报错
        raise RuntimeError(
            f"加载 Demucs 模型失败(可能是模型下载失败或网络问题):{exc}"
        ) from exc

    samplerate = getattr(model, "samplerate", DEMUCS_SAMPLE_RATE)

    if progress is not None:
        progress(0.2, desc="读取并重采样音频…")

    try:
        # 用 librosa 读取并重采样到模型要求的采样率(避开 torchaudio 对 torchcodec 的依赖)。
        # mono=False 时:单声道返回 (time,),多声道返回 (channels, time)。
        audio, _ = librosa.load(str(src), sr=samplerate, mono=False)
        if audio.ndim == 1:
            audio = audio[np.newaxis, :]  # (1, time)
        # 统一到模型需要的声道数(htdemucs 为 2):单声道复制成双声道
        if audio.shape[0] == 1 and model.audio_channels > 1:
            audio = np.repeat(audio, model.audio_channels, axis=0)
        elif audio.shape[0] > model.audio_channels:
            audio = audio[: model.audio_channels]
        wav = torch.from_numpy(np.ascontiguousarray(audio)).float()

        # 标准 demucs 归一化:减均值、除标准差,提升分轨质量
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        wav = (wav - mean) / std

        if progress is not None:
            progress(0.3, desc=f"正在分轨(设备:{device},耗时较长)…")

        with torch.no_grad():
            # apply_model 期望 [batch, channels, time];返回 [batch, sources, channels, time]
            sources = apply_model(
                model, wav[None], device=device, progress=False
            )[0]
        # 反归一化还原音量
        sources = sources * std + mean
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"分轨过程出错:{exc}") from exc

    results: dict[str, str] = {}
    total = len(model.sources)
    for i, (stem_name, source) in enumerate(zip(model.sources, sources)):
        if progress is not None:
            progress(
                0.6 + 0.4 * (i / max(total, 1)),
                desc=f"写入轨道:{stem_name}",
            )
        out_path = stem_dir / f"{stem_name}.wav"
        # source 形状 [channels, time];soundfile 需要 [time, channels]
        data = source.detach().cpu().numpy().T
        sf.write(str(out_path), data, samplerate)
        results[stem_name] = str(out_path)

    if progress is not None:
        progress(1.0, desc="分轨完成")

    return results


if __name__ == "__main__":  # 简单自测
    import sys

    if len(sys.argv) < 2:
        print("用法:python separate.py <音频路径> [输出目录]")
        raise SystemExit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "./out"
    paths = separate(sys.argv[1], out)
    for name, p in paths.items():
        print(f"{name}: {p}")
