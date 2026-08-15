"""PDF 解析面板 — 双击 start_panel.bat 启动。

两个阶段各一个按钮：
  ① 开始解析  pending 里的文件逐个交给 MinerU（大 PDF 自动分批）
  ② 归档      把 pending 里已解析成功的文件移入 done\，保持待处理区干净
"""

import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from core import config
from core import parser

USAGE = """【使用方法】
① 把 PDF / 图片 放进 workspace\\pending 文件夹（可用子文件夹分项目）
② 点「① 开始解析」，等日志出现"全部完成"（CPU 解析，大文件请耐心等待，
   超过 30 页的 PDF 会自动按 15 页/批切分）
③ 解析成功后点「② 归档」，把 pending 里已完成的文件移入 workspace\\done\\
④ 解析结果在 workspace\\output\\<文件名>\\ 里，文字内容为 auto\\<文件名>.md，
   图片在 auto\\images\\ 下

提示：解析失败的文件会移入 workspace\\pending\\failed\\，可从那里取回重试。
勾选「包含已解析过的文件」可强制重新解析。"""


class Panel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.busy = False
        self.force_var = tk.BooleanVar(value=False)
        self.msg_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        config.ensure_dirs()
        self._build_ui()
        self._poll_queue()

    # ── 界面构建 ──────────────────────────────────────────

    def _build_ui(self):
        self.root.title(f"{config.APP_NAME} 面板  v{config.VERSION}")
        self.root.geometry("860x680")
        self.root.minsize(760, 560)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))

        # 按钮区
        bar = ttk.Frame(self.root, padding=(12, 10))
        bar.pack(fill=tk.X)

        self.btn_parse = ttk.Button(bar, text="① 开始解析", command=self.on_parse)
        self.btn_parse.pack(side=tk.LEFT)
        self.btn_archive = ttk.Button(bar, text="② 归档", command=self.on_archive)
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
        # 新一轮运行：清空状态文件
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
                self.log("提示：点「② 归档」可把 pending 里已完成的文件移入 done\\")
            else:
                self.log("✅ 没有新文件需要解析", "done")
        except Exception as e:
            self.log(f"❌ 出错：{e}", "error")
        finally:
            self.busy = False
            self.root.after(0, lambda: self._set_buttons(True))

    def on_archive(self):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)
        self.log("──── 归档已解析完成的文件 ────")
        threading.Thread(target=self._archive_worker, daemon=True).start()

    def _archive_worker(self):
        try:
            moved, left = parser.archive_processed(self.log)
            self.log(f"✅ 归档完成：移入 done\\ {moved} 个，pending 剩余 {left} 个", "done")
        except Exception as e:
            self.log(f"❌ 出错：{e}", "error")
        finally:
            self.busy = False
            self.root.after(0, lambda: self._set_buttons(True))

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
