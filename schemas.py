from typing import List
from pydantic import BaseModel

class QueryResult(BaseModel):
    title: str
    url: str
    resume: str

class ReportState(BaseModel):
    user_input: str = ""
    queries: List[str] = []
    queries_results: List[QueryResult] = []
    final_response: str = ""