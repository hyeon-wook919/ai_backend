from pydantic import BaseModel
from typing import List, Optional


class PolicyItem(BaseModel):
    policy_id:        int
    policy_name:      str
    category:         str
    agency:           str
    summary:          str
    target_criteria:  Optional[str] = None
    support_detail:   Optional[str] = None
    content:          str
    ai_search_text:   str


class ChatRequest(BaseModel):
    user_message: str
    member_id:    Optional[int] = None  


class ChatResponse(BaseModel):
    extracted_keyword:    str
    ai_confidence:        str
    ai_response:          str
    recommended_policies: List[PolicyItem]