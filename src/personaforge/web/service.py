"""Service layer used by the FastAPI Web app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from personaforge.ingest.embeddings import BgeM3Encoder, TextEncoder
from personaforge.ingest.query_understanding import build_grounded_query_plan, plan_to_trace
from personaforge.ingest.retrieve import ParentHit, RetrieveResult, retrieve_parents, retrieve_parents_for_queries
from personaforge.llm import DeepSeekJsonClient, JsonChatClient
from personaforge.persona.writer import build_writer_messages


@dataclass(slots=True)
class WebConfig:
    author: str | None = None
    data_dir: Path = Path("data")
    port: int = 8000
    model_name: str = "BAAI/bge-m3"
    embedding_device: str = "auto"
    use_fp16: bool = True
    child_top_k: int = 100
    per_query_parent_k: int = 30
    parent_top_k: int = 20
    max_search_results: int = 5
    temperature: float = 0.85
    max_tokens: int = 1600


@dataclass(slots=True)
class LocalPersona:
    author: str
    source: str
    display_name: str
    avatar_url: str | None
    headline: str
    content_count: int | None
    author_dir: Path
    index_dir: Path
    qdrant_path: Path


@dataclass(slots=True)
class PreparedChat:
    session_id: str
    author: str
    query: str
    query_mode: str
    writer_prompt: str
    objective_background: str
    query_trace: dict[str, Any] | None
    retrieve_result: RetrieveResult
    messages: list[dict[str, str]]


class PersonaChatService:
    def __init__(
        self,
        config: WebConfig,
        *,
        encoder: TextEncoder | None = None,
        llm: JsonChatClient | None = None,
    ) -> None:
        self.config = config
        self._encoder = encoder
        self._llm = llm

    def list_personas(self) -> list[LocalPersona]:
        return list_local_personas(self.config.data_dir)

    def default_author(self) -> str | None:
        if self.config.author:
            return self.config.author
        personas = self.list_personas()
        return personas[0].author if personas else None

    def prepare_chat(
        self,
        *,
        author: str | None,
        session_id: str | None,
        query: str,
        query_mode: str,
        writer_prompt: str,
        parent_top_k: int | None = None,
    ) -> PreparedChat:
        selected_author = (author or self.default_author() or "").strip()
        if not selected_author:
            raise ValueError("No local persona index found. Run `pf build` and `pf index` first.")

        selected_session_id = session_id or new_session_id()
        retrieve_result, query_trace, objective_background = self._retrieve(
            author=selected_author,
            query=query,
            query_mode=query_mode,
            parent_top_k=parent_top_k or self.config.parent_top_k,
        )
        messages = build_writer_messages(
            query=query,
            parent_hits=retrieve_result.parents,
            objective_background=objective_background,
            writer_prompt=writer_prompt,
        )
        return PreparedChat(
            session_id=selected_session_id,
            author=selected_author,
            query=query,
            query_mode=query_mode,
            writer_prompt=writer_prompt,
            objective_background=objective_background,
            query_trace=query_trace,
            retrieve_result=retrieve_result,
            messages=messages,
        )

    def stream_answer(self, prepared: PreparedChat) -> Iterator[str]:
        yield from self._get_llm().stream_text(
            prepared.messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def list_sessions(self, author: str) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in sorted(session_dir(self.config.data_dir, author).glob("*.json"), reverse=True):
            try:
                payload = read_json(path)
            except json.JSONDecodeError:
                continue
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            sessions.append(
                {
                    "id": str(payload.get("id") or path.stem),
                    "author": author,
                    "title": str(payload.get("title") or "未命名对话"),
                    "created_at": str(payload.get("created_at") or ""),
                    "updated_at": str(payload.get("updated_at") or ""),
                    "message_count": len(messages),
                }
            )
        return sessions

    def get_session(self, author: str, session_id: str) -> dict[str, Any]:
        path = session_path(self.config.data_dir, author, session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        payload = read_json(path)
        payload.setdefault("id", session_id)
        payload.setdefault("author", author)
        payload.setdefault("title", "未命名对话")
        payload.setdefault("messages", [])
        return payload

    def delete_session(self, author: str, session_id: str) -> None:
        path = session_path(self.config.data_dir, author, session_id)
        if path.exists():
            path.unlink()

    def list_suggestions(self, author: str) -> list[str]:
        path = suggestions_path(self.config.data_dir, author)
        if not path.exists():
            return []
        try:
            payload = read_json(path)
        except json.JSONDecodeError:
            return []
        suggestions = payload.get("suggestions")
        if not isinstance(suggestions, list):
            return []
        return [str(item) for item in suggestions if isinstance(item, str)]

    def save_turn(self, prepared: PreparedChat, answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        now = utc_now()
        path = session_path(self.config.data_dir, prepared.author, prepared.session_id)
        if path.exists():
            payload = read_json(path)
        else:
            payload = {
                "id": prepared.session_id,
                "author": prepared.author,
                "title": session_title(prepared.query),
                "created_at": now,
                "messages": [],
            }
        payload["updated_at"] = now
        messages = payload.setdefault("messages", [])
        messages.append({"role": "user", "text": prepared.query})
        messages.append({"role": "assistant", "text": answer, "sources": sources})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _retrieve(
        self,
        *,
        author: str,
        query: str,
        query_mode: str,
        parent_top_k: int,
    ) -> tuple[RetrieveResult, dict[str, Any] | None, str]:
        index_dir = self.config.data_dir / "authors" / "zhihu" / author / "index"
        qdrant_path = index_dir / "qdrant"
        query_trace = None
        objective_background = ""
        if query_mode == "grounded":
            plan = build_grounded_query_plan(
                query,
                llm=self._get_llm(),
                max_results_per_query=self.config.max_search_results,
            )
            query_trace = plan_to_trace(plan)
            objective_background = plan.transform.objective_background
            result = retrieve_parents_for_queries(
                query,
                plan.transform.retrieval_queries,
                author=author,
                index_dir=index_dir,
                qdrant_path=qdrant_path,
                encoder=self._get_encoder(),
                child_top_k=self.config.child_top_k,
                per_query_parent_k=self.config.per_query_parent_k,
                parent_top_k=parent_top_k,
            )
        elif query_mode == "raw":
            result = retrieve_parents(
                query,
                author=author,
                index_dir=index_dir,
                qdrant_path=qdrant_path,
                encoder=self._get_encoder(),
                child_top_k=self.config.child_top_k,
                parent_top_k=parent_top_k,
            )
        else:
            raise ValueError(f"Unknown query_mode: {query_mode}")
        return result, query_trace, objective_background

    def _get_encoder(self) -> TextEncoder:
        if self._encoder is None:
            self._encoder = BgeM3Encoder(
                self.config.model_name,
                device=self.config.embedding_device,
                use_fp16=self.config.use_fp16,
            )
        return self._encoder

    def _get_llm(self) -> JsonChatClient:
        if self._llm is None:
            self._llm = DeepSeekJsonClient.from_env()
        return self._llm


def list_local_personas(data_dir: Path = Path("data")) -> list[LocalPersona]:
    root = data_dir / "authors" / "zhihu"
    if not root.exists():
        return []
    personas: list[LocalPersona] = []
    for author_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        index_dir = author_dir / "index"
        qdrant_path = index_dir / "qdrant"
        if (index_dir / "parents.jsonl").exists() and qdrant_path.exists():
            profile = load_persona_profile(author_dir)
            personas.append(
                LocalPersona(
                    author=author_dir.name,
                    source="zhihu",
                    display_name=str(profile.get("display_name") or profile.get("nickname") or author_dir.name),
                    avatar_url=profile.get("avatar_url"),
                    headline=str(profile.get("headline") or ""),
                    content_count=count_parents(index_dir),
                    author_dir=author_dir,
                    index_dir=index_dir,
                    qdrant_path=qdrant_path,
                )
            )
    return personas


def sources_from_parent_hits(parent_hits: list[ParentHit]) -> list[dict[str, Any]]:
    return [
        {
            "rank": hit.rank,
            "parent_id": hit.parent_id,
            "score": hit.score,
            "title": hit.title,
            "path": hit.path,
            "first_hits": [
                {
                    "rank": child.rank,
                    "score": child.score,
                    "node_id": child.node_id,
                    "node_type": child.node_type,
                    "route": child.route,
                }
                for child in hit.first_hits
            ],
        }
        for hit in parent_hits
    ]


def load_persona_profile(author_dir: Path) -> dict[str, Any]:
    for path in [author_dir / "profile.json", author_dir / "raw" / "profile.json"]:
        if path.exists():
            return read_json(path)
    return {}


def count_parents(index_dir: Path) -> int | None:
    path = index_dir / "parents.jsonl"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def session_dir(data_dir: Path, author: str) -> Path:
    return data_dir / "authors" / "zhihu" / author / "sessions"


def session_path(data_dir: Path, author: str, session_id: str) -> Path:
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
    if not safe_id:
        safe_id = new_session_id()
    return session_dir(data_dir, author) / f"{safe_id}.json"


def suggestions_path(data_dir: Path, author: str) -> Path:
    return data_dir / "authors" / "zhihu" / author / "profile_suggestions.json"


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid4().hex[:8]}"


def session_title(query: str) -> str:
    title = " ".join(query.strip().split())
    return title[:32] if title else "未命名对话"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
