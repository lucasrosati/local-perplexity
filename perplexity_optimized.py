"""
perplexity_markdown_clean.py - Formatação Markdown limpa + UI melhorado
"""

import streamlit as st
from typing import List, Dict, Any
from pydantic import BaseModel
from dotenv import load_dotenv
import time

from langgraph.graph import START, END, StateGraph
from langchain_ollama import ChatOllama

from schemas import ReportState, QueryResult
from utils import tavily_search

load_dotenv()

@st.cache_resource
def get_llm():
    return ChatOllama(
        model="llama3.2:1b",
        temperature=0.1,
        num_predict=512,
        num_ctx=3072,
    )

# --------------------------------------------------------------------------- #
# Prompts para formatação Markdown limpa                                    #
# --------------------------------------------------------------------------- #

QUERY_PROMPT = """Create 2-3 specific search queries to answer: "{user_input}"

Examples:
Question: "How do neural networks work?"
Queries:
- neural networks explained
- how neural networks learn
- neural network architecture

Now create queries for: "{user_input}"
Return only the queries, one per line:"""

FINAL_PROMPT = """You are an AI assistant providing comprehensive answers using clean Markdown formatting.

Question: {user_input}

Search Results:
{search_results}

Write a detailed answer using ONLY standard Markdown formatting:
- Use # for main title, ## for major sections, ### for subsections
- Use **bold** for important terms
- Use - for bullet points (single dash with space)
- Use numbered lists (1. 2. 3.) for sequential steps
- Use > for important quotes or key insights
- Reference sources as [1], [2] naturally in text
- Keep paragraphs clean with line breaks
- Structure: Introduction → Key Concepts → Details → Applications

Write in clean Markdown format:

# {user_input}

[Your detailed answer here using proper Markdown]

## Sources
[You don't need to write sources section, just the answer]
"""

# --------------------------------------------------------------------------- #
# Nós do grafo                                                               #
# --------------------------------------------------------------------------- #

def generate_queries(state: ReportState) -> Dict[str, Any]:
    """Gera queries melhoradas"""
    try:
        llm = get_llm()
        prompt = QUERY_PROMPT.format(user_input=state.user_input)
        
        response = llm.invoke(prompt)
        
        lines = response.content.strip().split('\n')
        queries = []
        
        for line in lines:
            line = line.strip().lstrip('- ').lstrip('1234567890. ')
            if line and len(line) > 3:
                queries.append(line)
        
        if not queries:
            base_terms = state.user_input.lower()
            queries = [
                f"{base_terms} explained",
                f"what is {base_terms}",
                f"how does {base_terms} work"
            ]
        
        queries = queries[:3]
        print(f"✅ Queries geradas: {queries}")
        return {"queries": queries}
        
    except Exception as e:
        print(f"❌ Erro ao gerar queries: {e}")
        base = state.user_input.lower()
        return {"queries": [base, f"what is {base}"]}

def execute_search(state: ReportState) -> Dict[str, Any]:
    """Busca"""
    collected = []
    
    try:
        for i, query in enumerate(state.queries):
            print(f"🔍 Buscando: {query}")
            
            tavily_resp = tavily_search(query, max_results=1, include_raw_content=True)
            
            if tavily_resp.get("results"):
                r = tavily_resp["results"][0]
                
                content = r.get("raw_content") or r.get("content", "")
                content = content[:1000] if content else ""
                
                result = QueryResult(
                    title=r.get("title", "Sem título"),
                    url=r.get("url", ""),
                    resume=content
                )
                
                collected.append(result)
                print(f"✅ Processado: {result.title}")
                
    except Exception as e:
        print(f"❌ Erro na busca: {e}")
    
    print(f"📊 Coletados: {len(collected)} resultados")
    return {"queries_results": collected}

def write_response(state: ReportState) -> Dict[str, Any]:
    """Gera resposta em Markdown limpo"""
    if not state.queries_results:
        return {"final_response": "Não foi possível encontrar informações relevantes."}
    
    try:
        search_context = []
        for i, res in enumerate(state.queries_results, 1):
            search_context.append(f"[{i}] {res.title}: {res.resume}")
        
        context = "\n\n".join(search_context)
        prompt = FINAL_PROMPT.format(
            user_input=state.user_input,
            search_results=context
        )
        
        llm = get_llm()
        response = llm.invoke(prompt)
        
        print("✅ Resposta final gerada")
        return {"final_response": response.content.strip()}
        
    except Exception as e:
        print(f"❌ Erro na resposta final: {e}")
        return {"final_response": f"Erro ao gerar resposta: {str(e)}"}

# --------------------------------------------------------------------------- #
# Grafo                                                                      #
# --------------------------------------------------------------------------- #

@st.cache_resource
def create_graph():
    builder = StateGraph(ReportState)
    
    builder.add_node("generate_queries", generate_queries)
    builder.add_node("execute_search", execute_search)
    builder.add_node("write_response", write_response)
    
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "execute_search")
    builder.add_edge("execute_search", "write_response")
    builder.add_edge("write_response", END)
    
    return builder.compile()

# --------------------------------------------------------------------------- #
# Interface melhorada                                                        #
# --------------------------------------------------------------------------- #

def display_sources_clean(sources: List[QueryResult]):
    """Exibe fontes em estilo limpo"""
    if not sources:
        return
    
    st.markdown("## 📚 Sources")
    
    for i, source in enumerate(sources, 1):
        with st.container():
            # Card de fonte mais limpo
            st.markdown(f"""
            <div style="
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 8px;
                padding: 1rem;
                margin: 0.5rem 0;
                border-left: 3px solid #3b82f6;
            ">
                <div style="color: #3b82f6; font-weight: 600; margin-bottom: 0.5rem;">
                    [{i}] {source.title}
                </div>
                <div style="color: #9ca3af; font-size: 0.9rem; margin-bottom: 0.5rem;">
                    <a href="{source.url}" target="_blank" style="color: #60a5fa; text-decoration: none;">
                        {source.url[:60]}{'...' if len(source.url) > 60 else ''}
                    </a>
                </div>
            </div>
            """, unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="Local Perplexity",
        page_icon="🔍",
        layout="centered",  # Mudado para centered
        initial_sidebar_state="collapsed"
    )
    
    # CSS melhorado para UI mais limpa
    st.markdown("""
    <style>
    /* Fundo escuro */
    .stApp {
        background-color: #0f0f0f !important;
    }
    
    /* Container principal mais estreito */
    .main .block-container {
        background-color: #0f0f0f !important;
        color: #ffffff !important;
        padding-top: 2rem;
        max-width: 800px !important;  /* Mais estreito */
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        font-weight: 600;
    }
    
    /* Input mais estreito e menor */
    .stTextInput > div > div > input {
        background-color: #1a1a1a !important;
        color: #ffffff !important;
        border: 1px solid #333 !important;
        border-radius: 6px !important;
        height: 2.5rem !important;  /* Menor altura */
        font-size: 0.9rem !important;
    }
    
    /* Button moderno */
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 2.5rem !important;
        font-size: 0.9rem !important;
        padding: 0 1.5rem !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3) !important;
        transition: all 0.2s ease !important;
        letter-spacing: 0.5px !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #5b21b6) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4) !important;
    }
    
    .stButton > button:active {
        transform: translateY(0px) !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3) !important;
    }
    
    /* Métricas mais compactas */
    [data-testid="metric-container"] {
        background-color: #1a1a1a !important;
        border: 1px solid #333 !important;
        border-radius: 6px !important;
        padding: 0.75rem !important;  /* Padding menor */
    }
    
    [data-testid="metric-container"] > div {
        color: #ffffff !important;
    }
    
    /* Status container */
    .stStatus {
        background-color: #1a1a1a !important;
        color: #ffffff !important;
    }
    
    /* Remove espaçamentos desnecessários */
    .element-container {
        margin-bottom: 0.5rem !important;
    }
    
    /* Markdown styling limpo */
    .stMarkdown {
        background: transparent !important;
    }
    
    /* Container de resposta mais limpo */
    .answer-container {
        background: #0f0f0f !important;
        border: none !important;
        padding: 1rem 0 !important;
        margin: 1rem 0 !important;
    }
    
    /* Headers do markdown */
    .answer-container h1 {
        color: #ffffff !important;
        font-size: 1.8rem !important;
        margin: 1.5rem 0 1rem 0 !important;
        font-weight: 700 !important;
    }
    
    .answer-container h2 {
        color: #ffffff !important;
        font-size: 1.4rem !important;
        margin: 1.2rem 0 0.8rem 0 !important;
        font-weight: 600 !important;
    }
    
    .answer-container h3 {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        margin: 1rem 0 0.6rem 0 !important;
        font-weight: 600 !important;
    }
    
    /* Paragrafos */
    .answer-container p {
        color: #d1d5db !important;
        line-height: 1.6 !important;
        margin: 0.8rem 0 !important;
    }
    
    /* Listas */
    .answer-container ul, .answer-container ol {
        color: #d1d5db !important;
        margin: 0.8rem 0 !important;
        padding-left: 1.5rem !important;
    }
    
    .answer-container li {
        margin: 0.4rem 0 !important;
        line-height: 1.5 !important;
    }
    
    /* Bold text */
    .answer-container strong {
        color: #3b82f6 !important;
        font-weight: 600 !important;
    }
    
    /* Blockquotes */
    .answer-container blockquote {
        border-left: 3px solid #3b82f6 !important;
        padding-left: 1rem !important;
        margin: 1rem 0 !important;
        color: #9ca3af !important;
        font-style: italic !important;
    }
    
    /* Code */
    .answer-container code {
        background-color: #1a1a1a !important;
        color: #3b82f6 !important;
        padding: 0.2rem 0.4rem !important;
        border-radius: 3px !important;
        font-size: 0.9rem !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header mais compacto
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <h1 style="font-size: 2.2rem; margin-bottom: 0.3rem; color: #ffffff;">
            🔍 Local Perplexity
        </h1>
        <p style="color: #9ca3af; font-size: 1rem; margin-bottom: 0;">AI-powered search with local LLMs</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Input compacto em duas colunas
    col1, col2 = st.columns([4, 1])
    
    with col1:
        question = st.text_input(
            "",
            placeholder="Ask me anything...",
            label_visibility="collapsed"
        )
    
    with col2:
        search_button = st.button("🔍 Search", type="primary", use_container_width=True)
    
    # Busca
    if search_button and question.strip():
        start_time = time.time()
        
        with st.status("🔍 Searching...") as status:
            try:
                graph = create_graph()
                initial_state = ReportState(user_input=question.strip())
                
                final_step = None
                all_data = {}
                
                for step in graph.stream(initial_state.model_dump()):
                    for key, value in step.items():
                        if isinstance(value, dict):
                            all_data.update(value)
                    final_step = step
                
                execution_time = time.time() - start_time
                status.update(label=f"✅ Completed in {execution_time:.1f}s", state="complete")
                
                # Extrai dados
                final_response = None
                sources = []
                queries = []
                
                if final_step:
                    for node_name, node_data in final_step.items():
                        if isinstance(node_data, dict):
                            if "final_response" in node_data:
                                final_response = node_data["final_response"]
                            if "queries_results" in node_data:
                                sources = node_data["queries_results"]
                            if "queries" in node_data:
                                queries = node_data["queries"]
                
                if not final_response:
                    final_response = all_data.get("final_response")
                if not sources:
                    sources = all_data.get("queries_results", [])
                if not queries:
                    queries = all_data.get("queries", [])
                
                # Display
                if final_response:
                    # Métricas compactas
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("⏱️ Time", f"{execution_time:.1f}s")
                    with col2:
                        st.metric("📚 Sources", len(sources))
                    with col3:
                        st.metric("🔍 Queries", len(queries))
                    
                    # Resposta em Markdown LIMPO
                    st.markdown('<div class="answer-container">', unsafe_allow_html=True)
                    st.markdown(final_response)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Fontes
                    if sources:
                        display_sources_clean(sources)
                    
                else:
                    st.error("❌ No answer generated")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main()