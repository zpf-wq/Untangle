"""音频转 MIDI 模块。

使用 Spotify 开源的 basic-pitch 把任意 WAV(或其它音频)转成 MIDI。
basic-pitch 内部会自动把音频重采样到模型所需的采样率(22050Hz),
因此 Demucs 输出的 44100Hz WAV 可以直接传入,无需手动重采样。
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# basic-pitch 的默认 onset / frame 阈值参考官方推荐值
DEFAULT_ONSET_THRESHOLD = 0.5
DEFAULT_FRAME_THRESHOLD = 0.3

# 默认音高范围(MIDI 音符编号)。
#   21  = A0(钢琴最低音)
#   108 = C8(钢琴最高音)
DEFAULT_MIN_NOTE_MIDI = 21
DEFAULT_MAX_NOTE_MIDI = 108

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff", ".aif"}


def _midi_to_hz(midi_note: int) -> float:
    """把 MIDI 音符编号转成频率(Hz)。"""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def audio_to_midi(
    wav_path: str,
    output_path: str,
    onset_threshold: float = DEFAULT_ONSET_THRESHOLD,
    frame_threshold: float = DEFAULT_FRAME_THRESHOLD,
    min_note_midi: int = DEFAULT_MIN_NOTE_MIDI,
    max_note_midi: int = DEFAULT_MAX_NOTE_MIDI,
    progress=None,
) -> str:
    """把一个音频文件转成 MIDI。

    Args:
        wav_path: 输入音频文件路径(通常是分轨后的 WAV)。
        output_path: 输出 .mid 文件路径。
        onset_threshold: 音符起始(onset)检测阈值,0~1,越高音符越少越保守。
        frame_threshold: 帧级别音高检测阈值,0~1,越高越保守。
        min_note_midi: 允许的最低音符(MIDI 编号),默认 21(A0)。
        max_note_midi: 允许的最高音符(MIDI 编号),默认 108(C8)。
        progress: 可选进度回调,签名为 ``progress(fraction, desc)``。

    Returns:
        str: 生成的 .mid 文件路径。

    Raises:
        FileNotFoundError: 输入文件不存在。
        ValueError: 输入文件格式不受支持,或参数取值非法。
        RuntimeError: basic-pitch 推理失败(含模型下载失败)。
    """
    src = Path(wav_path)
    if not src.exists():
        raise FileNotFoundError(f"待转换的音频文件不存在:{wav_path}")
    if src.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的音频格式:{src.suffix}。"
            f"支持的格式:{', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if not (0.0 <= onset_threshold <= 1.0):
        raise ValueError(f"onset_threshold 应在 0~1 之间,当前为 {onset_threshold}")
    if not (0.0 <= frame_threshold <= 1.0):
        raise ValueError(f"frame_threshold 应在 0~1 之间,当前为 {frame_threshold}")
    if min_note_midi >= max_note_midi:
        raise ValueError(
            f"min_note_midi({min_note_midi})必须小于 max_note_midi({max_note_midi})"
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if progress is not None:
        progress(0.0, desc="加载 basic-pitch 模型…")

    # 延迟导入,避免未装依赖时 import 即失败
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise RuntimeError(
            "未检测到 basic-pitch,请先安装依赖:pip install -r requirements.txt"
        ) from exc

    if progress is not None:
        progress(0.3, desc="正在转 MIDI(音高识别)…")

    try:
        # basic-pitch 会自动读取并重采样音频;频率参数以 Hz 给出。
        # basic-pitch 内部会向 stdout 打印调试信息,这里重定向到 stderr,
        # 以保证 GUI(--json 模式)读取的 stdout 只包含纯净的 JSON。
        with contextlib.redirect_stdout(sys.stderr):
            _model_output, midi_data, _note_events = predict(
                str(src),
                ICASSP_2022_MODEL_PATH,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_frequency=_midi_to_hz(min_note_midi),
                maximum_frequency=_midi_to_hz(max_note_midi),
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"basic-pitch 转 MIDI 失败(可能是模型下载失败或音频读取问题):{exc}"
        ) from exc

    if progress is not None:
        progress(0.9, desc="写入 .mid 文件…")

    # midi_data 是 pretty_midi.PrettyMIDI 对象
    midi_data.write(str(out))

    if progress is not None:
        progress(1.0, desc="MIDI 生成完成")

    return str(out)


if __name__ == "__main__":  # 简单自测
    import sys

    if len(sys.argv) < 2:
        print("用法:python to_midi.py <音频路径> [输出.mid]")
        raise SystemExit(1)
    dst = sys.argv[2] if len(sys.argv) > 2 else "./out.mid"
    print(audio_to_midi(sys.argv[1], dst))
