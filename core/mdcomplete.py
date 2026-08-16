"""已完成标记：录题完成后，把处理过的 md 文件（及全完成的文件夹）改名加「已完成」。

用法（在仓库根目录执行）：
    python core/mdcomplete.py <md文件路径1> <md文件路径2> ...

规则：
- 文件：<文件名>.md → <文件名>已完成.md（已带后缀的跳过，可重复执行）
- 文件夹：分组文件夹内所有 md 都带「已完成」时，文件夹名一并加「已完成」
"""

import sys
from pathlib import Path

from core import config

SUFFIX = "已完成"


def _mark_file(md: Path) -> bool:
    if md.stem.endswith(SUFFIX):
        return False
    dest = md.with_name(f"{md.stem}{SUFFIX}.md")
    md.rename(dest)
    return True


def _folder_all_done(folder: Path) -> bool:
    mds = list(folder.glob("*.md"))
    return bool(mds) and all(m.stem.endswith(SUFFIX) for m in mds)


def mark_complete(md_paths: list[Path]) -> dict:
    """给 md 加「已完成」后缀；所在分组文件夹内全部完成时文件夹一并改名。"""
    renamed_files = 0
    touched_dirs: set[Path] = set()
    for p in md_paths:
        p = p.resolve()
        if not p.is_file() or not p.suffix.lower() == ".md":
            continue
        try:
            if _mark_file(p):
                renamed_files += 1
            if p.parent != config.MD_DB.resolve():
                touched_dirs.add(p.parent)
        except OSError:
            pass

    renamed_dirs = 0
    for d in sorted(touched_dirs):
        if d.exists() and not d.name.endswith(SUFFIX) and _folder_all_done(d):
            dest = d.with_name(f"{d.name}{SUFFIX}")
            d.rename(dest)
            renamed_dirs += 1
    return {"files": renamed_files, "folders": renamed_dirs}


def main():
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print("用法: python core/mdcomplete.py <md文件路径...>")
        return
    result = mark_complete(paths)
    print(f"已完成标记：{result['files']} 个文件改名，{result['folders']} 个文件夹改名")


if __name__ == "__main__":
    main()
