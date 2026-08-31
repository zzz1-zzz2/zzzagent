# traceforce-llm

`traceforce-llm` 是 TraceForce 的模型边界包。它把不同 Provider 的 SDK 请求和响应转换为一套稳定的内部协议，供 `traceforce-runtime` 调用。

## 负责什么

- OpenAI、DeepSeek、Anthropic 和 OpenAI 兼容网关适配；
- 同步、异步和流式对话；
- 统一 `Message`、`Response`、`StreamChunk`；
- 聚合流式 tool-call 分片；
- 归一化 usage、finish reason 和 reasoning 元数据。

## 不负责什么

这个包不读取 workspace，不定义 `read` / `write` / `edit` / `bash`，不执行工具，不管理 Session，也不实现 Agent loop。它只负责连接模型服务和翻译协议。

## 最小用法

```python
from traceforce_llm import Config, LLM, Message

llm = LLM(
    config=Config(
        provider="openai",
        model="your-model-name",
        api_key="从环境变量读取，不要硬编码",
    )
)
response = llm.chat([
    Message(role="user", content="Explain this function briefly."),
])
print(response.content)
```

流式调用：

```python
for chunk in llm.stream(messages):
    print(chunk.content, end="", flush=True)
```

异步流式调用：

```python
async for chunk in llm.achat_stream(messages):
    print(chunk.content, end="", flush=True)
```

生产代码应从环境变量或未入库配置文件加载 `api_key`。不要把真实凭据写进源码、示例、日志、Session 或文档。

## 配置字段

`Config` 支持：

- `provider`：`openai`、`deepseek` 或 `anthropic`；
- `model`：Provider 对应模型名；
- `api_key`：本地传入的凭据；
- `base_url`：可选的 OpenAI 兼容网关地址；
- `temperature`、`max_tokens`、`timeout`、`max_retries`。

Provider 差异被封装在 `providers/` 内部，runtime 不需要感知不同 SDK 的返回结构。

## 开发与测试

```bash
cd packages/traceforce-llm
uv sync
uv lock --check
uv run python -m pytest -q
uv build
```

测试使用 Fake SDK 和离线数据，当前离线测试数量为 36 项（以实际运行结果为准），不需要真实 API key 或网络。

## 包结构

```text
src/traceforce_llm/
├── client.py                 # LLM 门面
├── config.py                 # 不可变配置模型
├── models.py                 # Message/Response/StreamChunk/ToolCall
└── providers/
    ├── _base.py              # Provider 抽象接口
    ├── registry.py           # provider 名称路由
    ├── openai.py             # OpenAI 适配
    ├── deepseek.py           # DeepSeek 适配
    └── anthropic.py          # Anthropic 适配
```

上层入口见 [根 README](../../README.md)，运行时边界见 [`traceforce-runtime`](../traceforce-runtime/README.md)。
