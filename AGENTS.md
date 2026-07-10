# AGENTS.md

Use this file as the working contract for future agents in this open-source repo.

## Working Loop

```text
read SPEC.md -> state assumption -> make a small change -> verify -> update SPEC.md if the contract changed
```

## Boundaries

- Keep this repo product-focused. Do not import research-only eval artifacts from `C:\PersonaForge`.
- Do not commit real crawled corpus, auth state, local indexes, model files, `.env`, or API keys.
- Prefer local-first behavior: user data and credentials stay on the user's machine.
- Keep MVP code paths explainable for interviews.

## Encoding

Chinese Markdown and sample text are allowed. Use UTF-8 for all files.

On Windows, prefer:

```powershell
chcp 65001 > $null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

## Current Priority

Build the open-source engineering skeleton:

1. sample corpus
2. CLI build path
3. provider abstraction
4. graph_v0 wrapper
5. local Web chat
6. README quickstart
