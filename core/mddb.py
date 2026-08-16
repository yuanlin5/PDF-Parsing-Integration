"""md 数据库：解析完成后把 md 与图片统一收集到 md数据库 文件夹。

- 命名：<文件名>.md；分批文件为 <文件名>_partN.md；重名自动加序号
- 图片：复制为 <md名>_images 目录并改写 md 里的引用，保证自包含
- 重复解析时同名覆盖（数据库始终镜像最新解析结果）
"""

import shutil
from pathlib import Path

from core import config


def _copy_md(md_path: Path, dest_dir: Path, dest_name: str, log) -> Path | None:
    """复制一个 md（图片目录随迁并改写引用），返回目标路径；失败返回 None。"""
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        images_src = md_path.parent / "images"
        if images_src.is_dir():
            images_dest = dest_dir / f"{Path(dest_name).stem}_images"
            if images_dest.exists():
                shutil.rmtree(images_dest)  # 覆盖：始终镜像最新解析
            shutil.copytree(images_src, images_dest)
            text = (
                text.replace("./images/", f"./{images_dest.name}/")
                    .replace("images/", f"{images_dest.name}/")
            )
        dest = dest_dir / dest_name
        dest.write_text(text, encoding="utf-8")
        return dest
    except OSError as e:
        log(f"  ⚠ 收集到 md数据库 失败：{e}")
        return None


def collect(md_path: Path, stem: str, chunk: int | None, log) -> Path | None:
    """把一份解析结果收集进 md数据库，返回目标路径。"""
    dest_name = f"{stem}_part{chunk}.md" if chunk else f"{stem}.md"
    return _copy_md(md_path, config.MD_DB, dest_name, log)


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
