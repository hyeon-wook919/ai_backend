from pydantic import BaseModel
from typing import List, Optional

# -------------------------------------------------------------------
# 정책 추천 API의 응답 양식
# -------------------------------------------------------------------

# 1. 개별 정책 하나의 생김새
class PolicyItem(BaseModel):
    id: int             # [추가] 정책의 고유 ID (프론트엔드에서 상세페이지 이동 시 필수)
    이름: str           # 정책 이름 (예: "동절기 에너지 바우처 지원")
    내용: str           # 정책 내용 (예: "취약계층 대상 가구당 15만원 난방비 지원")
    
    # [Tip] 나중에 정부24 API를 연동하면 아래 필드들의 주석을 풀고 사용하시면 됩니다!
    # 지원대상: Optional[str] = None 
    # 신청방법: Optional[str] = None 


# 2. 프론트엔드로 나가는 최종 응답 포장 상자
class RecommendResponse(BaseModel):
    keyword: str                # 검색에 사용된 키워드 (예: "난방비")
    message: str                # 안내 문구 (예: "3개의 정책을 찾았습니다.")
    policies: List[PolicyItem]  # 정책 목록