# 项目 Roadmap

## 当前状态

项目当前已经完成 V1 主链路验证：
- CDP 接管已登录 Edge
- 豆包网页真实发送、等待、提取
- `/chat` 作为稳定主接口
- `/v1/models` 和 `/v1/chat/completions` 作为最小 OpenAI-compatible shim
- Continue 已完成真实接入验证

本轮新增的工程目标：
- 去掉关键路径对当前 working directory 的依赖
- 提供下载后可直接使用的配置、脚本和文档

## 已验证结论

当前已经真实打通的链路：
- Continue
- `/v1/chat/completions`
- 豆包 provider
- CDP / 已登录浏览器
- SSE 返回
- Continue 正常显示结果

已验证行为：
- Continue `user-agent = OpenAI/JS 5.23.2`
- Continue 使用 `stream = true`
- 主聊天请求成功
- Continue 自动发出的标题请求成功
- 服务端 SSE 结构与最小 OpenAI chunk 形状兼容

## 当前版本运行方式

推荐启动方式：

```powershell
cd E:\API
.\scripts\open_doubao_cdp.ps1
.\scripts\start_server.ps1
```

当前版本默认按项目根目录解析以下关键路径：
- `.profiles/masters/doubao-edge`
- `.profiles/runtime/doubao-edge`
- `.artifacts`

同时支持环境变量覆盖，并兼容旧的 `WEB_LLM_*` 变量。

## 下一步顺序

### 1. 冻结并整理 Phase 1

- 固化 README 中的 Quick Start、Continue 配置、API 示例
- 保持 `/chat` 主链路不变
- 保持当前最小 OpenAI-compatible shim 稳定

### 2. 优化 OpenAI `messages -> prompt` 映射

- 继续复用 `/chat`
- 只优化兼容层映射策略
- 目标是减少网页侧直接看到 `System: ... User: ...` 的模板痕迹

### 3. 进入 Phase 2：Streaming 优化

- 当前兼容型 SSE 已可用
- 下一步再考虑更细粒度的页面增量流
- 优先提升实时性和体验，而不是重做协议层

### 4. 最后评估文件上传 / 多模态输入

- 单文件优先
- 再扩展图片 / 文档
- 最后再评估更复杂的多模态组合输入

## 一句话总结

项目当前已经从“豆包专用 HTTP API”升级为“可被 Continue 这类 OpenAI-compatible 客户端真实接入的桥接服务”，并且已经具备下载后按脚本和文档启动、验证和接入的基础落地能力。
