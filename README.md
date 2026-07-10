# PersonaForge Open Source

Local-first creator persona RAG.

This repo is the planned open-source product version split from the research workspace. The MVP goal is simple:

```text
crawl public creator content locally
-> build a local RAG index
-> connect your own LLM API key
-> chat with a local web UI
```

The detailed contract lives in [SPEC.md](SPEC.md).

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -e ".[dev]"
pf --help
pf init
python -m pytest -q
```

The real crawl/build/chat pipeline is still being implemented. The current repository contains the project skeleton, CLI entrypoint, and mock Zhihu-like corpus.

Current decisions:

- MVP is a local CLI + local Web app, not a hosted crawler service.
- Sample corpus will use self-made Zhihu-like Markdown under `samples/zhihu_mock_md/`.
- `--quality fast` is the default build path and does not call an LLM for preprocessing.
- `--quality full` may add document summaries, but does not create hypothetical questions.
- Query transform happens at query time.
- LLM providers will be abstracted for DeepSeek, OpenAI, and OpenRouter.
- Embedding stays local with BGE-M3 in the first version.

No real crawled corpus, auth state, local index, model files, eval output, or API keys should be committed.

## Notes For Contributors

Implementation notes are tracked in [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md). Each module should be explainable enough for an interview, not just runnable.
