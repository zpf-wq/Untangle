"""设备检测工具:优先使用 Apple Silicon 的 MPS 加速,不可用则回退 CPU。"""

from __future__ import annotations


def get_torch_device() -> str:
    """返回可用于 torch 的设备字符串。

    检测顺序:
        1. Apple Silicon 的 MPS(Metal Performance Shaders)
        2. CUDA(非 Apple 平台时可能可用)
        3. CPU(兜底)

    Returns:
        str: "mps" / "cuda" / "cpu" 之一。
    """
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - 仅在依赖缺失时触发
        raise ImportError(
            "未检测到 torch,请先按 README 安装依赖:pip install -r requirements.txt"
        ) from exc

    # Apple Silicon 优先
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"
