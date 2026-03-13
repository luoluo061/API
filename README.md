# Web LLM Adapter

`web-llm-adapter` 是一个基于 Playwright 的网页版大模型调用适配层，目标是把“人工在网页上使用模型”的过程封装成上层系统可调用的稳定接口。

当前首版默认主路径已经冻结为：
- 手工启动并保持一个已登录的 Edge 浏览器
- 服务通过 `connect_over_cdp` 连接该浏览器
- 使用豆包网页完成真实发送、等待与提取
- 通过统一 `/chat` 接口向上层返回结构化结果

这个项目不是官方 API SDK，也不是通用爬虫。它更像一个“浏览器驱动型模型调用网关”。

## 首版定位

这个项目适合以下场景：
- 网页版模型可用，但官方 API 不开放或接入成本高
- 需要快速验证业务流程，而不是先做重型集成
- 上层 Agent / Workflow 需要统一入口，不希望直接处理网页细节
- 需要把网页上的模型能力先服务化，作为内部工具或过渡方案

当前首版默认口径：
- 默认浏览器模式：`CDP`
- 默认连接地址：`http://127.0.0.1:9222`
- 默认 provider：`doubao`
- 默认调用方式：`POST /chat`

当前已验证的兼容层能力：
- `GET /v1/models`
- `POST /v1/chat/completions`
- OpenAI-compatible 非流式响应
- OpenAI-compatible SSE 流式响应
- Continue 作为 OpenAI provider 的真实接入

`launch` 和 persistent profile 相关实现仍保留在代码里，但不再作为默认主路径。

## Quick Start

### 1. 下载后先做什么

```powershell
cd E:\API
py -m pip install -e .[dev]
Copy-Item .env.example .env
```

默认情况下，关键路径会按项目根目录解析，不再依赖当前 working directory。

### 2. 准备已登录的豆包浏览器 / CDP

```powershell
.\scripts\open_doubao_cdp.ps1
```

然后在打开的 Edge 里：
- 登录豆包
- 手工发送一条消息，确认网页能正常收到回答
- 保持该窗口不要关闭

检查 CDP 是否可连：

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

### 3. 启动服务

```powershell
.\scripts\start_server.ps1
```

启动时服务会打印实际解析出的关键配置，包括：
- `project_root`
- `master_profile_dir`
- `runtime_profile_root`
- `artifact_dir`
- `browser_mode`
- `cdp_url`
- `host`
- `port`

### 4. 验证 `/health` 和 `/v1/models`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/v1/models
```

预期：
- `/health` 返回服务状态，且在 CDP 正常时 `browser.status = ok`
- `/v1/models` 返回固定模型名 `doubao-web`

### 5. 调用 `/v1/chat/completions`

PowerShell：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/chat/completions" -ContentType "application/json" -Headers @{ Authorization = "Bearer dummy" } -Body '{"model":"doubao-web","messages":[{"role":"user","content":"Reply with exactly OK."}],"stream":false}'
```

### 6. 配置 Continue

`C:\Users\tang7\.continue\config.yaml`

```yaml
name: Local Config
version: 1.0.0
schema: v1

models:
  - name: Doubao Web
    provider: openai
    model: doubao-web
    apiBase: http://127.0.0.1:8000/v1
    apiKey: dummy
    roles:
      - chat
```

## 系统架构

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

内部职责：
- API 层：`/chat`、`/profiles/verify`、`/health`
- 编排层：浏览器连接、串行执行、超时、日志、trace、截图
- Provider 层：豆包页面操作、完成态识别、结果提取、异常识别

## 当前能力

已实现并验证的能力：
- `GET /health`：系统级健康检查
- `POST /profiles/verify`：验证 CDP 浏览器可连、登录有效、聊天页可交互
- `POST /chat`：真实发送 prompt 并返回回答
- Markdown 基本保真的回答提取
- 参考链接抽取
- 失败截图、HTML 快照、请求日志、可选 trace
- 单 worker 串行执行

已验证样例：
- 短答
- 长答
- 联网回答
- 代码块回答
- Markdown 列表回答

固定验收样例见：[docs/acceptance-samples.md](E:\API\docs\acceptance-samples.md)

## 默认主路径：CDP

### 1. 启动已登录 Edge

推荐直接用脚本：

```powershell
.\scripts\open_doubao_cdp.ps1
```

等价的手工方式如下：

```powershell
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --remote-debugging-port=9222 --user-data-dir="E:\API\.profiles\masters\doubao-edge" "https://www.doubao.com/chat/"
```

在这个窗口里：
- 登录豆包
- 手工发送一条消息，确认能收到回复
- 保持该 Edge 窗口不要关闭

### 2. 检查 9222

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

预期：
- 返回 JSON
- JSON 中包含 `webSocketDebuggerUrl`

### 3. 启动服务

推荐直接用脚本：

```powershell
.\scripts\start_server.ps1
```

等价的手工方式如下：

```powershell
cd E:\API
py -m pip install -e .
$env:BROWSER_MODE = "cdp"
$env:CDP_URL = "http://127.0.0.1:9222"
$env:MASTER_PROFILE_DIR = ".profiles/masters/doubao-edge"
$env:TRACE_MODE = "failure"
$env:MOCK_MODE = "0"
$env:PYTHONPATH = "src"
py -m uvicorn web_adapter.main:app --host 127.0.0.1 --port 8000
```

说明：
- 当前版本默认按项目根目录解析相对路径
- 不再依赖当前 working directory 去解析 `.profiles\masters\doubao-edge`
- 标准启动方式仍然建议使用项目根目录下的脚本

## 本地测试

安装开发依赖：

```powershell
cd E:\API
py -m pip install -e .[dev]
```

运行测试：

```powershell
py -m pytest
```

说明：
- 仓库已在 `pyproject.toml` 中配置 `src` 作为测试导入路径
- 如果本机没有把 Python Scripts 目录加入 `PATH`，优先使用 `py -m pytest`，不要依赖裸 `pytest`

OpenAI-compatible 兼容层测试：

```powershell
py -m pytest tests/test_openai_compat.py -q
```

## 接口

### `GET /health`

`/health` 只做系统级预检，不发送真实 prompt。

在默认 CDP 模式下，它主要表达：
- 服务是否存活
- `127.0.0.1:9222` 是否可连
- 浏览器上下文是否可见
- provider 下一步是否应该用 `/profiles/verify` 验证登录与页面状态

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### `POST /profiles/verify`

`/profiles/verify` 是默认主路径下的真实浏览器验证步骤。

它会验证：
- 能否附着到当前已打开的 CDP 浏览器
- 豆包登录态是否有效
- 聊天页是否已经就绪

示例：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/profiles/verify" -ContentType "application/json" -Body '{"provider":"doubao"}'
```

成功时通常返回：
- `status = ok`
- `login_state = logged_in`
- `diagnostics.browser_mode = cdp`
- `diagnostics.page_ready = true`

### `POST /chat`

`/chat` 是首版对上层系统的正式主接口。

最小调用示例：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/chat" -ContentType "application/json" -Body '{"provider":"doubao","prompt":"Reply with exactly OK."}'
```

### `GET /v1/models`

最小 OpenAI-compatible 模型列表接口。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/models
```

当前首版固定只返回一个外部模型名：
- `doubao-web`

### `POST /v1/chat/completions`

最小 OpenAI-compatible 聊天接口。

当前已验证：
- 支持 `model = doubao-web`
- 支持 `stream = true`
- 返回 SSE `chat.completion.chunk`
- 可被 Continue 作为 OpenAI provider 真实消费

最小示例：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/chat/completions" -ContentType "application/json" -Body '{"model":"doubao-web","messages":[{"role":"user","content":"Reply with exactly OK."}],"stream":false}'
```

流式示例：

```powershell
$body = '{"model":"doubao-web","messages":[{"role":"user","content":"Reply with exactly OK."}],"stream":true}'
Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8000/v1/chat/completions" -ContentType "application/json" -Headers @{ Authorization = "Bearer dummy" } -Body $body
```

`curl` 示例：

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d "{\"model\":\"doubao-web\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly OK.\"}],\"stream\":false}"
```

Python `requests` 示例：

```python
import requests

response = requests.post(
    "http://127.0.0.1:8000/v1/chat/completions",
    headers={"Authorization": "Bearer dummy"},
    json={
        "model": "doubao-web",
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
        "stream": False,
    },
    timeout=120,
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])
```

## Continue 接入

Continue 首轮验证已通过，当前正确配置如下：

`C:\Users\tang7\.continue\config.yaml`

```yaml
name: Local Config
version: 1.0.0
schema: v1

models:
  - name: Doubao Web
    provider: openai
    model: doubao-web
    apiBase: http://127.0.0.1:8000/v1
    apiKey: dummy
    roles:
      - chat
```

已验证的真实链路：
- Continue 发出 `POST /v1/chat/completions`
- `user-agent = OpenAI/JS 5.23.2`
- `stream = true`
- 服务端进入豆包 provider
- 豆包真实返回
- 服务端以 SSE 返回
- Continue 正常显示回答
- Continue 会自动再发一个标题请求，当前也已验证成功

当前已验证的样例包括：
- `Reply with exactly OK.`
- `Reply with exactly YES.`
- `Reply with exactly HELLO.`
- `Reply in one short sentence: what is 2+2?`
- `Give me 3 short bullet points about apples.`

说明：
- Continue 会自动携带自己的 `system` 提示词模板
- 当前兼容层会把 `messages` 压平成单个 prompt，再送入网页 provider
- 因此豆包网页输入框里会看到 `System: ...` / `User: ...` 文本
- 这不影响当前 Phase 1 的协议兼容验证结论，只是后续可优化的映射策略

## `/chat` 响应协议

当前首版已经冻结以下字段：
- `request_id`
- `status`
- `provider`
- `content_markdown`
- `blocks`
- `usage_like_meta.references`
- `artifacts`
- `diagnostics`

兼容字段：
- `content`
  当前仍保留，值与 `content_markdown` 相同，仅作为兼容输出。

### 字段说明

#### `content_markdown`
主回答字段，供上层直接消费。

首版默认约定：
- 成功时优先返回 Markdown 可读结果
- 对短答、列表、代码块、常见联网总结都可直接显示

#### `blocks`
结构化块数组，便于上层按块处理。

当前常见块类型包括：
- `paragraph`
- `heading`
- `list`
- `code_block`
- `blockquote`

补充约定：
- 当页面 DOM 没有显式 `li`，但回答语义明显是多句列表型长答时，适配层可能将其规范化为 `list`
- 因此上层应优先按 `blocks` 消费结构，而不是假设长答一定以单段 `paragraph` 返回

#### `usage_like_meta.references`
参考链接列表，尤其用于联网类回答。

#### `artifacts`
诊断产物位置，包括：
- `request_log_path`
- `failure.png`
- `page.html`
- `trace.zip`
- `page_url`

#### `diagnostics`
首版新增的正式诊断字段。

当前至少包含：
- `extraction_path`
- `content_format`
- `completion_signals`
- `response_length`
- `fallback_used`
- `browser_mode`

## 提取路径

`diagnostics.extraction_path` 当前至少区分：
- `structured`
- `copy_fallback`
- `settled_text_fallback`
- `plain_text_fallback`

当前默认目标是优先走：
- `structured`

如果结构化结果异常偏短，则再尝试：
- `copy_fallback`
- `settled_text_fallback`

## 完成态判定

为了避免过早截断，provider 不是“看到文本就立即返回”，而是会结合以下信号：
- 回答底部功能框 `message_action_bar`
- 复制按钮 `message_action_copy`
- 重新生成按钮 `message_action_regenerate`
- “停止生成”按钮是否已经消失
- 最新回答文本是否稳定

这些信号会写入：
- `diagnostics.completion_signals`

## 常见失败与排查

重点错误码：
- `cdp_unreachable`
- `login_required`
- `provider_timeout`
- `extract_empty`
- `page_not_ready`

建议排查顺序：
1. 看 `request.log`
2. 看 `diagnostics.extraction_path`
3. 看 `diagnostics.completion_signals`
4. 看 `failure.png`
5. 看 `page.html`
6. 看 `trace.zip`

常见问题：
- `cdp_unreachable`
  说明 `9222` 不可达，先检查 Edge 是否按 CDP 模式启动
- `login_required`
  说明浏览器虽然打开，但豆包登录态失效或页面命中登录信号
- `provider_timeout`
  说明 prompt 已发送，但在超时前没有检测到稳定回答
- `extract_empty`
  说明页面流程走完了，但提取不到有效内容
- `page_not_ready`
  说明聊天页打开了，但输入框或发送区域不可用

## 环境变量

核心变量：
- `BROWSER_MODE`：`cdp` 或 `launch`，默认 `cdp`
- `CDP_URL`：默认 `http://127.0.0.1:9222`
- `MASTER_PROFILE_DIR`：默认 `.profiles/masters/doubao-edge`
- `RUNTIME_PROFILE_DIR`：默认 `.profiles/runtime/doubao-edge`
- `ARTIFACT_DIR`：默认 `.artifacts`
- `HOST`：默认 `127.0.0.1`
- `PORT`：默认 `8000`
- `TRACE_MODE`：`off`、`failure`、`always`
- `MOCK_MODE`：`1` 表示跳过真实浏览器
- `REQUEST_TIMEOUT_SECONDS`
- `QUEUE_WAIT_SECONDS`

兼容变量：
- 现有 `WEB_LLM_*` 变量仍可继续使用
- 若同时设置了新变量和 `WEB_LLM_*`，新变量优先

实验性变量：
- `HEADLESS`
- `PROFILE_MODE`
- `RUNTIME_PROFILE_RETENTION`
- `BROWSER_CHANNEL`

## 边界

这个项目不是官方 API 替代品，需要明确边界：
- 依赖网页 DOM 结构
- 依赖登录态和当前浏览器环境
- 稳定性通常不如官方 API
- 更适合内部工具、验证方案、过渡方案和补充能力

当前首版的工程目标是：
- 对上层提供统一接口
- 对下层屏蔽网页细节
- 让网页模型能力可复用、可替换、可扩展
- 为后续多 provider 抽象保留空间
