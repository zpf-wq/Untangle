"""整合流程模块。

把「分轨」和「转 MIDI」串起来:
    先用 Demucs 分轨 → 对指定的轨道分别用 basic-pitch 转 MIDI。
也支持「不分轨,直接对整首转 MIDI」的模式。
"""

from __future__ import annotations

from pathlib import Path

from separate import STEM_NAMES, separate
from to_midi import (
    DEFAULT_FRAME_THRESHOLD,
    DEFAULT_MAX_NOTE_MIDI,
    DEFAULT_MIN_NOTE_MIDI,
    DEFAULT_ONSET_THRESHOLD,
    audio_to_midi,
)


def process(
    input_path: str,
    stems_to_convert: list[str] | None,
    output_dir: str,
    separate_first: bool = True,
    onset_threshold: float = DEFAULT_ONSET_THRESHOLD,
    frame_threshold: float = DEFAULT_FRAME_THRESHOLD,
    min_note_midi: int = DEFAULT_MIN_NOTE_MIDI,
    max_note_midi: int = DEFAULT_MAX_NOTE_MIDI,
    progress=None,
) -> dict:
    """完整处理流程:分轨 +(可选)转 MIDI。

    两种模式:
        1. 分轨模式(``separate_first=True``):先把音频分成 4 轨,
           再对 ``stems_to_convert`` 中指定的轨道分别转 MIDI。
        2. 整首模式(``separate_first=False`` 或 ``stems_to_convert`` 为空):
           跳过分轨,直接对整首音频转 MIDI。

    Args:
        input_path: 输入音频路径。
        stems_to_convert: 需要转 MIDI 的轨道名列表(drums/bass/vocals/other)。
            若为 None 或空列表,则不转任何分轨的 MIDI。
        output_dir: 输出目录。
        separate_first: 是否先分轨。False 时直接对整首转 MIDI。
        onset_threshold: 传给 basic-pitch 的 onset 阈值。
        frame_threshold: 传给 basic-pitch 的 frame 阈值。
        min_note_midi: 最低音符(MIDI 编号)。
        max_note_midi: 最高音符(MIDI 编号)。
        progress: 可选进度回调,签名 ``progress(fraction, desc)``。

    Returns:
        dict: 产物路径,结构为::

            {
                "stems": {轨道名: wav路径, ...},   # 未分轨时为空 dict
                "midis": {名称: mid路径, ...},
            }

    Raises:
        FileNotFoundError / ValueError / RuntimeError: 见各子模块说明。
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"输入音频文件不存在:{input_path}")

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    stems_to_convert = stems_to_convert or []
    # 校验轨道名
    invalid = [s for s in stems_to_convert if s not in STEM_NAMES]
    if invalid:
        raise ValueError(
            f"未知的轨道名:{invalid}。可选:{', '.join(STEM_NAMES)}"
        )

    result: dict = {"stems": {}, "midis": {}}

    # ---- 模式 2:不分轨,直接整首转 MIDI ----
    if not separate_first:
        midi_out = out_root / f"{src.stem}.mid"
        if progress is not None:
            progress(0.1, desc="整首转 MIDI 模式")
        result["midis"]["full"] = audio_to_midi(
            str(src),
            str(midi_out),
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            min_note_midi=min_note_midi,
            max_note_midi=max_note_midi,
            progress=_subprogress(progress, 0.1, 1.0),
        )
        return result

    # ---- 模式 1:先分轨 ----
    stems = separate(
        str(src),
        str(out_root),
        progress=_subprogress(progress, 0.0, 0.6),
    )
    result["stems"] = stems

    # 对指定轨道分别转 MIDI
    n = len(stems_to_convert)
    for i, stem in enumerate(stems_to_convert):
        wav_path = stems.get(stem)
        if not wav_path:
            # 理论上不会发生(前面已校验),保险起见跳过
            continue
        midi_out = out_root / f"{src.stem}_{stem}.mid"
        lo = 0.6 + 0.4 * (i / max(n, 1))
        hi = 0.6 + 0.4 * ((i + 1) / max(n, 1))
        result["midis"][stem] = audio_to_midi(
            wav_path,
            str(midi_out),
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            min_note_midi=min_note_midi,
            max_note_midi=max_note_midi,
            progress=_subprogress(progress, lo, hi),
        )

    if progress is not None:
        progress(1.0, desc="全部完成")

    return result


def _subprogress(progress, start: float, end: float):
    """把子任务的 0~1 进度映射到整体进度的 [start, end] 区间。

    返回一个新的回调函数;若外层 progress 为 None,则返回 None。
    """
    if progress is None:
        return None

    def _cb(fraction: float, desc: str = ""):
        mapped = start + (end - start) * max(0.0, min(1.0, fraction))
        progress(mapped, desc=desc)

    return _cb
