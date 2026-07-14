---
name: gobe-ip-illustrations
description: 使用可替换的个人 IP 参考图，把中文文章中的判断、流程、状态和隐喻生成成套白底手绘配图。用于规划或生成 2.36:1 封面、16:9 正文图和 4:5 总结图，以及通过 Python 控制已登录的 ChatGPT 网页、一次上传 IP 图片、提交最多 10 张的批量任务、自动下载并删除临时任务时；不使用 OpenAI API。
---

# GOBE IP 文章配图

把中文文章变成白底、手绘、怪诞但清爽的连续配图。使用 `references/ip/` 中的图片定义人物；替换这组图片时，文章分析、构图方法和提示模板保持不变。

## 参考图输入

递归读取 `references/ip/` 中的 PNG、JPG、JPEG 和 WEBP。把这些图片作为同一个个人 IP 的身份参考一次上传，不使用纯文字猜测人物。

- 正式图片放入 `references/ip/source/`。
- HEIC 等网页上传不稳定的原件保存在 `references/ip/originals/`，另存兼容副本到 `source/`。
- 更换 IP 时直接替换 `references/ip/` 的整组图片，不混入旧人物。
- 可选风格图片放入 `references/style/`；IP 图控制“是谁”，风格图控制“怎么画”。

可运行以下脚本查看程序将使用的参考图路径：

```bash
python3 <skill-dir>/scripts/list_reference_images.py <skill-dir>/references/ip
```

## 按需读取资源

- 先读 `references/index.md` 了解目录。
- 涉及参考图时读 `references/workflow/reference-image-contract.md`。
- 组织批量任务时读 `references/workflow/batch-generation-contract.md`。
- 规划前读 `references/style/style-dna.md`、`references/composition/patterns.md` 和 `references/output/roles.md`。
- 写提示词时读 `references/prompt/template.md` 和 `references/prompt/batch-template.md`。
- 需要无人物示例时读 `references/examples/`。

## 工作流

### 1. 提炼文章

提取核心判断、读者问题、论证转折、流程、状态、对比和强隐喻。围绕认知锚点配图，不为每个小节机械配一张。

### 2. 生成视觉计划

默认规划：

- 1 张封面：2.36:1。
- N 张正文配图：16:9。
- 1 张总结图：4:5，用户可以覆盖。

总数最多 10 张，封面和总结图计入。每张图写清资产角色、来源章节、核心意思、具体场景、人物动作、构图、短标签和目标文件名。场景要能直接画出来，同时允许模型在道具、姿势、细节和隐喻表达上自由发挥。

### 3. 组装一次性批量提示词

使用 `references/prompt/batch-template.md` 合并：

- 全局 IP 身份说明
- 白底手绘风格
- 全部编号任务
- 独立图片而非拼贴的输出要求

把全部编号任务放入一个提示词，不在生成过程中插入追加问题、人工确认或逐张返工。

### 4. 使用 Python 控制 ChatGPT 网页

先确认 Chrome 已登录 ChatGPT，并且 OpenCLI Browser Bridge 可用：

```bash
python3 <browser-skill-dir>/scripts/chatgpt_chrome_image.py doctor
```

再运行本项目的调度程序：

```bash
python3 <skill-dir>/scripts/generate_with_chatgpt_web.py \
  --prompt-file <batch-prompt.md> \
  --plan-file <visual-plan.json> \
  --reference-dir <skill-dir>/references/ip \
  --output-dir <output-folder> \
  --json
```

程序会：

1. 递归找到并按文件内容去重参考图。
2. 打开保留登录态的 ChatGPT 网页新任务，不修改用户手动设置的模型与思考程度，并明确切到“创建图片”。
3. 把整组 IP 图片一次挂到网页上传框，再一次发送完整批量提示词。
4. 等待这次任务结束，下载当前任务中返回的图片。
5. 按 `visual-plan.json` 的顺序改成规划文件名，并写入技术运行清单。
6. 只在下载数量与规划数量一致后，才永久删除这次 ChatGPT 临时任务；数量不足时保留任务以便恢复下载。

默认不需要 API Key。使用 `--dry-run --json` 可只解析提示词、视觉计划和参考图，不操作网页。明确传入 `--keep-thread` 时始终保留网页任务；即使没有传入，批次不完整时也不会删除。

### 5. 浏览器底座

网页动作由同仓库的 `gobe-chatgpt-chrome-image` Skill 执行。它使用 Chrome 登录态与 OpenCLI Browser Bridge，不读取或保存 ChatGPT 密码。网页结构变化时优先更新这个底层 Skill，文章理解与提示模板无需跟着改。

### 6. 直接交付，不做画面检查

图片保存后直接报告输出目录和文件清单。默认不执行以下动作：

- 不逐张打开或人工评审图片。
- 不核对人物、文字、构图、比例或颜色。
- 不做自动评分、二次提示、返工或重生成。
- 不为了检查而建立额外对话或模型调用。

只处理会阻止程序完成的技术错误，例如浏览器桥接断开、登录失效、上传失败、网页生成超时、没有可保存的图片或本地写入失败。除非用户另行要求，不运行 `fit_canvas.py`；画幅交给提示词与图像模型自由完成。

## 公开示例

`references/examples/` 只保存无人物、无对话记录的文字示例：示例文章、视觉计划和一次性批量提示词。真实 IP 图、生成成品、运行清单和 ChatGPT 任务记录不纳入公开 Skill。

## 不变量

- IP 身份与画风分开控制。
- 更换 IP 图片时，不重写文章分析和提示模板。
- `references/ip/` 是个人 IP 图片的正式入口。
- 生图入口固定为已登录的 ChatGPT 网页，不使用 OpenAI API。
- 只有完整下载规划数量后，才默认删除本次临时 ChatGPT 任务。
- 模型与思考程度由用户在 ChatGPT 网页手动设置，程序不得改动；程序必须明确进入“创建图片”后再上传参考图和发送批量提示词。
- 发布仓库前确认参考图片拥有使用权与再分发权。
- 保留第三方方法来源与许可说明，见 `NOTICE.md`。
