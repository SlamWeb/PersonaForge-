# 离线评测规格

`src/personaforge/eval` 负责把“作者过去表达能否支撑对未来问题的回答”变成无泄漏、可复跑的本地实验。它不负责 Web UI、Judge 或 rewrite。

## 本轮目标

提供两个 CLI 子命令：

```powershell
pf eval prepare <author>
pf eval run <author> --dataset <dataset.jsonl> --split dev
```

`prepare` 从已有 `index/parents.jsonl` 构造严格时间切分数据集；`run` 在既有全量 Qdrant 索引上动态排除未来 parent，运行当前 RAG + writer 链路并写出可读结果。

## 数据切分

- 只把 `kind=answer`、有标题、有创建时间、正文至少 200 字的 parent 作为候选题。
- 按 `created_at` 升序排列，尾部依次分为 `dev=10` 和 `test=20`。
- temporal cutoff 是 dev 的第一题创建时间。
- 所有创建时间不早于 cutoff 的 parent，不论 answer/article/pin，都会写入 `excluded_parent_ids`。
- `dataset.jsonl` 保存原问题、gold 原回答、目标 parent_id、创建时间和 split；它只落本地 `data/eval/`，不进入 git。

因此，test 原回答虽然仍物理存在于本地全量索引中，但 dense/sparse 的任何一路都不能检索到其 child node。

## Runner 合同

Runner 默认固定当前 baseline：

```text
grounded
+ strong_identity
+ BGE-M3 dense+sparse
+ 4 路 query transform
+ child_top_k=100
+ per_query_parent_k=30
+ parent_top_k=20
+ DeepSeek Flash
```

每题输出：

- generated answer 和 gold answer。
- query understanding / Tavily trace。
- 每路检索摘要、最终 parent、writer variant 和参数。
- 排除名单审计：任何 excluded parent 出现在 route 或 parent context 时，run 立即失败。

每次 run 还必须写 manifest，包括 dataset hash、excluded-parent hash、git revision、模型名、参数、时间和 split。它不写 API key、cookie、完整 writer prompt 或 parent 正文副本。

## 不做什么

- 不重爬、不重切片、不重 embedding、不重建 Qdrant collection。
- 不把真实语料或 eval 输出提交到仓库。
- 不做 LLM Judge、pairwise Judge、rewrite 或统计显著性；这些单独作为下一阶段。
- 不把 test 当作日常调参集。常规实验跑 dev，候选最终方案才跑 test。

## 验收

- 临时语料单测能验证时间切分和排除名单。
- 检索单测能验证 excluded parent 不会传入 Qdrant query。
- `pf eval prepare` 能对现有作者索引写出本地数据集。
- `pf eval run --split dev --limit 1` 能写出 manifest、runs.jsonl、单题 Markdown，并通过排除审计。

## 最近验证

- 临时语料测试覆盖：严格时间切分会排除 cutoff 后的 answer/article/pin；Runner 会写出 manifest、JSONL 和单题 Markdown。
- 本地全量索引 smoke 已验证：dynamic excluded-parent filter 同时作用于 4 路 query 的 dense/sparse 检索；最终 parent context 与各 route child hit 均为零泄漏。
- 第一轮完整 dev baseline 只写入本地 `data/eval/`；它不构成冻结 test 结果，也不包含 LLM Judge。
