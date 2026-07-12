# Web MVP 规格

`src/personaforge/web` 负责本地 Web 服务和前端静态资源托管。

## 当前目标

Web MVP 面向面试展示，目标是把现有 CLI RAG 链路变成一个可交互产品：

```text
选择本地 persona
-> 输入问题
-> FastAPI 调用当前 RAG20 + writer 链路
-> SSE 真流式返回回答
-> 回答完成后展示检索来源
```

## 不改动的边界

本阶段只做 Web，不改：

- crawler 抓取逻辑。
- build/index 入库逻辑。
- query understanding / query transform 策略。
- dense+sparse retrieval 和 parent RRF 聚合。
- writer prompt 和生成策略。

Web 只复用这些能力，不重新设计。

## 技术选择

后端：

```text
FastAPI + Uvicorn
```

原因：

- 更符合“后端 + AI 应用 / RAG 工程”的求职叙事。
- 能讲清楚 API schema、服务层、SSE streaming、错误处理。
- 后续接 LangGraph trace 和评估接口更自然。

前端：

```text
React + Vite + TypeScript + 原生 CSS
```

原因：

- 比 Streamlit/Gradio 更像真实产品。
- 比 Next.js 轻。
- 暂不上 shadcn/Tailwind/Ant Design，避免第一版被 UI 配置拖住。

## 目录规划

Python 后端：

```text
src/personaforge/web/
  app.py          FastAPI create_app 和路由
  schemas.py      Pydantic request/response schema
  service.py      Web 调用当前 RAG + writer 的服务层
  streaming.py    SSE 序列化工具
```

React 前端：

```text
web/
  package.json
  index.html
  src/
    App.tsx
    api.ts
    main.tsx
    styles.css
```

## API v0

### `GET /health`

返回服务状态。

### `GET /api/personas`

扫描本地：

```text
data/authors/zhihu/<author>/index/
```

只返回已存在 `parents.jsonl` 且有 `qdrant/` 的作者。

### `POST /api/chat/stream`

请求：

```json
{
  "author": "wu-ren-jun-28",
  "query": "如何看待女生常说的配得感",
  "query_mode": "grounded",
  "writer_prompt": "strong_identity",
  "parent_top_k": 20
}
```

响应为 SSE：

```text
event: meta
data: {"author":"...","retrieval_queries":[...]}

event: token
data: {"text":"..."}

event: done
data: {"answer":"...","sources":[...]}
```

错误：

```text
event: error
data: {"error":"..."}
```

## 流式策略

采用真流式：

```text
DeepSeek stream
-> FastAPI StreamingResponse
-> React fetch ReadableStream 解析 SSE
-> 前端实时追加 token
```

为了支持 Web，LLM provider 层需要新增：

```text
stream_text(messages, options) -> iterator[str]
```

这只是 provider 能力扩展，不改变现有非流式 `complete_text`。

## 缓存

FastAPI 进程内缓存：

- BGE-M3 encoder。
- DeepSeek client。

原因：Web 是长进程，不能每个问题都冷启动 embedding model。

## CLI

```powershell
pf web <author-token> --port 8000 --embedding-device cuda
```

`author-token` 作为本地开发默认 persona。若不传，则 Web 扫描本地 persona 并选择第一个。

## MVP 展示范围

第一版页面展示：

- 左侧 persona 选择，显示头像、知乎昵称、用户名、内容数量。
- 左侧按作者隔离的历史会话列表。
- 右侧聊天软件式消息流，用户和 persona 都显示头像。
- 流式回答。
- sources 折叠区：默认展示可读标题/path；二级“技术详情”展示 parent rank、child route/rank/node_type。
- query mode、writer prompt、parent topK 收进“高级设置”，默认不打扰普通使用。

## 视觉方向

Web 主界面采用“Claude 式轻聊天 + 左侧作者会话列表”的产品气质：

- 顶部不放大标题，不显示“正在以某作者回答”这类说明文案。
- 左侧顶部直接显示当前作者，应用品牌弱化到底部。
- 右侧空状态使用作者头像和一句开场白，形成轻 NPC 感。
- 作者回答采用 answer block，不用厚重聊天气泡承载长文。
- 用户消息保留右侧轻气泡。
- 每条正式消息都提供复制按钮。
- 高级参数默认折叠，后续 developer mode 再承载 trace、eval、中间过程。
- 色彩选择暖白/纸张感 + 墨色，避免通用 AI SaaS 蓝紫渐变模板感。

## Persona Metadata

Web 优先读取：

```text
data/authors/zhihu/<author>/profile.json
data/authors/zhihu/<author>/raw/profile.json
```

支持字段：

```json
{
  "nickname": "你的ZombieMan",
  "avatar_url": "https://...",
  "headline": ""
}
```

如果没有 profile，前端用 author token 和 initials 兜底。头像不应成为使用 Web 的硬依赖。

## 会话存储

第一版不用数据库，采用 local-first JSON 文件：

```text
data/authors/zhihu/<author>/sessions/<session_id>.json
```

会话只负责产品层历史记录，不改变当前 writer 的上下文策略。也就是说，继续同一个会话时，当前生成链路仍以“当前问题 + RAG 材料”为主；长期记忆和多轮上下文注入留到后续 developer mode / memory 模块。

## 建议问题

空状态建议问题不直接使用作者历史原题，避免点击后 RAG 直接召回原回答而变成复读。

当前策略：

```text
pf suggest <author>
-> 读取 index/parents.jsonl 的历史问题标题
-> 调 LLM 生成新的知乎式问题候选
-> 过滤完全重复、共享长短语、字符重合过高的问题
-> 写入 data/authors/zhihu/<author>/profile_suggestions.json
```

Web 只读取本地 `profile_suggestions.json`，不会在打开页面时偷偷调用 LLM。

API：

```text
GET /api/personas/{author}/suggestions
```

前端展示为开场白下方的轻量 chips。点击 chip 只填入输入框，不自动发送，避免误触触发生成成本。

下一阶段再做：

- LangGraph/trace 时间线。
- eval 面板。
- 多模型对比。
- session memory。
