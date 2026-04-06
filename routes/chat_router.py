from fastapi import APIRouter
from pydantic import BaseModel
from routes.recommend_router import find_policies_by_keyword

# 핵심! 전역 창고(ai_models)에서 NLP 뇌를 가져옵니다.
from core.ai_models import nlp_classifier

from schemas.chat_schema import ChatRequest

router = APIRouter()



# AI에게 주어질 '객관식 보기' 리스트입니다. (여기에 원하는 정책 카테고리를 계속 추가하면 됩니다)
POLICY_CATEGORIES = ["난방비", "식비", "의류"]

@router.post("/")
async def process_chat(request: ChatRequest):
    message = request.user_message

    # ---------------------------------------------------------
    # 🤖 진짜 인공지능(NLP) 출동!
    # ---------------------------------------------------------
    # AI에게 사용자의 말을 던져주고, "난방비, 식비, 의류 중 어디에 제일 가까워?" 라고 묻습니다.
    ai_result = nlp_classifier(message, POLICY_CATEGORIES)
    
    # AI가 채점한 결과 중, 1등 카테고리(이름)와 그 확신도(점수)를 뽑아냅니다.
    top_category = ai_result['labels'][0]
    confidence_score = ai_result['scores'][0]

    # 예외 처리: 만약 AI의 1등 확신도가 40%(0.4)도 안 된다면? (예: "오늘 날씨 좋네" 같은 엉뚱한 말)
    if confidence_score < 0.4:
        return {
            "ai_response": "어떤 도움이 필요하신지 조금만 더 자세히 말씀해 주시겠어요?",
            "recommended_policies": []
        }

    # 확신도가 충분히 높다면, 그 1등 카테고리를 핵심 키워드로 사용합니다!
    extracted_keyword = top_category

    # DB에서 정책 검색
    policies = find_policies_by_keyword(extracted_keyword)

    # 챗봇 응답 생성
    ai_response = f"말씀하신 내용을 들어보니 '{extracted_keyword}' 지원이 필요해 보이시네요. 신청 가능한 정책을 찾아보았습니다."

    return {
        "extracted_keyword": extracted_keyword,
        "ai_confidence": f"{round(confidence_score * 100, 1)}%", # AI가 얼마나 확신했는지 %로 보여줌
        "ai_response": ai_response,
        "recommended_policies": policies
    }