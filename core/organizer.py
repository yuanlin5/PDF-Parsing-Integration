"""整理模块：把 MinerU 输出的 md 与图片按项目分类复制到 to-parse。"""

import shutil
from pathlib import Path

from core import config


def project_name_of(stem: str) -> str:
    """项目名 = 文件名第一个 _ / - / # 前的部分；没有分隔符则用整个文件名。"""
    for sep in ("_", "-", "#"):
        idx = stem.find(sep)
        if idx > 0:
            return _sanitize(stem[:idx])
    return _sanitize(stem)


def _sanitize(name: str) -> str:
    """去掉文件名里不允许的字符。"""
    name = name.strip().rstrip(".")
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name or "default"


def _unique_path(dest: Path) -> Path:
    """目标已存在时自动加序号，绝不覆盖。"""
    if not dest.exists():
        return dest
    n = 1
    while True:
        cand = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _copy_md_with_images(src_md: Path, dest_dir: Path, dest_name: str, log) -> int:
    """复制一个 md（图片引用同步改写为独立图片目录），返回 1=新增，0=跳过。"""
    text = src_md.read_text(encoding="utf-8", errors="replace")

    # 每个 md 配一个独立图片目录，改写 md 里的图片引用，互不干扰
    images_src = src_md.parent / "images"
    if images_src.is_dir():
        images_dest = dest_dir / f"{Path(dest_name).stem}_images"
        text = (
            text.replace("./images/", f"./{images_dest.name}/")
                .replace("images/", f"{images_dest.name}/")
        )
        if not images_dest.exists():
            shutil.copytree(images_src, images_dest)
        else:
            for f in images_src.rglob("*"):  # 已存在则只补缺失文件
                if f.is_file():
                    target = images_dest / f.relative_to(images_src)
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, target)

    dest_md = dest_dir / dest_name
    if dest_md.exists():
        if dest_md.read_text(encoding="utf-8", errors="replace") == text:
            log(f"  ↷ 已存在且内容相同，跳过：{dest_name}")
            return 0
        dest_md = _unique_path(dest_md)
        log(f"  ↷ 已存在同名文件，另存为：{dest_md.name}")
    dest_md.write_text(text, encoding="utf-8")
    return 1


def copy_result(entry: dict, log) -> int:
    """复制单条解析结果到 to-parse 对应项目文件夹。"""
    src_md: Path = entry["src_md"]
    stem: str = entry["stem"]
    chunk: int | None = entry.get("chunk")

    if not src_md.exists():
        log(f"  ⚠ 未找到解析结果：{src_md}")
        return 0

    dest_name = f"{stem}_part{chunk}.md" if chunk else f"{stem}.md"
    project = project_name_of(stem)
    dest_dir = config.TO_PARSE / project
    dest_dir.mkdir(parents=True, exist_ok=True)
    return _copy_md_with_images(src_md, dest_dir, dest_name, log)


def organize_entries(entries: list[dict], log) -> tuple[int, int]:
    """批量整理，返回 (新增数, 跳过数)。"""
    if not entries:
        log("没有需要整理的内容。")
        return 0, 0
    added = skipped = 0
    for entry in entries:
        r = copy_result(entry, log)
        if r:
            added += 1
        else:
            skipped += 1
    log(f"整理完成：新增 {added} 个，跳过 {skipped} 个")
    return added, skipped


def collect_from_output() -> list[dict]:
    """重新扫描 output 目录，返回与解析模块相同结构的结果清单（用于手动重跑整理）。

    MinerU 输出结构：
      普通文件：OUTPUT/<名>/auto/<名>.md
      分批文件：OUTPUT/<名>_partN/<名>/auto/<名>.md
    """
    entries: list[dict] = []
    for md in sorted(config.OUTPUT.rglob("auto/*.md")):
        stem_dir = md.parent.parent  # OUTPUT/<名> 或 OUTPUT/<名>_partN/<名>
        chunk = None
        if stem_dir.parent != config.OUTPUT:  # 分批文件：再上一级是 <名>_partN
            num = stem_dir.parent.name.rsplit("_part", 1)[-1]
            chunk = int(num) if num.isdigit() else None
        entries.append({"src_md": md, "stem": md.stem, "chunk": chunk})
    return entries
