from pydantic import BaseModel
from typing import List

from schemas.recommend_schema import PolicyItem


# -------------------------------------------------------------------
# 챗봇 API의 요청/응답 양식
#
# [수정 내역]
# - ChatResponse 클래스 추가 (기존엔 요청 스키마만 있고 응답 스키마 누락)
# - ChatUnclearResponse 클래스 추가
#   (AI 확신도가 낮아 카테고리를 특정 못 할 때 반환하는 응답 양식)
# -------------------------------------------------------------------


# 1. 프론트엔드 → 백엔드 요청 양식
class ChatRequest(BaseModel):
    user_message: str   # 사용자가 챗봇에 입력한 문장 (예: "저체온증에 걸릴 것 같아요")


# 2. 백엔드 → 프론트엔드 응답 양식 (정상: 카테고리 특정 성공)
class ChatResponse(BaseModel):
    extracted_keyword: str              # AI가 파악한 핵심 카테고리 (예: "난방비")
    ai_confidence: str                  # AI의 확신도 (예: "87.3%")
    ai_response: str                    # 챗봇이 사용자에게 전달할 자연어 응답 문장
    recommended_policies: List[PolicyItem]  # 추천된 정책 목록


# 3. 백엔드 → 프론트엔드 응답 양식 (예외: AI가 카테고리를 특정하지 못한 경우)
class ChatUnclearResponse(BaseModel):
    ai_response: str        # "어떤 도움이 필요하신지 더 자세히 말씀해 주세요." 같은 안내 문구
    recommended_policies: list  # 빈 리스트 []