# 实现笔记

这份文档只做项目级索引和时间线，不承载所有模块细节。

模块级说明放在模块目录自己的 `SPEC.md` 里。例如：

```text
src/personaforge/SPEC.md
src/personaforge/ingest/SPEC.md
src/personaforge/providers/SPEC.md
src/personaforge/web/SPEC.md
```

每个模块 `SPEC.md` 应该说明：

- 这个模块负责什么
- 不负责什么
- 目录里的每个 `.py` 文件做什么
- 关键函数或类的职责
- 这个模块的验证入口
- 面试时应该怎么解释

## 时间线

### 2026-07-05: 开源骨架

完成内容：

- 创建 `C:\PersonaForge-OpenSource`
- 添加开源边界：`.gitignore`、`.env.example`
- 添加 Python 包骨架：`pyproject.toml`、`src/personaforge/`
- 添加 CLI 壳子：`pf init/crawl/build/web/forge`
- 添加自造 mock corpus：`samples/zhihu_mock_md/`
- 添加基础测试：`tests/test_project_skeleton.py`
- 添加模块说明：[src/personaforge/SPEC.md](../src/personaforge/SPEC.md)

验证：

```powershell
python -m pytest -q
```

结果：

```text
3 passed
```

设计决策：

- `pyproject.toml` 是依赖和 CLI 入口的主配置。
- `requirements.txt` 可以后续作为兼容入口，但不作为依赖事实源。
- 真实 raw corpus、index、auth、models、eval 不进入 git。
- mock corpus 格式贴近 crawler 输出，用于开源 demo 和测试。

下一步：

```text
src/personaforge/ingest/
  SPEC.md
  models.py
  markdown.py
  chunking.py
  build.py
```

目标是先把 raw Markdown 解析成可审计中间产物：

```text
parents.jsonl
nodes.jsonl
```

暂时不接 BGE-M3 和 Qdrant。
### 2026-07-05: 爬虫 v0

完成内容：

- 新增 `src/personaforge/crawler/` 模块。
- 实现知乎免登录 public API 尝试。
- 实现 Playwright browser fallback 和本地登录态保存入口。
- 接入 CLI：
  - `pf crawl zhihu <author>`
  - `pf zhihu-login`
- 输出 raw corpus：
  - `profile.json`
  - `manifest.jsonl`
  - `*.md`
- 新增离线测试：
  - `tests/test_crawler_markdown.py`
  - `tests/test_zhihu.py`
  - `tests/test_zhihu_browser.py`
  - `tests/test_cli_crawl.py`

验证：

```powershell
python -m pytest -q
```

结果：

```text
16 passed
```

真实网络 smoke：

```powershell
$env:PYTHONPATH='src'
python -m personaforge.cli crawl zhihu wu-ren-jun-28 --max-items 3 --no-browser --quiet --out-dir .tmp-crawl\wu-ren-jun-28_md
```

结果：当前环境可免登录抓到 3 条公开想法。`.tmp-crawl` 已加入 `.gitignore`，smoke 后已删除本地产物。
### 2026-07-05: 本地可编辑安装

本机已把开源项目注册成 editable package，因此当前 Python 环境可以直接使用：

```powershell
pf --help
pf crawl zhihu wu-ren-jun-28 --max-items 3
```

实际入口位置：

```text
D:\Anaconda4.7g\Scripts\pf.exe
```

由于当前机器的 PyPI/代理访问不稳定，注册时采用：

```powershell
python -m pip install --no-build-isolation --no-deps -e .
```

这只注册当前项目和 `pf` 命令，不额外下载依赖。当前环境已经具备本轮 crawler smoke 需要的依赖：

- `beautifulsoup4`
- `pytest`
- `setuptools`
- `wheel`

为了减少新用户安装时对 `hatchling` 的额外依赖，`pyproject.toml` 的构建后端已改为 `setuptools.build_meta`。

验证：

```powershell
pf --help
pf crawl zhihu wu-ren-jun-28 --max-items 3 --no-browser --quiet --out-dir data/raw/wu-ren-jun-28_md_pf_smoke
python -m pytest -q
```

结果：

```text
pf help ok
Saved 3 item(s)
16 passed
```
