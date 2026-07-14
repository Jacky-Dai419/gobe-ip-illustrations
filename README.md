# GOBE IP Illustrations

把中文文章中的判断、流程、状态和隐喻，变成一组白底、手绘、怪诞但清爽的文章配图。人物身份由本地参考图决定；替换参考图即可替换 IP，文章分析、构图方法和批量工作流无需重写。

默认支持：

- 2.36:1 横版封面。
- 16:9 横版正文配图。
- 4:5 总结图。
- 一次上传整组 IP 参考图。
- 一次提交最多 10 个独立生图任务。
- 通过已登录的 ChatGPT 网页生成、批量下载，不使用 OpenAI API。
- 仅在规划图片已全部下载后删除临时 ChatGPT 任务。

## 仓库结构

```text
skills/
├── gobe-ip-illustrations/       # 文章拆解、视觉计划与批量提示词
└── gobe-chatgpt-chrome-image/  # ChatGPT 网页上传、等待、批量下载与任务清理
```

这两个 Skill 需要一起安装。上层 Skill 负责“画什么”，底层 Skill 负责“如何在网页上完成这一批”。

## 安装

1. 安装 Python 3.10+、Node.js 18+ 和兼容的 OpenCLI 命令行工具。
2. 安装 OpenCLI Chrome Browser Bridge 扩展，并在 Chrome 中登录 `chatgpt.com`。
3. 把 `skills/` 下的两个目录复制到你的 Skill 目录，例如 `~/.codex/skills/`。
4. 首次使用前运行：

```bash
python3 ~/.codex/skills/gobe-chatgpt-chrome-image/scripts/chatgpt_chrome_image.py doctor
```

如果 OpenCLI 不在系统 `PATH` 中，可设置 `OPENCLI_BIN`；如果 Node.js 不在 `PATH` 中，可设置 `NODE_BIN`。上传帮助程序无法自动定位 OpenCLI 模块时，可用 `OPENCLI_BROWSER_MODULE` 指向它的 `dist/src/browser/index.js`。

## 放入你的 IP 参考图

把同一人物的 PNG、JPG、JPEG 或 WEBP 图片放入：

```text
skills/gobe-ip-illustrations/references/ip/source/
```

生图时必须把这组图片真正上传到 ChatGPT，并明确要求严格使用该人物、保留其原始特征。不要只用文字猜测人物。

仓库默认忽略该目录中的图片。不要将个人照片、未授权 IP、ChatGPT 任务清单或下载成品提交到公开仓库。

## 最小运行方式

先参考 `skills/gobe-ip-illustrations/references/examples/`中的文章、视觉计划和批量提示词，然后运行：

```bash
python3 ~/.codex/skills/gobe-ip-illustrations/scripts/generate_with_chatgpt_web.py \
  --prompt-file /path/to/batch-prompt.md \
  --plan-file /path/to/visual-plan.json \
  --reference-dir ~/.codex/skills/gobe-ip-illustrations/references/ip \
  --output-dir /path/to/output \
  --json
```

先用 `--dry-run --json` 可验证文件、计划数量与参考图路由，不会操作网页。

## 隐私与发布边界

这个公开包不包含：

- 个人 IP 图片或人像。
- 带个人形象的生成成品。
- ChatGPT 对话地址、对话 ID、运行清单或清理回执。
- 本机绝对路径、账号、密码、Cookie 或 API 密钥。

发布前可运行：

```bash
python3 scripts/privacy_scan.py .
```

## 稳定性说明

这是一个基于网页界面的社区工作流，不是 OpenAI 官方 API 客户端。ChatGPT 网页、生图入口或图片画廊结构变化时，可能需要更新 `gobe-chatgpt-chrome-image`。请遵守你所使用服务的条款与所在地法律。

## 许可与来源

本项目使用 MIT License。工作流与视觉系统的初始启发来自 [helloianneo/ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations)，详见 [NOTICE.md](NOTICE.md)。本仓库不包含上游的小黑角色或示例图片。
