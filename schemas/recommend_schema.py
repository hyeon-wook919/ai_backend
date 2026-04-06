from pydantic import BaseModel
from typing import List

# 1. 개별 정책 하나하나의 생김새 정의
class PolicyItem(BaseModel):
    이름: str
    내용: str

# 2. 프론트엔드로 최종적으로 나갈 포장 상자 (응답 양식)
class RecommendResponse(BaseModel):
    keyword: str
    message: str
    policies: List[PolicyItem]