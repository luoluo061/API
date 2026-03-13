# 项目 Roadmap

## 当前状态

项目当前已经完成 V1 主链路验证：
- CDP 接管已登录 Edge
- 豆包网页真实发送、等待、提取
- `/chat` 作为稳定主接口
- `/v1/models` 和 `/v1/chat/completions` 作为最小 OpenAI-compatible shim
- Continue 已完成真实接入验证

当前明确运行约束：
- 服务必须在 `E:\API` 目录下启动
- 启动命令固定为：

```powershell
cd E:\API
py -m uvicorn web_adapter.main:app --host 127.0.0.1 --port 8000
```

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

## 下一步顺序

### 1. 冻结并整理 Phase 1

- 固化 README 中的启动方式、Continue 配置、运行约束
- 清理测试残留与 Git 状态
- 记录 Continue 已验证通过
- 保持 `/chat` 主链路不变

### 2. 优化 OpenAI `messages -> prompt` 映射

- 继续复用 `/chat`
- 只优化兼容层映射策略
- 目标是减少网页侧直接看到 `System: ... User: ...` 的模板痕迹
- 不改变当前已打通的协议链路

### 3. 进入 Phase 2：Streaming 优化

- 当前兼容型 SSE 已可用
- 下一步再考虑更细粒度的页面增量流
- 优先提升实时性和体验，而不是重做协议层

### 4. 最后评估文件上传 / 多模态输入

- 单文件优先
- 再扩展图片 / 文档
- 最后再评估更复杂的多模态组合输入

## Git 管理建议

- 当前阶段先把 Phase 1 相关改动单独收口提交
- 提交内容建议只包含：
  - OpenAI-compatible shim
  - Continue 验证相关文档
  - 测试
  - `.gitignore` 清理
- 不要把运行时 `.artifacts`、`.profiles`、临时测试目录提交进仓库

## 一句话总结

项目当前已经从“豆包专用 HTTP API”升级为“可被 Continue 这类 OpenAI-compatible 客户端真实接入的桥接服务”，下一步优先做 Phase 1 收口和映射优化，再进入流式增强。
