"""Query understanding, optional web grounding, and retrieval query transform."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from personaforge.env import first_env_value, load_env_file
from personaforge.llm import JsonChatClient

ROUTES = (
    "literal_question",
    "event_background",
    "mechanism_scene",
    "colloquial_surface",
)


class SearchClient(Protocol):
    def search_many(self, queries: list[str], *, max_results: int = 5) -> list["SearchResult"]:
        """Search the public web for each query and return compact results."""


@dataclass(frozen=True, slots=True)
class SearchPlan:
    needs_web: bool
    search_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SearchResult:
    query: str
    title: str
    url: str
    content: str


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    route: str
    query: str


@dataclass(frozen=True, slots=True)
class QueryTransformResult:
    objective_background: str
    retrieval_queries: list[RetrievalQuery]


@dataclass(frozen=True, slots=True)
class GroundedQueryPlan:
    original_query: str
    search_plan: SearchPlan
    search_results: list[SearchResult]
    transform: QueryTransformResult


@dataclass(frozen=True, slots=True)
class TavilySearchClient:
    api_key: str
    base_url: str = "https://api.tavily.com"
    timeout_seconds: float = 30.0
    search_depth: str = "basic"

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> "TavilySearchClient":
        load_env_file(env_file)
        api_key = first_env_value("TAVILY_API_KEY", "Tavily_API_KEY")
        if not api_key:
            raise ValueError("Missing Tavily API key: set TAVILY_API_KEY in .env or environment.")
        return cls(api_key=api_key)

    def search_many(self, queries: list[str], *, max_results: int = 5) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            payload = self._search(query, max_results=max_results)
            for row in payload.get("results") or []:
                if not isinstance(row, dict):
                    continue
                results.append(
                    SearchResult(
                        query=query,
                        title=str(row.get("title") or ""),
                        url=str(row.get("url") or ""),
                        content=str(row.get("content") or ""),
                    )
                )
        return results

    def _search(self, query: str, *, max_results: int) -> dict[str, object]:
        body = {
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/search",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Tavily HTTP {exc.code}: {detail}") from exc
        return json.loads(payload)


def build_grounded_query_plan(
    query: str,
    *,
    llm: JsonChatClient,
    search_client: SearchClient | None = None,
    max_search_queries: int = 3,
    max_results_per_query: int = 5,
) -> GroundedQueryPlan:
    search_plan = plan_web_search(query, llm=llm, max_search_queries=max_search_queries)
    search_results: list[SearchResult] = []
    if search_plan.needs_web:
        if search_client is None:
            search_client = TavilySearchClient.from_env()
        search_results = search_client.search_many(
            search_plan.search_queries,
            max_results=max_results_per_query,
        )
    transform = build_background_and_retrieval_queries(query, search_results=search_results, llm=llm)
    return GroundedQueryPlan(
        original_query=query,
        search_plan=search_plan,
        search_results=search_results,
        transform=transform,
    )


def plan_web_search(query: str, *, llm: JsonChatClient, max_search_queries: int = 3) -> SearchPlan:
    payload = llm.complete_json(
        [
            {"role": "system", "content": SEARCH_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"知乎问题：{query}"},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    needs_web = bool(payload.get("needs_web"))
    search_queries = _string_list(payload.get("search_queries"))[:max_search_queries]
    if not needs_web:
        search_queries = []
    return SearchPlan(needs_web=needs_web, search_queries=search_queries)


def build_background_and_retrieval_queries(
    query: str,
    *,
    search_results: list[SearchResult],
    llm: JsonChatClient,
) -> QueryTransformResult:
    has_search_results = bool(search_results)
    payload = llm.complete_json(
        [
            {"role": "system", "content": BACKGROUND_TRANSFORM_SYSTEM_PROMPT},
            {"role": "user", "content": _background_transform_user_prompt(query, search_results)},
        ],
        temperature=0.0,
        max_tokens=1400,
    )
    background = str(payload.get("objective_background") or "").strip() if has_search_results else ""
    queries = _parse_retrieval_queries(payload.get("retrieval_queries"), original_query=query)
    return QueryTransformResult(objective_background=background, retrieval_queries=queries)


def plan_to_trace(plan: GroundedQueryPlan) -> dict[str, object]:
    return {
        "original_query": plan.original_query,
        "search_plan": {
            "needs_web": plan.search_plan.needs_web,
            "search_queries": plan.search_plan.search_queries,
        },
        "search_results": [
            {
                "query": item.query,
                "title": item.title,
                "url": item.url,
                "content": item.content,
            }
            for item in plan.search_results
        ],
        "objective_background": plan.transform.objective_background,
        "retrieval_queries": [
            {"route": item.route, "query": item.query} for item in plan.transform.retrieval_queries
        ],
    }


def _background_transform_user_prompt(query: str, search_results: list[SearchResult]) -> str:
    if search_results:
        rows = []
        for index, result in enumerate(search_results, start=1):
            rows.append(
                "\n".join(
                    [
                        f"[{index}] query: {result.query}",
                        f"title: {result.title}",
                        f"url: {result.url}",
                        f"content: {result.content}",
                    ]
                )
            )
        search_block = "\n\n".join(rows)
    else:
        search_block = "无联网搜索结果。objective_background 必须输出空字符串。仍需生成 4 路 retrieval_queries。"
    return f"知乎问题：{query}\n\n搜索结果：\n{search_block}"


def _parse_retrieval_queries(value: object, *, original_query: str) -> list[RetrievalQuery]:
    by_route: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            route = str(item.get("route") or "").strip()
            query = str(item.get("query") or "").strip()
            if route and query:
                by_route[route] = query

    queries: list[RetrievalQuery] = []
    for route in ROUTES:
        query = by_route.get(route) or original_query
        queries.append(RetrievalQuery(route=route, query=query))
    return queries


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


SEARCH_PLANNER_SYSTEM_PROMPT = """你是 PersonaForge 的 Search Planner。

任务：只判断一个知乎问题是否需要联网查客观背景，并给出用于 Tavily 搜索的 query。

你只能输出 JSON object：
{
  "needs_web": true,
  "search_queries": ["..."]
}

判断原则：
- 如果问题涉及近期事件、具体人物近期言论、热搜、新闻、直播、电影综艺新梗、外文新词、平台热点，needs_web=true。
- 如果问题只是普通观念、情感、社会现象、常识性概念，needs_web=false。
- search_queries 只用于查清“题目在说什么”，不能搜索“如何评价/怎么看”的立场文章。
- search_queries 应抽出实体、事件、原话、关键词；最多 3 条。
- 不要预测作者立场，不要给写作角度，不要生成答案。
"""


BACKGROUND_TRANSFORM_SYSTEM_PROMPT = """你是 PersonaForge 的 Background + Query Transform 节点。

输入是一个知乎问题，以及可选的 Tavily 搜索结果。

你必须输出 JSON object：
{
  "objective_background": "...",
  "retrieval_queries": [
    {"route": "literal_question", "query": "..."},
    {"route": "event_background", "query": "..."},
    {"route": "mechanism_scene", "query": "..."},
    {"route": "colloquial_surface", "query": "..."}
  ]
}

约束：
- 如果没有搜索结果，objective_background 必须为空字符串。
- 如果有搜索结果，objective_background 只解释题目涉及的词义、人物、事件、梗或背景，最多 1-2 句。
- objective_background 只回答“这题在说什么”，不能写“涉及哪些问题/社会现象/权力结构/现实困境”。
- 不要评价事件，不要改写题目，不要推断作者立场，不要写“应该批判谁”。
- retrieval_queries 用于检索作者本地历史内容，不是用于 Web 搜索。
- retrieval_queries 不要为了显得深刻，主动引入原题和搜索结果都没有支持的公共议题框架、媒体评论词或学术分析词。
- retrieval_queries 应优先使用具体场景、人物关系、行为动机、冲突模式、日常说法。
- 四个 route 必须都输出，含义如下：
  1. literal_question：保留题目字面意思，不扩展，不抽象。
  2. event_background：如果有联网背景，保留事件实体、关键词和关键事实；没有背景时接近 literal_question。
  3. mechanism_scene：把题目转成具体关系机制、行为动机、冲突场景和日常动作，不写成公共价值框架。
  4. colloquial_surface：换成知乎常见口语表达、网络表达和短词组合，利于 sparse lexical 命中。
- query 要短，适合向量检索和 sparse 关键词检索。

反例：
问题：为什么很多女明星嫁入豪门后，都觉得自己上当了？
错误 objective_background：该问题涉及豪门婚姻中的权力不对等、家庭压力、女性自主权和经济控制等现实问题。
为什么错：这不是背景解释，而是额外引入公共议题框架，会污染后续检索和生成。
正确 objective_background：“嫁入豪门”通常指与富豪或显赫家族成员结婚；“觉得上当”指婚后发现现实与想象不一致。

错误 mechanism_scene query：豪门婚姻 权力不对等 女性自主权 经济控制
为什么错：这些词不是题目实体，也不是必要背景，而是媒体评论/学术分析框架。
更合适：嫁豪门 婚后 觉得上当；女人 嫁有钱人 婚后 不满足；婚姻 有钱男人 女人 后悔
"""
