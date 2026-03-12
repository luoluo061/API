# Web LLM Adapter

`web-llm-adapter` 是一个基于 Playwright 的网页版大模型调用适配层。

它的目标不是替代官方 API，也不是做普通爬虫或普通浏览器自动化，而是把“人工在网页上使用大模型”这件事，封装成上层系统可以稳定调用的内部能力。

当前首版已经验证的主链路是：
- 手工启动并保持一个已登录的 Edge 浏览器
- 服务通过 `connect_over_cdp` 连接该浏览器
- 发送真实 prompt 到豆包网页
- 等待网页回答完成
- 结构化提取结果并通过 `/chat` 返回

## 项目定位

这个项目不是：
- 官方模型 API SDK
- 通用爬虫框架
- 面向公开互联网抓取的采集系统
- 模型训练或推理服务

这个项目是：
- 一个浏览器驱动型模型调用适配器
- 一个对上层暴露统一调用入口的中间层
- 一个把网页模型能力封装成 skill 或 HTTP API 的工程化方案

适用场景：
- 某些模型网页版可用，但官方 API 不开放、不好接或接入成本高
- 需要先验证业务流程，而不是立即投入正式 API 集成
- 上层 Agent / Workflow 需要统一入口，不希望业务直接处理网页细节
- 需要把现有网页模型能力先服务化、接口化，作为内部工具或过渡方案

## 当前首版结论

当前项目的默认主路径已经收敛到 `CDP` 模式。

原因很明确：
- 直接用 `launch_persistent_context` 接管本地 profile，在当前豆包场景下不稳定
- “母本 profile + 运行时副本 profile” 在本机验证中也不是可靠主路径
- `CDP + 手工保持打开的已登录 Edge` 已经验证可稳定完成真实发送与回答提取

因此当前默认模式是：
- `browser_mode = cdp`
- 默认连接 `http://127.0.0.1:9222`
- 默认浏览器为本机手工打开并保持登录状态的 Edge

`launch`、`persistent profile`、`clone profile` 相关逻辑仍保留在代码中，作为备选实验路径，但不再是 README 主流程。

## 系统架构

整体链路：

```text
上层业务 / Agent / Workflow
        ↓
统一 skill / HTTP API
        ↓
Web LLM Adapter
        ↓
Playwright / CDP 浏览器接入层
        ↓
豆包网页版
```

项目内部职责大致分为三层：
- API 层：`/chat`、`/profiles/verify`、`/health`
- 执行编排层：浏览器连接、串行执行、超时、日志、trace、截图
- Provider 层：豆包页面操作、完成态识别、结果提取、异常识别

## 当前能力

当前已经实现并验证的能力包括：
- `GET /health`：系统级健康检查
- `POST /profiles/verify`：验证 CDP 浏览器可连、豆包登录有效、页面可交互
- `POST /chat`：真实发送 prompt 并返回回答
- 豆包 provider 的页面加载、输入、发送、等待、提取流程
- 结构化 Markdown 提取
- 失败截图、HTML 快照、请求日志、可选 trace
- 单 worker 串行执行模型调用
- `mock mode`，用于不连接真实浏览器时验证接口链路

### 已验证场景

已在本机验证通过的典型场景：
- 普通短答
- 中文输入
- 长回答
- 联网类回答
- 代码块回答
- Markdown 列表回答

当前返回结果不只是纯文本可读，已经能在大多数常见场景下保留基本 Markdown 结构，例如：
- `pre/code` -> fenced code block
- `ul/ol/li` -> Markdown 列表
- `h1/h2/h3` -> Markdown 标题
- `a` -> 链接文本，并抽取到 `references`
- `blockquote` -> Markdown 引用
- `strong/em` -> 基础行内格式

## 完成态与提取策略

为了降低“过早截断”的风险，当前 provider 不是看到页面有内容就立即返回，而是采用多层保险：

1. 等待回答进入完成态
- 识别回答底部功能框 `message_action_bar`
- 识别复制按钮 `message_action_copy`
- 识别重新生成按钮 `message_action_regenerate`
- 检查“停止生成”按钮是否已经消失
- 结合文本稳定轮询判断页面是否已经完成输出

2. 优先做 DOM 结构化提取
- 以 `receive_message -> message_text_content` 为主入口
- 将真实回答节点序列化为 Markdown 友好的块结构

3. 结构化结果异常时触发兜底
- 若结构化结果明显偏短或为空，尝试复制按钮 fallback
- 若复制仍不可用，则退回 settled plain text

4. 记录提取路径与完成态信号
- `usage_like_meta.extraction_path`
- `usage_like_meta.completion_signals`

## 快速开始

### 1. 准备环境

要求：
- Windows
- Python 3.12+
- Microsoft Edge
- 已安装 Playwright Python 包

安装依赖：

```powershell
cd E:\API
py -m pip install -e .
```

### 2. 启动一个已登录的 Edge（CDP 模式）

使用专用 `user-data-dir` 启动 Edge，并保持窗口打开：

```powershell
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --remote-debugging-port=9222 --user-data-dir="E:\API\.profiles\masters\doubao-edge" "https://www.doubao.com/chat/"
```

然后在这个窗口中：
- 登录豆包
- 手工发送一条消息并确认能收到回复
- 保持这个 Edge 窗口不要关闭

### 3. 检查 9222 端口

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

预期：
- 能返回 JSON
- JSON 中包含 `webSocketDebuggerUrl`

### 4. 启动服务

```powershell
cd E:\API
$env:WEB_LLM_BROWSER_MODE = "cdp"
$env:WEB_LLM_CDP_URL = "http://127.0.0.1:9222"
$env:WEB_LLM_MASTER_PROFILE_DIR = "E:\API\.profiles\masters\doubao-edge"
$env:WEB_LLM_TRACE_MODE = "failure"
$env:WEB_LLM_MOCK_MODE = "0"
py -m uvicorn web_adapter.main:app --host 127.0.0.1 --port 8000
```

说明：
- `WEB_LLM_BROWSER_MODE` 当前默认就是 `cdp`
- `WEB_LLM_TRACE_MODE=failure` 表示失败时保存 trace
- `WEB_LLM_MOCK_MODE=0` 表示启用真实浏览器链路

## 接口说明

### `GET /health`

用于系统级健康检查，不发送真实 prompt。

主要关注：
- CDP 端口是否可连
- 浏览器上下文是否存在
- 当前服务配置是否有效
- provider 是否处于可验证状态

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### `POST /profiles/verify`

用于验证：
- 能否连上当前 CDP 浏览器
- 豆包登录态是否有效
- 聊天页面是否已就绪

示例：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/profiles/verify" -ContentType "application/json" -Body '{"provider":"doubao"}'
```

成功时通常返回：
- `status = ok`
- `login_state = logged_in`
- `artifacts.page_url` 指向豆包聊天页

### `POST /chat`

统一调用入口。

最小示例：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/chat" -ContentType "application/json" -Body '{"provider":"doubao","prompt":"Reply with exactly OK."}'
```

典型成功返回：
- `status = ok`
- `content` 为真实网页回答
- `usage_like_meta.content_format` 为 `markdown` 或 `text`
- `usage_like_meta.extraction_path` 说明最终采用了哪条提取路径
- `artifacts.page_url` 指向真实会话页

## 返回结果中的关键信息

`/chat` 当前会返回这些核心字段：
- `content`：主回答内容
- `usage_like_meta.content_format`：`markdown` 或 `text`
- `usage_like_meta.blocks`：结构化块信息
- `usage_like_meta.references`：参考链接
- `usage_like_meta.extraction_path`：`structured`、`copy_fallback`、`settled_text_fallback`
- `usage_like_meta.completion_signals`：完成态判定信号

这使上层系统既可以直接消费 `content`，也可以根据 `blocks` / `references` 做更细粒度处理。

## 错误码

当前重点错误码包括：
- `cdp_unreachable`：无法连接到 `WEB_LLM_CDP_URL`
- `login_required`：豆包要求重新登录，或页面出现登录信号
- `provider_timeout`：在超时前没有检测到稳定回答
- `extract_empty`：回答流程结束，但提取结果为空
- `page_not_ready`：页面打开了，但输入区域不可用

其他保留错误码：
- `master_profile_missing`
- `profile_locked`
- `runtime_profile_copy_failed`
- `browser_unavailable`
- `page_navigation_failed`
- `send_failed`
- `selector_not_found`

## 诊断与排障

每次请求都会在 `.artifacts/<timestamp>-<request_id>/` 下写入诊断信息。

优先看：
- `request.log`：执行时间线、错误码、完成态、提取路径
- `failure.png`：失败时页面截图
- `page.html`：失败时 DOM 快照
- `trace.zip`：开启 trace 后的 Playwright 轨迹

如果返回不符合预期，建议优先检查：
1. `request.log` 里的 `completion_signals`
2. `request.log` 里的 `extraction_path`
3. 是否发生了 `structured_result_short` 或 `copy_fallback_*`
4. `failure.png` 与 `page.html` 是否显示页面结构变化

## 环境变量

核心变量：
- `WEB_LLM_BROWSER_MODE`：`cdp` 或 `launch`，默认 `cdp`
- `WEB_LLM_CDP_URL`：默认 `http://127.0.0.1:9222`
- `WEB_LLM_MASTER_PROFILE_DIR`：手工启动 Edge 时使用的专用 profile 目录
- `WEB_LLM_TRACE_MODE`：`off`、`failure`、`always`
- `WEB_LLM_MOCK_MODE`：`1` 表示跳过真实浏览器
- `WEB_LLM_REQUEST_TIMEOUT_SECONDS`：请求超时
- `WEB_LLM_QUEUE_WAIT_SECONDS`：队列等待超时
- `WEB_LLM_ARTIFACT_DIR`：诊断目录

实验性变量：
- `WEB_LLM_HEADLESS`
- `WEB_LLM_PROFILE_MODE`
- `WEB_LLM_RUNTIME_PROFILE_ROOT`
- `WEB_LLM_RUNTIME_PROFILE_RETENTION`
- `WEB_LLM_BROWSER_CHANNEL`

## 项目边界

这个项目的目标不是提供官方 API 级别的稳定性。

需要明确的边界：
- 依赖网页 DOM 结构，页面改版会影响 provider
- 依赖登录态和当前浏览器环境
- 稳定性通常不如官方 API
- 更适合内部工具、验证方案、过渡方案和补充能力

因此当前工程目标是：
- 在明确边界前提下做到可用
- 让上层不直接依赖网页细节
- 让 provider 能被复用、替换、扩展
- 为后续多 provider 接入保留抽象层

## 当前代码结构

核心目录：
- `src/web_adapter/main.py`：应用入口
- `src/web_adapter/service.py`：服务编排与接口逻辑
- `src/web_adapter/browser.py`：浏览器接入与 CDP/launch 模式
- `src/web_adapter/providers/doubao.py`：豆包 provider
- `tests/`：单测与基础回归

## 当前状态

当前仓库已经具备一个可运行的首版：
- 可以通过 README 复现 CDP 链路
- 可以对豆包进行真实发送和真实提取
- 可以返回 Markdown 基本保真的回答结果
- 已经具备基础错误码、日志、截图、trace 和验证接口

如果后续继续演进，最自然的方向是：
- 增强多 provider 抽象
- 继续提升结构化提取质量
- 增加更强的回归测试和运维可观测性
