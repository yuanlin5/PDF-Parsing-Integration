"""解析模块：扫描 pending 文件夹，逐个调用 MinerU 解析（大 PDF 自动分批）。"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core import config


# ── 已处理记录（防重复解析）────────────────────────────────

def _load_processed() -> dict:
    """读取已处理记录：{相对路径: [大小, 修改时间]}。"""
    try:
        return json.loads(config.PROCESSED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_processed(data: dict):
    config.PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.PROCESSED_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _rel_key(path: Path) -> str:
    return str(path.relative_to(config.PENDING)).replace("\\", "/")


def _file_signature(path: Path) -> list:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


# ── 扫描待处理文件 ─────────────────────────────────────────

def scan_pending(force: bool, log) -> list[Path]:
    """收集待处理文件；force=False 时跳过已处理过的文件。"""
    files: list[Path] = []
    processed = _load_processed()
    for p in sorted(config.PENDING.rglob("*")):
        if not p.is_file():
            continue
        if config.FAILED in p.parents or p.parent == config.FAILED:
            continue
        if p.suffix.lower() not in config.SUPPORTED_EXT:
            continue
        if p.name.startswith("~$"):  # Office 临时文件
            continue
        key = _rel_key(p)
        if not force and processed.get(key) == _file_signature(p):
            continue
        files.append(p)
    return files


def _is_stable(path: Path, log) -> bool:
    """等文件大小在 3 秒内不变（防止用户还在复制就开跑）。"""
    size = path.stat().st_size
    waited = 0
    while waited < config.STABLE_TIMEOUT:
        time.sleep(config.STABLE_INTERVAL)
        waited += config.STABLE_INTERVAL
        try:
            new_size = path.stat().st_size
        except OSError:
            return False
        if new_size == size:
            return True
        size = new_size
    log(f"  ⚠ 跳过：{path.name} 长时间仍在写入（可能还在复制）")
    return False


# ── MinerU 调用 ────────────────────────────────────────────

def _run_mineru(src: Path, out_dir: Path, log,
                start: int | None = None, end: int | None = None) -> bool:
    """调用 MinerU CLI 解析（可指定页段），逐行回显输出。成功返回 True。"""
    cmd = [str(config.MINERU_EXE), "-p", str(src), "-o", str(out_dir), *config.MINERU_ARGS]
    if start is not None:
        cmd += ["-s", str(start)]
    if end is not None:
        cmd += ["-e", str(end)]

    log(f"  $ mineru -p {src.name} -o {out_dir.name}")
    si = None
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=si,
        cwd=str(config.ROOT),
    )
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip()
        if line:
            log(f"    {line}")
    proc.wait()
    return proc.returncode == 0


def _pdf_pages(path: Path) -> int | None:
    """PDF 页数（非 PDF 返回 None）。"""
    if path.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


# ── 失败处理 ───────────────────────────────────────────────

def _move_to_failed(src: Path, log):
    config.FAILED.mkdir(parents=True, exist_ok=True)
    target = config.FAILED / src.name
    n = 1
    while target.exists():
        target = config.FAILED / f"{src.stem}_{n}{src.suffix}"
        n += 1
    src.rename(target)
    log(f"  ❌ 解析失败，文件已移入 workspace\\pending\\failed\\")


def _cleanup_outputs(src: Path):
    """清除该文件在 output 下的（部分）解析产物。"""
    for d in config.OUTPUT.glob(f"{src.stem}*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


# ── 主流程 ─────────────────────────────────────────────────

def process_pending(force: bool, log) -> list[dict]:
    """解析 pending 全部文件，返回结果清单（供整理模块使用）。

    结果条目：{"src_md": Path, "stem": str, "chunk": int|None}
    """
    results: list[dict] = []
    files = scan_pending(force, log)
    if not files:
        log("待处理文件夹为空，没有需要解析的文件。")
        return results

    log(f"共发现 {len(files)} 个文件，逐个解析（CPU 单任务，请耐心等待）…")
    processed = _load_processed()
    ok_files = 0
    fail_files = 0

    for idx, src in enumerate(files, 1):
        log(f"[{idx}/{len(files)}] 解析 {src.name}")
        if not _is_stable(src, log):
            continue

        pages = _pdf_pages(src)
        entries: list[dict] = []
        if pages is not None and pages > config.SPLIT_THRESHOLD:
            n_chunks = (pages + config.PAGE_CHUNK - 1) // config.PAGE_CHUNK
            log(f"  共 {pages} 页，超过 {config.SPLIT_THRESHOLD} 页，按 {config.PAGE_CHUNK} 页/批切分")
            for i in range(n_chunks):
                s = i * config.PAGE_CHUNK
                e = min(s + config.PAGE_CHUNK - 1, pages - 1)
                out_dir = config.OUTPUT / f"{src.stem}_part{i + 1}"
                log(f"  第 {i + 1}/{n_chunks} 批：第 {s + 1}~{e + 1} 页")
                ok = _run_mineru(src, out_dir, log, start=s, end=e)
                if ok:
                    entries.append({
                        "src_md": out_dir / src.stem / "auto" / f"{src.stem}.md",
                        "stem": src.stem,
                        "chunk": i + 1,
                    })
                else:
                    break  # 某批失败则放弃该文件
        else:
            ok = _run_mineru(src, config.OUTPUT, log)
            if ok:
                entries.append({
                    "src_md": config.OUTPUT / src.stem / "auto" / f"{src.stem}.md",
                    "stem": src.stem,
                    "chunk": None,
                })

        # 全部批都成功才算成功
        if pages is not None and pages > config.SPLIT_THRESHOLD:
            expected = (pages + config.PAGE_CHUNK - 1) // config.PAGE_CHUNK
        else:
            expected = 1
        if len(entries) >= expected and entries:
            results.extend(entries)
            processed[_rel_key(src)] = _file_signature(src)
            ok_files += 1
        else:
            _cleanup_outputs(src)
            _move_to_failed(src, log)
            processed.pop(_rel_key(src), None)  # 失败不记录，方便重试
            fail_files += 1
        _save_processed(processed)

    log(f"解析完成：成功 {ok_files} 个，失败 {fail_files} 个")
    return results


# ── 归档 ─────────────────────────────────────────────────

def archive_processed(log) -> tuple[int, int]:
    """把 pending 里已解析成功的源文件移入 done\（保持待处理区干净）。

    返回 (移入数, 剩余数)。重名自动加序号；归档后从已处理清单移除，
    若用户把文件放回 pending 会重新解析。
    """
    processed = _load_processed()
    moved = 0
    remaining = 0
    for p in sorted(config.PENDING.rglob("*")):
        if not p.is_file():
            continue
        if config.FAILED in p.parents or p.parent == config.FAILED:
            continue
        key = _rel_key(p)
        if processed.get(key) != _file_signature(p):
            remaining += 1
            continue
        config.DONE.mkdir(parents=True, exist_ok=True)
        target = config.DONE / p.name
        n = 1
        while target.exists():
            target = config.DONE / f"{p.stem}_{n}{p.suffix}"
            n += 1
        p.rename(target)
        processed.pop(key, None)
        moved += 1
        log(f"  归档：{target.name}")
    _save_processed(processed)
    return moved, remaining
