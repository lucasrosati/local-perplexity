"""
perplexity.py  —  Streamlit + LangGraph + LLMs locais (Ollama)

Fluxo:

    1) build_first_queries   → gera 3-5 queries sobre a pergunta do usuário
    2) serial_search         → executa cada query no Tavily, sintetiza via LLM
                               e acumula QueryResult (tudo em série = sem conflito)
    3) final_writer          → compila resposta final e referências
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports                                                                     #
# --------------------------------------------------------------------------- #
from typing import List, Dict
import streamlit as st
from pydantic import BaseModel
from dotenv import load_dotenv

from langgraph.graph import START, END, StateGraph
from langchain_ollama import ChatOllama

from schemas import ReportState, QueryResult
from prompts import (
    build_queries,
    resume_search,
    build_final_response,
)
from utils import tavily_search

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
load_dotenv()  # lê variáveis do .env

# LLM que gera as queries e faz mini-resumos de resultados
planner_llm = ChatOllama(model="llama3:8b-instruct-q4_K_S")

# LLM que escreve a resposta final longa
reasoning_llm = ChatOllama(model="deepseek-r1:14b")

# --------------------------------------------------------------------------- #
# Nós do grafo                                                                #
# --------------------------------------------------------------------------- #
def build_first_queries(state: ReportState) -> Dict[str, List[str]]:
    """Planeja 3-5 queries a partir da pergunta do usuário."""
    class QueryList(BaseModel):
        queries: List[str]

    prompt = build_queries.format(user_input=state.user_input)
    
    try:
        queries = (
            planner_llm
            .with_structured_output(QueryList)
            .invoke(prompt)
            .queries
        )
        print(f"Queries geradas: {queries}")  # Debug
        return {"queries": queries}
    except Exception as e:
        print(f"Erro ao gerar queries: {e}")
        # Fallback com queries básicas
        return {"queries": [state.user_input]}


def serial_search(state: ReportState) -> Dict[str, List[QueryResult]]:
    """
    Executa as queries em série (evita concorrência).
    Para cada resultado, produz um QueryResult.
    """
    collected: List[QueryResult] = []
    
    print(f"Executando busca para {len(state.queries)} queries")  # Debug

    for i, q in enumerate(state.queries):
        print(f"Buscando query {i+1}: {q}")  # Debug
        
        try:
            tavily_resp = tavily_search(q, max_results=1, include_raw_content=True)
            if not tavily_resp.get("results"):
                print(f"Nenhum resultado para query: {q}")
                continue

            r = tavily_resp["results"][0]
            raw = r.get("raw_content") or r["content"]

            synth_prompt = resume_search.format(
                user_input=state.user_input,
                search_results=raw,
            )
            
            summary = planner_llm.invoke(synth_prompt).content

            query_result = QueryResult(
                title=r["title"], 
                url=r["url"], 
                resume=summary
            )
            collected.append(query_result)
            print(f"Resultado processado: {query_result.title}")  # Debug
            
        except Exception as e:
            print(f"Erro ao processar query '{q}': {e}")
            continue

    print(f"Total de resultados coletados: {len(collected)}")  # Debug
    return {"queries_results": collected}


def final_writer(state: ReportState) -> Dict[str, str]:
    """Gera resposta final longa + referências."""
    print(f"Gerando resposta final com {len(state.queries_results)} resultados")  # Debug
    
    if not state.queries_results:
        return {"final_response": "Não foi possível encontrar informações relevantes para sua pergunta."}
    
    body_parts, ref_parts = [], []

    for idx, res in enumerate(state.queries_results, start=1):
        body_parts.append(
            f"[{idx}]\nTitle: {res.title}\nURL: {res.url}\n"
            f"Content: {res.resume}\n----------------\n"
        )
        ref_parts.append(f"[{idx}] - [{res.title}]({res.url})")

    prompt = build_final_response.format(
        user_input=state.user_input,
        search_results="".join(body_parts),
    )
    
    try:
        final_text = reasoning_llm.invoke(prompt).content
        full_answer = f"{final_text}\n\nReferences:\n" + "\n".join(ref_parts)
        return {"final_response": full_answer}
    except Exception as e:
        print(f"Erro ao gerar resposta final: {e}")
        return {"final_response": f"Erro ao gerar resposta: {str(e)}"}


# --------------------------------------------------------------------------- #
# Construção do grafo                                                         #
# --------------------------------------------------------------------------- #
def create_graph():
    """Cria e retorna o grafo compilado."""
    builder = StateGraph(ReportState)
    builder.add_node("build_queries", build_first_queries)
    builder.add_node("serial_search", serial_search)
    builder.add_node("final_writer", final_writer)

    builder.add_edge(START, "build_queries")
    builder.add_edge("build_queries", "serial_search")
    builder.add_edge("serial_search", "final_writer")
    builder.add_edge("final_writer", END)

    return builder.compile()

graph = create_graph()

# --------------------------------------------------------------------------- #
# Streamlit UI                                                                #
# --------------------------------------------------------------------------- #
def main():
    st.set_page_config(page_title="Local Perplexity")
    st.title("🌎 Local Perplexity")

    question = st.text_input(
        "Qual a sua pergunta?",
        value="How is the process of building an LLM?"
    )

    if st.button("Pesquisar") and question.strip():
        with st.status("Gerando resposta…") as status:
            try:
                # Estado inicial
                initial_state = ReportState(user_input=question.strip())
                
                # Debug
                st.write("Executando busca...")
                
                # Executa o grafo
                result_state = graph.invoke(initial_state.dict())
                
                status.update(label="Resposta gerada!", state="complete")
                
                # Exibe resultado
                if result_state.get("final_response"):
                    st.markdown(result_state["final_response"])
                else:
                    st.error("Nenhuma resposta foi gerada.")
                    
            except Exception as e:
                status.update(label="Erro na execução", state="error")
                st.error(f"Erro: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

if __name__ == "__main__":
    main()