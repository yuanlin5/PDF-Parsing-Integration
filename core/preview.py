"""预览模块：把解析出的 md 渲染成排版好的 HTML，在浏览器里直观查看。"""

import base64
import os
import re
from pathlib import Path

import markdown

# md 里的图片引用：![xxx](相对路径)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")

_CSS = """
body {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    max-width: 860px;
    margin: 32px auto;
    padding: 0 24px;
    line-height: 1.75;
    color: #24292f;
}
h1, h2, h3, h4 { margin: 1.4em 0 0.6em; border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0.3em; }
img { max-width: 100%; height: auto; border: 1px solid #eee; border-radius: 4px; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #d0d7de; padding: 6px 12px; }
th { background: #f6f8fa; }
blockquote { border-left: 4px solid #d0d7de; margin: 0; padding: 0 1em; color: #57606a; }
code { background: #f6f8fa; padding: 2px 5px; border-radius: 3px; }
pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
"""


def _embed_images(text: str, md_path: Path) -> str:
    """把 md 里的本地图片替换为 base64 内嵌，生成的 HTML 不依赖任何路径。"""
    base = md_path.parent

    def replace(m: re.Match) -> str:
        alt = m.group(1)
        ref = m.group(2)
        img = (base / ref).resolve()
        if not img.is_file():
            return m.group(0)  # 找不到图就保留原样
        try:
            data = img.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"![{alt}](data:image/{img.suffix.lstrip('.') or 'jpeg'};base64,{b64})"
        except OSError:
            return m.group(0)

    return _IMG_RE.sub(replace, text)


def render(md_path: Path) -> Path:
    """把 md 渲染成同目录下的 <名>.preview.html（每次重建保证最新）。"""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    text = _embed_images(text, md_path)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{md_path.stem}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )
    out = md_path.parent / f"{md_path.stem}.preview.html"
    out.write_text(html, encoding="utf-8")
    return out


def open_preview(md_path: Path) -> Path:
    """渲染并在默认浏览器打开，返回 HTML 路径。"""
    html = render(md_path)
    os.startfile(str(html))
    return html
