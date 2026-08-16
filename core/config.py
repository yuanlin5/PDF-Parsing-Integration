"""全局配置：路径常量、版本号、MinerU 调用参数。"""

import os
from pathlib import Path

APP_NAME = "PDF 解析集成"
VERSION = "1.2.3"

# Edge 浏览器（内置 Markdown 渲染，用于直接查看 md 的排版格式）
EDGE_EXE = Path(
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

def _find_wps() -> Path | None:
    """定位 WPS 文字（wps.exe），取已安装的最高版本；未安装返回 None。"""
    bases = [
        Path(r"C:\Program Files (x86)\Kingsoft\WPS Office"),
        Path(r"C:\Program Files\Kingsoft\WPS Office"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Kingsoft" / "WPS Office",
    ]

    def _ver(p: Path) -> tuple:
        try:
            return tuple(int(x) for x in p.parent.parent.name.split("."))
        except ValueError:
            return (0,)

    exes: list[Path] = []
    for base in bases:
        if base.exists():
            exes += list(base.glob("*/office6/wps.exe"))
    return max(exes, key=_ver) if exes else None


# WPS 文字（用户熟悉的办公软件，md 阅读+编辑都所见即所得，用于核对时修改解析结果）
WPS_EXE = _find_wps()

# 仓库根目录（core 的上一级）
ROOT = Path(__file__).resolve().parent.parent

# 工作目录（用户数据，不入 git，启动时自动创建）
WORKSPACE = ROOT / "workspace"
PENDING = WORKSPACE / "pending"      # 待处理：用户把 PDF/图片丢进来
FAILED = PENDING / "failed"          # 解析失败的文件移到这里
OUTPUT = WORKSPACE / "output"        # MinerU 解析结果
DONE = WORKSPACE / "done"            # 归档：已解析成功的源文件移到这里
STATUS_FILE = OUTPUT / "status.txt"  # 最近一次运行的状态记录
PROCESSED_FILE = WORKSPACE / "processed.json"  # 已处理文件清单（防重复）
REVIEW_FILE = WORKSPACE / "review.json"  # 核对状态清单（待核对/已确认）

# MinerU：本机安装位置与参数（与 MinerU 图形界面 mineru_gui.py 保持一致）
MINERU_EXE = Path(
    r"C:\Users\WRS\AppData\Local\Programs\Python\Python312\Scripts\mineru.exe"
)
MINERU_ARGS = [
    "-b", "pipeline",      # CPU 后端（本机无独立显卡）
    "-m", "auto",          # 自动判断解析方式
    "--effort", "medium",
    "-l", "ch",            # 中文文档
    "-f", "true",          # 公式识别
    "-t", "true",          # 表格识别
    "--image-analysis", "false",
]

# 支持的文件类型
SUPPORTED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".docx", ".pptx", ".xlsx"}

# 分批参数：PDF 超过 SPLIT_THRESHOLD 页时，按 PAGE_CHUNK 页/批切分解析
SPLIT_THRESHOLD = 30
PAGE_CHUNK = 15

# 文件写入稳定检查：间隔 3 秒，最多等 60 秒（防止用户还在复制文件）
STABLE_INTERVAL = 3
STABLE_TIMEOUT = 60


def ensure_dirs():
    """确保所有工作目录存在。"""
    for d in (PENDING, FAILED, OUTPUT, DONE):
        d.mkdir(parents=True, exist_ok=True)
