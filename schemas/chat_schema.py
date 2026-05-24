<<<<<<< HEAD
from pydantic import BaseModel, Field
from typing import List, Optional


# -------------------------------------------------------------------
# 1. 정책 카드 하나의 구조 (프론트엔드 카드 UI용)
#
# [수정 내역]
# - target_criteria 추가 : 지원 대상 (자세히 보기 화면에 표시)
# - support_detail  추가 : 지원 내용 (자세히 보기 화면에 표시)
# - content         : ai_search_text와 동일한 내용 (자세히 보기 본문)
# - ai_search_text  : AI FAISS 검색용 줄글 (사용자에게 노출 안 됨)
# -------------------------------------------------------------------
class PolicyItem(BaseModel):
    policy_id:        int
    policy_name:      str
    category:         str
    agency:           str
    summary:          str                    # 카드 목록에 짧게 표시
    target_criteria:  Optional[str] = None   # 자세히 보기 → 대상
    support_detail:   Optional[str] = None   # 자세히 보기 → 지원내용
    content:          str                    # 자세히 보기 본문 (= ai_search_text)
    ai_search_text:   str                    # FAISS 검색용 (UI 노출 없음)


# -------------------------------------------------------------------
# 2. 프론트엔드 → 백엔드 요청 양식
# -------------------------------------------------------------------
class ChatRequest(BaseModel):
    user_message: str                    # 유저가 입력한 자연어 문장
    member_id:    Optional[int] = None   # 로그인 구현 후 채울 필드 (미입력 시 임시 1번)


# -------------------------------------------------------------------
# 3. 백엔드 → 프론트엔드 응답 양식
# -------------------------------------------------------------------
class ChatResponse(BaseModel):
    extracted_keyword:    str                # 매칭된 1순위 정책명
    ai_confidence:        str                # 검색 방식 (예: "RAG 시맨틱 매칭 성공")
    ai_response:          str                # Gemini가 생성한 공감형 답변
    recommended_policies: List[PolicyItem]   # 추천 정책 카드 리스트
=======
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
>>>>>>> c54ff4be60edae1ccc9c817c1eb3e3182d869de3
