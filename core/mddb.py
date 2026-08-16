"""md 数据库：解析完成后把 md 收集进 md数据库（图片内嵌，只存 md 文件）。

- 图片：引用改为 base64 内嵌，md 自包含，md数据库 里只有 .md 文件
- 分组：相同前缀但序号不同的文件（如「毛中特帽子 (1)」「毛中特帽子 (2)」）
  归入同一子文件夹；单独的文件保持原样放在根目录
- 重复解析时同名覆盖（数据库始终镜像最新解析结果）
"""

import base64
import re
import shutil
from pathlib import Path

from core import config

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

# 序号模式（用于提取分组前缀）：(N) 结尾 / _N_ 中间 / _N 结尾
_NUM_RES = [
    re.compile(r"\(\s*\d+\s*\)\s*$"),
    re.compile(r"_\d+_"),
    re.compile(r"_\d+\s*$"),
]


def _embed_images(text: str, base_dir: Path) -> str:
    """把本地图片引用替换为 base64 内嵌，使 md 自包含。"""

    def repl(m: re.Match) -> str:
        ref = m.group(2)
        img = (base_dir / ref).resolve()
        if img.suffix.lower() in _IMG_EXT and img.is_file():
            try:
                b64 = base64.b64encode(img.read_bytes()).decode("ascii")
                return (
                    f"![{m.group(1)}]"
                    f"(data:image/{img.suffix.lower().lstrip('.')};base64,{b64})"
                )
            except OSError:
                pass
        return m.group(0)

    return _IMG_RE.sub(repl, text)


def collect(md_path: Path, stem: str, chunk: int | None, log) -> Path | None:
    """新解析结果收集：图片内嵌后写入 md数据库 根目录（纯 md 文件）。"""
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        text = _embed_images(text, md_path.parent)
        dest_name = f"{stem}_part{chunk}.md" if chunk else f"{stem}.md"
        dest = config.MD_DB / dest_name
        dest.write_text(text, encoding="utf-8")
        return dest
    except OSError as e:
        log(f"  ⚠ 收集进 md数据库 失败：{e}")
        return None


def embed_existing() -> int:
    """对 md数据库 里已有的 md 做图片内嵌（保留用户已编辑的内容）。"""
    count = 0
    for md in config.MD_DB.glob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        new = _embed_images(text, md.parent)
        if new != text:
            md.write_text(new, encoding="utf-8")
            count += 1
    return count


def cleanup_image_dirs():
    """删除 md数据库 里的图片目录（内容已内嵌进 md）。"""
    for d in config.MD_DB.glob("*_images"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _prefix_of(stem: str) -> str | None:
    """提取分组前缀：文件名中首个序号标记前的部分；无序号返回 None。"""
    for pattern in _NUM_RES:
        m = pattern.search(stem)
        if m and m.start() > 0:
            return stem[: m.start()].rstrip(" _-")
    return None


def organize_groups() -> int:
    """相同前缀（序号不同）的文件移入同一子文件夹；单独文件保持原样。"""
    stems = [p.stem for p in config.MD_DB.glob("*.md")]
    prefixes: dict[str, int] = {}
    for s in stems:
        pfx = _prefix_of(s)
        if pfx:
            prefixes[pfx] = prefixes.get(pfx, 0) + 1

    moved = 0
    for p in config.MD_DB.glob("*.md"):
        pfx = _prefix_of(p.stem)
        if pfx and prefixes.get(pfx, 0) >= 2:
            folder = config.MD_DB / pfx
            folder.mkdir(exist_ok=True)
            dest = folder / p.name
            if dest.exists():
                dest.unlink()  # 同名覆盖（重复解析时）
            p.rename(dest)
            moved += 1
    return moved


def collect_all_output(log) -> int:
    """迁移：把 output 里现有全部 md 收集进 md数据库，返回收集数量。"""
    count = 0
    for md in sorted(config.OUTPUT.rglob("auto/*.md")):
        stem_dir = md.parent.parent  # OUTPUT/<名> 或 OUTPUT/<名>_partN/<名>
        chunk = None
        if stem_dir.parent != config.OUTPUT:
            num = stem_dir.parent.name.rsplit("_part", 1)[-1]
            chunk = int(num) if num.isdigit() else None
        if collect(md, md.stem, chunk, log):
            count += 1
    return count
