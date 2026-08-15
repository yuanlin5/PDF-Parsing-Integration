# PDF-Parsing-Integration

PDF 解析面板：把 PDF/图片丢进待处理文件夹，一键调用本机 MinerU 完成解析，解析结果按文件归入输出目录，源文件一键归档。

## 快速开始

1. 双击 `start_panel.bat` 打开面板
2. 把 PDF/图片放进 `workspace\pending\`（可用子文件夹分项目）
3. 点「① 开始解析」，等日志出现"全部完成"
4. 点「② 归档」，把 pending 里已完成的文件移入 `workspace\done\`
5. 解析结果在 `workspace\output\<文件名>\`，文字内容为 `auto\<文件名>.md`，图片在 `auto\images\`

完整说明见面板内的「使用方法」区。

## 目录结构

```
├── panel.py            # 主面板（tkinter）
├── start_panel.bat     # 双击启动
├── core/
│   ├── config.py       # 路径与 MinerU 参数配置
│   └── parser.py       # 扫描 pending + 调用 MinerU（大 PDF 自动分批）+ 归档
├── workspace/          # 工作数据（不入 git，启动自动创建）
│   ├── pending/        # 待处理（失败文件移入 pending\failed\）
│   ├── output/         # MinerU 解析结果
│   └── done/           # 归档：已解析成功的源文件
└── test-pdf1/          # 测试样例（1 个 PDF + 1 张图片）
```

## 环境要求

- **MinerU**：本机已安装（Python312，pipeline 后端，模型已下载），面板按 `core/config.py` 中的路径调用
- **Python 3.12** + `pypdf`（`pip install -r requirements.txt`）

## 注意事项

- 无独立显卡，MinerU 走 CPU pipeline 后端，解析较慢属正常现象；超过 30 页的 PDF 会自动按 15 页/批切分
- 已解析过的文件不会重复解析；如需重跑请勾选面板上的「包含已解析过的文件」
- 解析失败的文件会移入 `workspace\pending\failed\`，可移回 pending 重试
- 归档后若把文件放回 pending，会重新解析
- `test-pdf1` 里的 208MB 大 PDF 超出 GitHub 100MB 限制，未入库（保留在本地）

## 版本

- v1.1.1（2026-08-15）— 收窄为「解析 + 归档」两项功能：移除整理到待解析与录题启动，新增归档按钮
- v1.1.0（2026-08-15）— 首个版本：面板化解析 + 分类整理 + 录题启动
