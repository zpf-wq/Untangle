"""命令行入口。

示例:
    # 分轨,并对 other / bass 两轨转 MIDI
    python cli.py song.mp3 --stems other,bass --output ./out

    # 不分轨,直接对整首转 MIDI
    python cli.py song.mp3 --no-separate --output ./out
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline import process
from separate import STEM_NAMES
from to_midi import (
    DEFAULT_FRAME_THRESHOLD,
    DEFAULT_MAX_NOTE_MIDI,
    DEFAULT_MIN_NOTE_MIDI,
    DEFAULT_ONSET_THRESHOLD,
)


def _make_console_progress():
    """返回一个把进度打印到终端的回调。"""

    def _cb(fraction: float, desc: str = ""):
        pct = int(max(0.0, min(1.0, fraction)) * 100)
        # \r 原地刷新进度
        sys.stdout.write(f"\r[{pct:3d}%] {desc:<40}")
        sys.stdout.flush()
        if pct >= 100:
            sys.stdout.write("\n")

    return _cb


def _emit_json(obj: dict) -> None:
    """把一条事件以单行 JSON 写到 stdout 并立即 flush(供 Swift/GUI 解析)。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _make_json_progress():
    """返回一个把进度以 JSON 事件输出的回调,供 GUI 前端读取。"""

    def _cb(fraction: float, desc: str = ""):
        _emit_json(
            {
                "type": "progress",
                "fraction": max(0.0, min(1.0, fraction)),
                "desc": desc,
            }
        )

    return _cb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Untangle:本地音频分轨 + 转 MIDI 工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="输入音频文件路径(wav/mp3/flac/m4a)")
    parser.add_argument(
        "--stems",
        default="other",
        help=(
            "要转 MIDI 的轨道,逗号分隔。"
            f"可选:{', '.join(STEM_NAMES)}。分轨模式下生效。"
        ),
    )
    parser.add_argument(
        "--output", "-o", default="./out", help="输出目录"
    )
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="跳过分轨,直接对整首音频转 MIDI",
    )
    parser.add_argument(
        "--onset-threshold",
        type=float,
        default=DEFAULT_ONSET_THRESHOLD,
        help="basic-pitch onset 阈值(0~1)",
    )
    parser.add_argument(
        "--frame-threshold",
        type=float,
        default=DEFAULT_FRAME_THRESHOLD,
        help="basic-pitch frame 阈值(0~1)",
    )
    parser.add_argument(
        "--min-note",
        type=int,
        default=DEFAULT_MIN_NOTE_MIDI,
        help="最低音符(MIDI 编号,21=A0)",
    )
    parser.add_argument(
        "--max-note",
        type=int,
        default=DEFAULT_MAX_NOTE_MIDI,
        help="最高音符(MIDI 编号,108=C8)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以逐行 JSON 输出进度与结果(供 GUI 前端调用,非人类阅读)",
    )

    args = parser.parse_args(argv)

    separate_first = not args.no_separate
    if separate_first:
        stems = [s.strip() for s in args.stems.split(",") if s.strip()]
    else:
        stems = []

    progress_cb = _make_json_progress() if args.json else _make_console_progress()

    try:
        result = process(
            input_path=args.input,
            stems_to_convert=stems,
            output_dir=args.output,
            separate_first=separate_first,
            onset_threshold=args.onset_threshold,
            frame_threshold=args.frame_threshold,
            min_note_midi=args.min_note,
            max_note_midi=args.max_note,
            progress=progress_cb,
        )
    except (FileNotFoundError, ValueError) as exc:
        if args.json:
            _emit_json({"type": "error", "message": str(exc)})
        else:
            print(f"\n错误:{exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        if args.json:
            _emit_json({"type": "error", "message": str(exc)})
        else:
            print(f"\n运行出错:{exc}", file=sys.stderr)
        return 1

    if args.json:
        # 最终结果事件:stems / midis 都是 {名称: 路径}
        _emit_json(
            {"type": "result", "stems": result["stems"], "midis": result["midis"]}
        )
        return 0

    print("\n===== 处理完成 =====")
    if result["stems"]:
        print("分轨 WAV:")
        for name, path in result["stems"].items():
            print(f"  {name}: {path}")
    if result["midis"]:
        print("MIDI 文件:")
        for name, path in result["midis"].items():
            print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
