# 취약 계층/ 회원정보 -> 맞춤 물품 추천
from fastapi import APIRouter
from schemas.recommend_schema import RecommendResponse

router = APIRouter()

# [더미 데이터] 
DUMMY_POLICY_DB = {
    "난방비": [
        {"이름": "동절기 에너지 바우처 지원", "내용": "취약계층 대상 가구당 10만원 난방비 지원"},
        {"이름": "사랑의 연탄 나눔", "내용": "지역 내 독거노인 연탄 200장 무상 지원"}
    ],
    "식비": [
        {"이름": "결식우려 아동 급식카드", "내용": "월 15만원 한도 아동 급식카드 지급"},
        {"이름": "희망 반찬 배달", "내용": "거동이 불편한 어르신 주 2회 밑반찬 배달"}
    ],
    "의류": [
        {"이름": "아름다운 옷장", "내용": "기부받은 방한복 및 겨울 패딩 무상 제공"}
    ]
}

# 내부 매칭 함수 (챗봇 라우터에서 빌려 쓸 수 있도록 독립된 함수로 분리)
def find_policies_by_keyword(keyword: str):
    return DUMMY_POLICY_DB.get(keyword, [])


@router.get("/")
async def get_recommendation(keyword: str):
    policies = find_policies_by_keyword(keyword)
    if not policies:
        return {"keyword": keyword, "message": "관련된 정책이 없습니다.", "policies": []}
    return {"keyword": keyword, "message": f"{len(policies)}개의 정책을 찾았습니다.", "policies": policies}