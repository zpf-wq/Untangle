"""Gradio 本地网页界面。

功能:
    - 上传音频(wav/mp3/flac/m4a)
    - 选择是否分轨;开启分轨时用复选框选择要转 MIDI 的轨道
    - 关闭分轨时直接对整首转 MIDI
    - 处理过程有进度反馈
    - 输出可下载的 .mid 文件与分轨 WAV

启动:
    python app.py
"""

from __future__ import annotations

import os
import tempfile

import gradio as gr

from pipeline import process
from separate import STEM_NAMES
from to_midi import (
    DEFAULT_FRAME_THRESHOLD,
    DEFAULT_MAX_NOTE_MIDI,
    DEFAULT_MIN_NOTE_MIDI,
    DEFAULT_ONSET_THRESHOLD,
)

# 所有产物统一放到系统临时目录下的子文件夹,方便 gradio 提供下载
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "untangle_output")


def run(
    audio_path: str | None,
    do_separate: bool,
    stems: list[str],
    onset_threshold: float,
    frame_threshold: float,
    min_note: int,
    max_note: int,
    progress=gr.Progress(),
):
    """Gradio 回调:执行完整处理流程并返回产物文件列表。

    Returns:
        tuple: (状态文本, 产物文件路径列表)。文件列表供 gr.Files 下载。
    """
    if not audio_path:
        return "请先上传一个音频文件。", []

    # 把 gradio 的 Progress 适配成 pipeline 期望的 progress(fraction, desc) 形式
    def _progress(fraction: float, desc: str = ""):
        progress(fraction, desc=desc)

    try:
        result = process(
            input_path=audio_path,
            stems_to_convert=stems if do_separate else [],
            output_dir=OUTPUT_DIR,
            separate_first=do_separate,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            min_note_midi=int(min_note),
            max_note_midi=int(max_note),
            progress=_progress,
        )
    except (FileNotFoundError, ValueError) as exc:
        return f"❌ 输入有误:{exc}", []
    except RuntimeError as exc:
        return f"❌ 运行出错:{exc}", []
    except Exception as exc:  # noqa: BLE001 - 界面层兜底,避免崩溃
        return f"❌ 未知错误:{exc}", []

    files: list[str] = []
    files.extend(result["stems"].values())
    files.extend(result["midis"].values())

    lines = ["✅ 处理完成!"]
    if result["stems"]:
        lines.append(f"分轨 WAV:{len(result['stems'])} 个")
    if result["midis"]:
        lines.append(f"MIDI 文件:{len(result['midis'])} 个")
    return "\n".join(lines), files


def build_demo() -> gr.Blocks:
    """构建 Gradio 界面。"""
    with gr.Blocks(title="Untangle — 本地分轨 + 转 MIDI") as demo:
        gr.Markdown(
            "# 🎵 Untangle\n"
            "本地音频**分轨**(Demucs)+ **转 MIDI**(basic-pitch)工具。"
            "全程本地运行,不上传云端。"
        )

        with gr.Row():
            with gr.Column():
                audio_in = gr.Audio(
                    label="上传音频(wav/mp3/flac/m4a)",
                    type="filepath",
                )
                do_separate = gr.Checkbox(
                    label="先分轨(关闭则直接对整首转 MIDI)",
                    value=True,
                )
                stems_in = gr.CheckboxGroup(
                    choices=list(STEM_NAMES),
                    value=["other"],
                    label="选择要转 MIDI 的轨道(分轨开启时生效)",
                )

                with gr.Accordion("高级参数(可选)", open=False):
                    onset = gr.Slider(
                        0.0, 1.0, value=DEFAULT_ONSET_THRESHOLD, step=0.05,
                        label="onset 阈值(越高音符越保守)",
                    )
                    frame = gr.Slider(
                        0.0, 1.0, value=DEFAULT_FRAME_THRESHOLD, step=0.05,
                        label="frame 阈值",
                    )
                    min_note = gr.Slider(
                        0, 127, value=DEFAULT_MIN_NOTE_MIDI, step=1,
                        label="最低音符(MIDI 编号,21=A0)",
                    )
                    max_note = gr.Slider(
                        0, 127, value=DEFAULT_MAX_NOTE_MIDI, step=1,
                        label="最高音符(MIDI 编号,108=C8)",
                    )

                run_btn = gr.Button("开始处理", variant="primary")

            with gr.Column():
                status = gr.Textbox(label="状态", lines=4, interactive=False)
                files_out = gr.Files(label="下载产物(WAV / MIDI)")

        # 切换分轨开关时,联动启用/禁用轨道复选框
        def _toggle(do_sep: bool):
            return gr.update(interactive=do_sep)

        do_separate.change(_toggle, inputs=do_separate, outputs=stems_in)

        run_btn.click(
            fn=run,
            inputs=[
                audio_in, do_separate, stems_in,
                onset, frame, min_note, max_note,
            ],
            outputs=[status, files_out],
        )

    return demo


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    build_demo().launch()
