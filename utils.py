# utils.py
"""
Utilidades de busca e formatação de fontes.

• Tavily  — busca web estruturada
• Perplexity API  — busca LLM-first (opcional)
• OpenPerplex  — busca web + IA (opcional)

Todas as funções retornam dicionários padronizados para que os nós do
LangGraph montem o objeto `QueryResult` sem precisar conhecer detalhes
de cada provedor.
"""

from __future__ import annotations

import os
import requests
from typing import Dict, Any, List

from tavily import TavilyClient
from openperplex import OpenperplexSync
from langsmith import traceable
from dotenv import load_dotenv

load_dotenv()  # lê as variáveis de ambiente do .env local


# --------------------------------------------------------------------------- #
# Helpers de formatação                                                      #
# --------------------------------------------------------------------------- #

def deduplicate_and_format_sources(
    search_response: dict | list,
    max_tokens_per_source: int = 2_048,
    include_raw_content: bool = False,
) -> str:
    """
    Recebe um único dicionário ou lista de dicionários de resposta de busca
    (estilo Tavily) e devolve uma string formatada com fontes únicas.

    • Deduplica por URL
    • Trunca raw_content (≈4 chars ≅ 1 token) se solicitado
    """
    # Normaliza para lista
    if isinstance(search_response, dict):
        sources_list: List[dict] = search_response.get("results", [])
    elif isinstance(search_response, list):
        sources_list = []
        for resp in search_response:
            sources_list.extend(resp.get("results", []))
    else:
        raise ValueError(
            "search_response precisa ser dict{'results':…} ou list de resultados."
        )

    # Deduplicação
    unique: dict[str, dict] = {src["url"]: src for src in sources_list}

    lines: List[str] = ["Sources:\n"]
    for src in unique.values():
        lines.append(f"Source {src['title']}:\n===")
        lines.append(f"URL: {src['url']}\n===")
        lines.append(f"Most relevant content: {src['content']}\n===")
        if include_raw_content and (raw := src.get("raw_content")):
            limit = max_tokens_per_source * 4
            snippet = (raw[:limit] + "... [truncated]") if len(raw) > limit else raw
            lines.append(
                f"Full source content "
                f"(≤{max_tokens_per_source} tokens≈{limit} chars): {snippet}\n"
            )
        lines.append("")  # linha em branco
    return "\n".join(lines).strip()


def format_sources(search_results: dict) -> str:
    """Converte resposta Tavily em lista-bullet de fontes."""
    return "\n".join(
        f"* {src['title']} : {src['url']}" for src in search_results["results"]
    )


# --------------------------------------------------------------------------- #
# Provedores de busca                                                         #
# --------------------------------------------------------------------------- #

@traceable
def tavily_search(
    query: str,
    *,
    include_raw_content: bool = True,
    max_results: int = 3,
) -> dict:
    """
    Busca Tavily e retorna dicionário no formato original.

    Args:
        query: texto da busca
        include_raw_content: incluir ou não raw_content completo
        max_results: nº máx. de resultados

    Returns: dict  →  {'results': [ {...}, ... ]}
    """
    client = TavilyClient()
    return client.search(
        query=query,
        max_results=max_results,
        include_raw_content=include_raw_content,
    )


@traceable
def perplexity_search(
    query: str,
    *,
    model: str = "sonar",
    perplexity_search_loop_count: int = 0,
) -> Dict[str, Any]:
    """
    Busca usando a Perplexity API.

    Necessita `PERPLEXITY_API_KEY` no ambiente.

    Retorna estrutura de resultados similar à Tavily:
        {'results': [ {'title', 'url', 'content', 'raw_content'}, ... ] }
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY não definida no ambiente.")

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Search the web and provide factual information with sources."},
            {"role": "user", "content": query},
        ],
    }
    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", ["https://perplexity.ai"])

    # Formata igual Tavily
    results: List[dict] = [{
        "title": f"Perplexity Search {perplexity_search_loop_count+1}, Source 1",
        "url":   citations[0],
        "content": content,
        "raw_content": content,
    }]
    for i, cit in enumerate(citations[1:], start=2):
        results.append({
            "title": f"Perplexity Search {perplexity_search_loop_count+1}, Source {i}",
            "url": cit,
            "content": "See above.",
            "raw_content": None,
        })
    return {"results": results}


@traceable
def openperplex_search(
    query: str,
    *,
    model: str = "gemini-2.0-flash",
    location: str = "us",
    response_language: str = "en",
) -> Dict[str, Any]:
    """
    Busca via OpenPerplex (wrapper de múltiplas fontes + reranking LLM).

    Requer `OPENPERPLEX_API_KEY` no ambiente.
    """
    key = os.getenv("OPENPERPLEX_API_KEY")
    if not key:
        raise RuntimeError("OPENPERPLEX_API_KEY não definida no ambiente.")

    client = OpenperplexSync(key)
    resp = client.search(
        query=query,
        model=model,
        date_context="2024-08-25",
        location=location,
        response_language=response_language,
        answer_type="text",
        search_type="general",
        return_citations=True,
        return_sources=True,
        return_images=False,
        recency_filter="anytime",
    )
    return {
        "title":   query,
        "content": resp["llm_response"],
        "sources": resp["sources"],
    }
