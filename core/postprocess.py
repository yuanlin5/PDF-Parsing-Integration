"""md 后处理：把 MinerU 输出的 HTML 表格转成标准 Markdown 表格。

MinerU 3.x 对表格内容输出 `<table><tr><td ...>...</td></tr></table>` 写法，
WPS 的 Markdown 渲染器不认识 HTML 标签，会把源码原样显示。
本模块在解析完成后原地转换，保证 WPS/浏览器/后续流程都能正常显示表格。
"""

import re
from html.parser import HTMLParser
from pathlib import Path

_TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL)
_IMG_RE = re.compile(r"<img\s+src=[\"']([^\"']+)[\"'][^>]*>")


class _TableParser(HTMLParser):
    """提取一个 <table> 块的行列结构。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)  # 自动解析 &#x27; 等实体
        self.rows: list = []
        self._cells = None
        self._buf = None
        self._rowspan = 1
        self._colspan = 1
        self.has_rowspan = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._cells = []
        elif tag in ("td", "th") and self._cells is not None:
            self._buf = []
            self._rowspan = int(a.get("rowspan", 1))
            self._colspan = int(a.get("colspan", 1))
            if self._rowspan > 1:
                self.has_rowspan = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._buf is not None:
            self._cells.append((self._buf, self._colspan))
            self._buf = None
        elif tag == "tr" and self._cells is not None:
            self.rows.append(self._cells)
            self._cells = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


def _table_block_to_md(block: str) -> str | None:
    """单个 <table>…</table> 块 → Markdown 表格；不支持的结构返回 None（保持原样）。"""
    parser = _TableParser()
    parser.feed(block)
    if not parser.rows:
        return None
    if parser.has_rowspan:
        return None  # 跨行单元格结构复杂，保持 HTML 原样

    flat: list[list[str]] = []
    max_cols = 0
    for cells in parser.rows:
        line: list[str] = []
        for buf, colspan in cells:
            text = "".join(buf).replace("\n", " ").strip()
            text = text.replace("|", "\\|")
            line.extend([text] * colspan)  # 跨列按重复内容展开
        max_cols = max(max_cols, len(line))
        flat.append(line)

    out = []
    for i, line in enumerate(flat):
        line += [""] * (max_cols - len(line))
        out.append("| " + " | ".join(line) + " |")
        if i == 0:
            out.append("|" + "---|" * max_cols)
    return "\n".join(out)


def convert_html_tables(text: str) -> str:
    """把 md 文本里的 HTML 表格转换为 Markdown 表格。"""
    text = _IMG_RE.sub(r"![](\1)", text)
    return _TABLE_RE.sub(lambda m: _table_block_to_md(m.group(0)) or m.group(0), text)


def process_file(md_path: Path) -> bool:
    """原地转换一个 md 文件；有改动返回 True。"""
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    new = convert_html_tables(text)
    if new != text:
        md_path.write_text(new, encoding="utf-8")
        return True
    return False
