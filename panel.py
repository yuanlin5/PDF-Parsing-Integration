"""PDF 解析面板 — 双击 start_panel.bat 启动。

三个阶段各一个按钮：
  ① 开始解析  pending 里的文件逐个交给 MinerU（大 PDF 自动分批）
  ② 核对      核对区逐项打开原文件与解析 md 对照，无误点「确认」
  ③ 归档      把已确认的文件移入 done\，保持待处理区干净
"""

import datetime
import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, scrolledtext

from core import config
from core import parser
from core import review

USAGE = """【使用方法】
① 把 PDF / 图片 放进 workspace\\pending 文件夹（可用子文件夹分项目）
② 点「① 开始解析」，等日志出现"全部完成"（CPU 解析，大文件请耐心等待，
   超过 30 页的 PDF 会自动按 15 页/批切分）
③ 在下方核对区逐项点「打开核对」：同时打开原文件与解析出的 md
   （md 用 Edge 浏览器打开，自动显示标题/加粗/图片等排版格式）；
   发现文字有误就点「编辑 md」在 Obsidian 里改完保存（Ctrl+S）；
   对照无误后点「确认」（再次点击可撤销；解析一批核对一批，互不影响）
④ 全部确认后点「③ 归档」——只归档已确认的文件，未确认的留在 pending
⑤ 解析结果在 workspace\\output\\<文件名>\\ 里，文字内容为 auto\\<文件名>.md，
   图片在 auto\\images\\ 下

提示：解析失败的文件会移入 workspace\\pending\\failed\\，可从那里取回重试。
勾选「包含已解析过的文件」可强制重新解析（重新解析会重置核对状态）。"""


class Panel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.busy = False
        self.force_var = tk.BooleanVar(value=False)
        self.filter_var = tk.StringVar(value="全部")
        self.msg_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        config.ensure_dirs()
        self._build_ui()
        self._poll_queue()
        self.refresh_checklist()

    # ── 界面构建 ──────────────────────────────────────────

    def _build_ui(self):
        self.root.title(f"{config.APP_NAME} 面板  v{config.VERSION}")
        self.root.geometry("860x720")
        self.root.minsize(760, 600)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))

        # 按钮区
        bar = ttk.Frame(self.root, padding=(12, 10))
        bar.pack(fill=tk.X)

        self.btn_parse = ttk.Button(bar, text="① 开始解析", command=self.on_parse)
        self.btn_parse.pack(side=tk.LEFT)
        self.btn_archive = ttk.Button(bar, text="③ 归档", command=self.on_archive)
        self.btn_archive.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(
            bar, text="包含已解析过的文件", variable=self.force_var
        ).pack(side=tk.LEFT, padx=(16, 0))

        # 打开文件夹
        open_bar = ttk.Frame(self.root, padding=(12, 0))
        open_bar.pack(fill=tk.X)
        ttk.Label(open_bar, text="打开文件夹：").pack(side=tk.LEFT)
        for text, path in (
            ("待处理", config.PENDING),
            ("输出结果", config.OUTPUT),
            ("已完成", config.DONE),
        ):
            ttk.Button(
                open_bar, text=text,
                command=lambda p=path: self._open_folder(p),
            ).pack(side=tk.LEFT, padx=(6, 0))

        # 核对区
        check_frame = ttk.LabelFrame(
            self.root,
            text="核对区（解析后逐项打开原文件与 md 对照，确认无误后点「确认」）",
            padding=6,
        )
        check_frame.pack(fill=tk.X, padx=12, pady=(8, 0))

        check_bar = ttk.Frame(check_frame)
        check_bar.pack(fill=tk.X)
        self.check_summary = ttk.Label(check_bar, text="")
        self.check_summary.pack(side=tk.LEFT)
        ttk.Button(check_bar, text="刷新", command=self.refresh_checklist).pack(side=tk.RIGHT)
        self.filter_box = ttk.Combobox(
            check_bar, textvariable=self.filter_var,
            values=["全部", "待核对", "已确认"], state="readonly", width=8,
        )
        self.filter_box.pack(side=tk.RIGHT, padx=(0, 6))
        self.filter_var.trace_add("write", lambda *a: self.refresh_checklist())

        # 可滚动任务列表
        list_frame = ttk.Frame(check_frame)
        list_frame.pack(fill=tk.X)
        self.task_canvas = tk.Canvas(list_frame, height=160, highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.task_canvas.yview)
        self.task_canvas.configure(yscrollcommand=sb.set)
        self.task_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_inner = ttk.Frame(self.task_canvas)
        self._task_window = self.task_canvas.create_window(
            (0, 0), window=self.task_inner, anchor="nw"
        )
        self.task_inner.bind(
            "<Configure>",
            lambda e: self.task_canvas.configure(scrollregion=self.task_canvas.bbox("all")),
        )
        self.task_canvas.bind(
            "<Configure>",
            lambda e: self.task_canvas.itemconfigure(self._task_window, width=e.width),
        )

        # 日志区
        log_frame = ttk.LabelFrame(self.root, text="进度日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 0))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, state=tk.DISABLED, wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("error", foreground="#d33a3a")
        self.log_text.tag_configure("done", foreground="#1a7f37")

        # 使用方法区
        usage_frame = ttk.LabelFrame(self.root, text="使用方法", padding=6)
        usage_frame.pack(fill=tk.X, padx=12, pady=(8, 10))
        self.usage_label = ttk.Label(usage_frame, text=USAGE, justify=tk.LEFT)
        self.usage_label.pack(anchor=tk.W)

    # ── 核对区：任务看板 ────────────────────────────────────

    def refresh_checklist(self):
        """按过滤条件重建任务列表（主线程调用）。"""
        for child in self.task_inner.winfo_children():
            child.destroy()
        tasks = review.list_tasks()
        filter_mode = self.filter_var.get()
        shown = [
            t for t in tasks
            if filter_mode == "全部"
            or (filter_mode == "待核对" and not t["confirmed"])
            or (filter_mode == "已确认" and t["confirmed"])
        ]
        pending, confirmed = review.summary(tasks)
        self.check_summary.configure(text=f"待核对 {pending} · 已确认 {confirmed}")

        if not shown:
            ttk.Label(self.task_inner, text="（暂无需要核对的解析结果）",
                      foreground="#999").pack(anchor=tk.W, pady=4)
            return

        for t in shown:
            row = ttk.Frame(self.task_inner)
            row.pack(fill=tk.X, pady=1)
            btn = ttk.Button(
                row, text="✓ 已确认" if t["confirmed"] else "确认", width=9,
                command=lambda task=t: self._toggle_confirm(task),
            )
            btn.pack(side=tk.LEFT, padx=(2, 6))
            ttk.Label(row, text=t["stem"], anchor=tk.W).pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
            ttk.Button(
                row, text="打开核对",
                command=lambda task=t: self._open_review(task),
            ).pack(side=tk.LEFT, padx=(6, 2))
            ttk.Button(
                row, text="编辑 md",
                command=lambda task=t: self._open_editor(task),
            ).pack(side=tk.LEFT, padx=(2, 2))

    def _toggle_confirm(self, task: dict):
        review.set_confirmed(task["key"], not task["confirmed"])
        verb = "已确认" if not task["confirmed"] else "已撤销确认"
        self.log(f"  核对 {verb}：{task['stem']}")
        self.refresh_checklist()

    def _open_review(self, task: dict):
        """同时打开原文件与全部解析 md（md 用 Edge 打开，自动显示排版格式）。"""
        try:
            os.startfile(str(task["src"]))
            for md in task["mds"]:
                self._open_md(md)
            self.log(f"  已打开核对：{task['stem']}（原文件 + {len(task['mds'])} 个 md，Edge 显示格式）")
        except OSError as e:
            self.log(f"❌ 无法打开文件：{e}", "error")

    def _open_md(self, md: Path):
        """用 Edge 打开 md（Edge 内置 Markdown 渲染，直接显示排版格式）。"""
        if config.EDGE_EXE.exists():
            subprocess.Popen([str(config.EDGE_EXE), md.as_uri()])
        else:
            os.startfile(str(md))  # 兜底：交给系统默认程序

    def _open_editor(self, task: dict):
        """用 Obsidian 打开全部解析 md 进行编辑（所见即所得）。"""
        try:
            for md in task["mds"]:
                self._open_md_in_obsidian(md)
            self.log(f"  已在 Obsidian 打开：{task['stem']}（编辑后 Ctrl+S 保存即可）")
        except OSError as e:
            self.log(f"❌ 无法打开文件：{e}", "error")

    def _open_md_in_obsidian(self, md: Path):
        if config.OBSIDIAN_EXE.exists():
            subprocess.Popen([str(config.OBSIDIAN_EXE), str(md)])
        else:
            os.startfile(str(md))  # 兜底：交给系统默认程序

    # ── 日志（线程安全：队列 + 轮询回写界面）────────────────

    def log(self, msg: str, tag: str = ""):
        self.msg_queue.put((msg, tag))
        self._write_status(msg)

    def _poll_queue(self):
        try:
            while True:
                msg, tag = self.msg_queue.get_nowait()
                self.log_text.configure(state=tk.NORMAL)
                self.log_text.insert(tk.END, msg + "\n", tag)
                self.log_text.see(tk.END)
                self.log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _write_status(self, msg: str):
        try:
            line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n"
            with open(config.STATUS_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    # ── 按钮动作 ──────────────────────────────────────────

    def _set_buttons(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_parse.configure(state=state)
        self.btn_archive.configure(state=state)

    def on_parse(self):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)
        try:
            config.STATUS_FILE.write_text("", encoding="utf-8")
        except OSError:
            pass
        self.log(f"──── 开始解析（v{config.VERSION}）────")
        threading.Thread(target=self._parse_worker, daemon=True).start()

    def _parse_worker(self):
        try:
            results = parser.process_pending(self.force_var.get(), self.log)
            n_files = len({r["stem"] for r in results})
            if results:
                self.log(f"✅ 全部完成：成功 {n_files} 个文件，结果在 workspace\\output\\", "done")
                self.log("请到核对区逐项核对，确认后点「③ 归档」")
            else:
                self.log("✅ 没有新文件需要解析", "done")
        except Exception as e:
            self.log(f"❌ 出错：{e}", "error")
        finally:
            self.busy = False
            self.root.after(0, self._set_buttons, True)
            self.root.after(0, self.refresh_checklist)

    def on_archive(self):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)
        self.log("──── 归档已核对确认的文件 ────")
        threading.Thread(target=self._archive_worker, daemon=True).start()

    def _archive_worker(self):
        try:
            moved, left = parser.archive_processed(self.log)
            if left:
                self.log(f"✅ 归档完成：移入 done\\ {moved} 个；pending 还有 {left} 个未确认/未解析", "done")
            else:
                self.log(f"✅ 归档完成：移入 done\\ {moved} 个", "done")
        except Exception as e:
            self.log(f"❌ 出错：{e}", "error")
        finally:
            self.busy = False
            self.root.after(0, self._set_buttons, True)
            self.root.after(0, self.refresh_checklist)

    def _open_folder(self, path):
        try:
            os.startfile(str(path))
        except OSError as e:
            self.log(f"❌ 无法打开文件夹：{e}", "error")


def main():
    root = tk.Tk()
    Panel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
