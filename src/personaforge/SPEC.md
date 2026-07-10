# personaforge Package SPEC

这是开源版 PersonaForge 的 Python 包入口层。它目前只承担项目元信息和 CLI 入口，不包含 crawler、ingest、retrieval、provider 或 web 的具体业务逻辑。

## 职责

- 暴露包版本。
- 提供 `pf` / `personaforge` 命令行入口。
- 创建本地数据目录。
- 固定未来 CLI 的命令形态。

## 非职责

- 不直接爬取平台内容。
- 不解析 Markdown。
- 不构建向量索引。
- 不调用 LLM。
- 不启动真实 Web 服务。

这些功能后续分别放入独立模块，例如：

```text
src/personaforge/crawler/
src/personaforge/ingest/
src/personaforge/retrieval/
src/personaforge/providers/
src/personaforge/web/
```

每个模块都要有自己的 `SPEC.md`。

## 文件说明

### `__init__.py`

包初始化文件。

当前只定义：

```python
__version__ = "0.1.0"
```

用途：

- 给 CLI 的 `--version` 使用。
- 给测试确认包能被正常导入。
- 后续发布包时保持单一版本入口。

### `cli.py`

命令行入口。

安装项目后，`pyproject.toml` 会把下面两个命令注册到终端：

```text
pf
personaforge
```

它们都指向：

```text
personaforge.cli:main
```

## 函数职责

### `build_parser() -> argparse.ArgumentParser`

定义 CLI 的整体命令树。

当前子命令：

```text
pf init
pf crawl
pf build
pf web
pf forge
```

这些命令先稳定接口，再逐步接入真实功能。

### `_ensure_data_dirs(data_dir: Path) -> list[Path]`

创建 local-first 项目需要的数据目录：

```text
data/raw/
data/index/
data/auth/
data/models/
data/eval/
```

这些目录全部被 `.gitignore` 屏蔽。

设计原因：

- raw corpus、索引、登录态、模型和评估结果都是本地产物。
- 开源仓库只提交代码、sample、测试和文档。
- 用户运行 `pf init` 后才在自己的机器上创建这些目录。

### `main(argv: list[str] | None = None) -> int`

CLI 总入口。

流程：

```text
构造 parser
-> 解析 argv
-> 根据子命令分发
-> 返回进程退出码
```

当前真实实现：

- `pf init`

当前只保留壳子的命令：

- `pf crawl`
- `pf build`
- `pf web`
- `pf forge`

这些命令会明确报错 `not implemented yet`，防止用户误以为功能已经完成。

## 验证入口

```powershell
python -m pytest -q
```

当前相关测试：

```text
tests/test_project_skeleton.py
```

覆盖：

- 包有版本号。
- CLI help 能运行。
- sample corpus 形状正确。

## 面试解释

可以这样讲：

> 我先把开源项目做成标准 Python package，而不是散落脚本。`pyproject.toml` 注册 `pf` 命令，`cli.py` 固定用户入口，`pf init` 创建 local-first 数据目录。这样后续 crawler、ingest、retrieval、web 都可以作为模块逐步接入，用户不需要知道内部脚本路径。

如果被问为什么还没实现的命令也先放出来：

> 因为 CLI 是产品契约。先稳定命令形态，后续每个模块接入时只填实现，不频繁改变用户使用方式。
## 2026-07-05 Update: Crawler CLI

`pf crawl` 现在已经接入 Zhihu crawler v0，不再只是占位命令。

当前真实命令：

```powershell
$env:PYTHONPATH='src'
python -m personaforge.cli crawl zhihu wu-ren-jun-28 --max-items 20
```

默认输出：

```text
data/raw/<author-token>_md/
  profile.json
  manifest.jsonl
  *.md
```

如果公开接口被挡，可以先在本机保存登录态：

```powershell
$env:PYTHONPATH='src'
python -m personaforge.cli zhihu-login --storage-state data/auth/zhihu_storage_state.json
```

然后重试：

```powershell
$env:PYTHONPATH='src'
python -m personaforge.cli crawl zhihu wu-ren-jun-28 --storage-state data/auth/zhihu_storage_state.json
```

设计边界：

- crawler 默认先尝试免登录 public API。
- 只有失败或抓不到时才尝试 Playwright fallback。
- 登录态只保存在用户本地 `data/auth/`，不进入 git。
- crawler 只负责 raw corpus，不负责 ingest、embedding、RAG 或 LLM。
