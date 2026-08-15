"""临时探测脚本：找出 Luti2 SPA 中填空题的题干/答案约定。用完即删。"""
import re

s = open("_spa.js", encoding="utf-8", errors="replace").read()

# 找所有 fill_blank 出现位置
positions = [m.start() for m in re.finditer("fill_blank", s)]
print("total fill_blank occurrences:", len(positions))

# 找渲染/解析填空题答案的线索
pat = re.compile(r".{120}fill_blank.{120}", re.S)
seen = set()
for m in pat.finditer(s):
    ctx = m.group(0)
    if "label" in ctx or "qTe" in ctx or "JTe" in ctx or "XZ" in ctx or "YZ" in ctx:
        continue  # 类型名映射表，跳过
    if ctx not in seen:
        seen.add(ctx)
        print("-----")
        print(ctx)
