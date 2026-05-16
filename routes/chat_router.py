import logging
import numpy as np
import google.generativeai as genai
from fastapi import APIRouter, HTTPException

from schemas.chat_schema import ChatRequest, ChatResponse
from schemas.recommend_schema import PolicyItem

# [중요] recommend_router에서 로드해둔 AI 모델과 임시 데이터를 그대로 빌려옵니다.
from routes.recommend_router import embedder, faiss_index, MOCK_DB_POLICIES

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================================================
# Gemini API 초기 세팅
# =====================================================================
# TODO: 본인의 구글 Gemini API 키로 반드시 교체하세요!
genai.configure(api_key="여기에_본인의_GEMINI_API_키를_입력하세요")
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

@router.post("/", response_model=ChatResponse)
async def process_chat(request: ChatRequest):
    """
    RAG(검색 증강 생성) 기반 챗봇 API
    1. 사용자의 자연어를 벡터로 변환해 FAISS에서 관련 정책을 찾습니다.
    2. 찾은 정책 데이터를 Gemini에게 넘겨주고 따뜻한 위로와 함께 안내하게 합니다.
    """
    message = request.user_message

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해 주세요.")

    if not embedder or not faiss_index:
        raise HTTPException(status_code=503, detail="AI 모델이 아직 로드되지 않았습니다.")

    # ------------------------------------------------------------------
    # Step 1: FAISS 시맨틱 검색 (가장 관련 있는 정책 2개 추출)
    # ------------------------------------------------------------------
    user_vector = embedder.encode([message])
    # k=2: 상위 2개의 정책을 가져옵니다.
    distances, indices = faiss_index.search(np.array(user_vector).astype('float32'), 2)
    
    matched_policies = []
    policy_texts = []
    
    for idx in indices[0]:
        if idx != -1 and idx < len(MOCK_DB_POLICIES):
            policy = MOCK_DB_POLICIES[idx]
            matched_policies.append(policy)
            policy_texts.append(f"- 정책명: {policy['이름']}\n  상세내용: {policy['내용']}")

    # 검색 결과가 하나도 없을 경우 방어 로직
    if not matched_policies:
        return ChatResponse(
            extracted_keyword="알 수 없음",
            ai_confidence="0%",
            ai_response="죄송합니다, 말씀하신 내용과 일치하는 지원 정책을 찾지 못했습니다. 조금 더 구체적으로 말씀해 주시겠어요?",
            recommended_policies=[]
        )

    # ------------------------------------------------------------------
    # Step 2: Gemini RAG (검색 증강 생성) 프롬프트 조립 및 호출
    # ------------------------------------------------------------------
    policies_str = "\n\n".join(policy_texts)
    
    system_prompt = f"""
    너는 취약계층을 위해 따뜻하고 친절하게 안내하는 정부24 복지 상담사 '나눔이'야.
    사용자의 상황에 깊이 공감하고 위로의 말을 먼저 건네줘.
    
    [실제 지원 가능한 복지 정책 정보]
    {policies_str}
    
    [주의사항]
    1. 반드시 위 [실제 지원 가능한 복지 정책 정보]에 있는 내용만 바탕으로 답변할 것. (절대 지어내거나 외부 지식 사용 금지)
    2. 어르신도 이해하기 쉬운 부드러운 말투(~해요, ~습니다)를 사용할 것.
    3. 너무 길지 않게 핵심만 3~4문장으로 따뜻하게 답변할 것.
    """

    logger.info("👉 Gemini 챗봇 응답 생성 중...")
    try:
        response = gemini_model.generate_content(
            system_prompt + "\n\n사용자 질문: " + message
        )
        ai_answer = response.text
    except Exception as e:
        logger.error(f"Gemini API 호출 에러: {e}")
        raise HTTPException(status_code=500, detail="챗봇 응답 생성 중 외부 AI 서버 오류가 발생했습니다.")

    # ------------------------------------------------------------------
    # Step 3: 최종 결과 반환
    # ------------------------------------------------------------------
    policies_for_response = [PolicyItem(**p) for p in matched_policies]
    
    return ChatResponse(
        extracted_keyword=matched_policies[0]['이름'], # 가장 유사도가 높은 정책명
        ai_confidence="RAG 시맨틱 매칭", 
        ai_response=ai_answer,
        recommended_policies=policies_for_response
    )