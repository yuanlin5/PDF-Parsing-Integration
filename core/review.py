"""核对模块：解析后的人工核对状态管理（待核对 / 已确认）。

机制说明（应对并行任务多的情况）：
- 每个任务（源文件）有独立状态，互不影响，可以边解析边核对
- 状态持久化到 workspace/review.json，面板重启/关闭不丢失
- 归档只收「已确认」的任务，天然防止漏核对
- 重新解析会自动重置该文件的确认状态（内容变了必须重新核对）
"""

import datetime
import json
from pathlib import Path

from core import config


def load_review() -> dict:
    """读取核对状态：{相对路径: {"confirmed": True, "at": "..."}}。"""
    try:
        return json.loads(config.REVIEW_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_review(data: dict):
    config.REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.REVIEW_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_confirmed(key: str) -> bool:
    return bool(load_review().get(key, {}).get("confirmed"))


def set_confirmed(key: str, confirmed: bool):
    data = load_review()
    if confirmed:
        data[key] = {
            "confirmed": True,
            "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    else:
        data.pop(key, None)
    save_review(data)


def reset(key: str):
    """重新解析后清空核对状态（内容已变，需重新核对）。"""
    set_confirmed(key, False)


def _rel_key(path: Path) -> str:
    return str(path.relative_to(config.PENDING)).replace("\\", "/")


def _find_mds(stem: str) -> list[Path]:
    """该文件在 md数据库 下的全部 md（分批文件有多个；支持分组子文件夹）。"""
    mds = sorted(config.MD_DB.glob(f"**/{stem}.md"))
    mds += sorted(config.MD_DB.glob(f"**/{stem}_part*.md"))
    return mds


def list_tasks() -> list[dict]:
    """核对任务清单：pending 里已在 md数据库 有结果的文件（含分批）。

    任务条目：{key, src, stem, mds, confirmed}
    """
    tasks: list[dict] = []
    for p in sorted(config.PENDING.rglob("*")):
        if not p.is_file():
            continue
        if config.FAILED in p.parents or p.parent == config.FAILED:
            continue
        if p.suffix.lower() not in config.SUPPORTED_EXT:
            continue
        mds = _find_mds(p.stem)
        if not mds:
            continue  # 未解析/解析中，不进核对清单
        key = _rel_key(p)
        tasks.append({
            "key": key,
            "src": p,
            "stem": p.stem,
            "mds": mds,
            "confirmed": is_confirmed(key),
        })
    return tasks


def summary(tasks: list[dict] | None = None) -> tuple[int, int]:
    """返回 (待核对数, 已确认数)。"""
    if tasks is None:
        tasks = list_tasks()
    pending = sum(1 for t in tasks if not t["confirmed"])
    return pending, len(tasks) - pending
