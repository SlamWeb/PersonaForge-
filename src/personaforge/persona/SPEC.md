# Persona 生成规格

`src/personaforge/persona` 负责把检索到的作者历史表达和题目背景组织成 writer prompt，并调用 LLM 生成回答。

本模块不负责爬取、切片、向量化和 Qdrant 检索。

## v0 职责

```text
用户问题
客观题目背景（可为空）
RAG top20 父文档全文
-> context pack
-> writer prompt
-> LLM answer
```

## 设计边界

- writer 可以看到题目背景，但题目背景只解释事件/梗/概念，不代表作者立场。
- writer 可以看到作者历史表达全文，用于判断观点、切入角度、论证方式和语言风格。
- writer 不应该在最终回答里提“材料1/材料2/样本/检索结果/历史表达”。
- writer 不做引用回答，不输出来源列表。
- 来源、排名、child 命中只进入 trace，不进入最终文本。

## 当前 prompt 策略

第一版保留两套 writer prompt，方便自用和实验对比：

- `current`：当前调过的反 AI / 反 advice / 反契约训诫 prompt，默认使用，保证现有自用效果不被覆盖。
- `strong_identity`：通用强身份沉浸 prompt，不写任何特定作者词汇，测试“RAG20 + 强模型是否能自行归纳作者表达身份”。

CLI 切换方式：

```powershell
pf ask <author> "<question>" --writer-prompt current
pf ask <author> "<question>" --writer-prompt strong_identity
pf prompt-pack <author> "<question>" --writer-prompt strong_identity --out .tmp/chatgpt_prompt.md
```

`prompt-pack` 用于模型差异手测。它复用检索和上下文打包，但不调用 writer LLM，只把 `build_writer_messages(...)` 的结果渲染成一份可粘贴到 ChatGPT 网页的 Markdown。这样可以比较“同样 RAG20 + 同样 prompt”下，不同模型的表达底色差异。

`current` 策略：

- 像该创作者回答当前知乎问题。
- 不要写成 AI 分析文、课堂讲解、总分总作文。
- 不要写成情感课、行动建议、人生指导或契约训诫。
- 允许使用“你”做口语化推演，但不要进入 advice mode。
- 优先解释现象背后的机制，不要把回答写成道德审判或解决方案。
- 允许短句、跳跃、突然判断、口语化表达。
- 优先学习历史表达里的观点结构和切入方式。
- 无关历史表达只作为语气参考，不能强行塞进答案。
- 不要说“根据材料”“材料里”“历史表达中”。

反例约束：

- 错误类型：把回答写成“交易、合同、条款、甲乙方、谁该承担后果”的契约训诫。
- 错误原因：这会把创作者写成情感导师或契约论老师。
- 更好的方向：解释为什么当事人会产生这种感觉，以及这种感觉背后的关系机制。
- 不要复用反例里的说法。

`strong_identity` 策略：

- 任务不是“模仿文风”或“总结风格”，而是接管创作者的公开表达身份。
- 从 RAG20 中内部判断该创作者通常抓什么矛盾、采取什么表达形态、句子和段落节奏如何。
- 如果历史表达显示创作者常给建议，就给建议；常吐槽，就吐槽；常短评，就短评；常长文，就长文。
- 保留创作者表达中的不平衡、偏执、跳跃、重复、粗糙、尖锐或突然判断，不自动修成更礼貌、更中立、更完整、更有条理的 AI 文。
- 只输出最终回答正文，不描述风格，不输出分析过程。

## 上下文打包

`pack_author_context(...)` 接收 parent hits，输出给 writer 的紧凑上下文。

每个 parent 保留：

- 标题
- 正文全文

不保留：

- 检索排名
- dense/sparse 分数
- child node 命中信息
- URL、ID、时间等元数据

原因：writer 不需要知道检索过程，检索过程只用于 trace。

## 文件说明

### `writer.py`

- `build_writer_messages(...)`：构造 writer messages。
- `build_prompt_pack(...)`：构造可粘贴到 ChatGPT 网页的 Markdown prompt pack。
- `render_prompt_pack(...)`：把 chat messages 渲染为单段 Markdown。
- `pack_author_context(...)`：把 top parent 全文打包为创作者历史表达上下文。
- `generate_answer(...)`：调用 LLM 生成回答。
- `AnswerResult`：保存 answer、messages 和进入 writer 的 parent 标题，便于 CLI trace。

## 后续不进入 v0 的能力

- judge/rewrite 在线闭环。
- 多轮 session memory。
- 长度控制前端选项。
- 多 provider 完整抽象。
- profile v2 / claim evidence。
