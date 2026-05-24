import logging
import numpy as np
import faiss
import os

from fastapi import APIRouter, HTTPException
from sentence_transformers import SentenceTransformer
from google.genai import types, Client
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from schemas.chat_schema import ChatRequest, ChatResponse, PolicyItem

logger = logging.getLogger(__name__)
router = APIRouter()

# -------------------------------------------------------------------
# 1. 환경변수 로드
# -------------------------------------------------------------------
load_dotenv()

# -------------------------------------------------------------------
# 2. DB 연결
# -------------------------------------------------------------------
DB_URL = os.getenv("DB_URL")


try:
    db_engine = create_engine(DB_URL, connect_args={"ssl": {}})
    logger.info("✅ Aiven DB 엔진 초기화 완료!")
except Exception as e:
    logger.error(f"❌ DB 연결 세팅 실패: {e}")
    db_engine = None

# -------------------------------------------------------------------
# 3. Gemini 클라이언트
# -------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

gemini_client = Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------
# 4. 한국어 임베딩 모델 로드
# -------------------------------------------------------------------
logger.info("👉 한국어 AI 임베딩 모델 로드 중...")
try:
    embedder = SentenceTransformer('jhgan/ko-sroberta-multitask')
    logger.info("✅ 임베딩 모델 로드 완료!")
except Exception as e:
    logger.error(f"❌ 임베딩 모델 로드 실패: {e}")
    embedder = None

# -------------------------------------------------------------------
# 5. DB에서 정책 로드 + FAISS 인덱스 구축
#
# [컬럼 구조]
# policy_id        : PK
# policy_name      : 정책명
# category         : 카테고리 (생활비/주거/의료/교육/양육/일자리/복지)
# agency           : 기관
# summary          : 요약 - 카드 목록에 짧게 표시
# target_criteria  : 지원 대상 - 자세히 보기 화면
# support_detail   : 지원 내용 - 자세히 보기 화면
# content          : 자세히 보기 본문 (= ai_search_text와 동일 내용)
# ai_search_text   : FAISS 검색용 줄글 (사용자에게 노출 안 됨)
# -------------------------------------------------------------------
POLICIES_CACHE = []
faiss_index = None


def build_faiss_index():
    global POLICIES_CACHE, faiss_index

    if not db_engine or not embedder:
        logger.error("❌ DB 또는 임베딩 모델이 없어 FAISS 인덱스 구축 불가")
        return

    try:
        with db_engine.connect() as conn:
            rows = conn.execute(text(
                """
                SELECT policy_id, policy_name, category, agency, summary,
                       target_criteria, support_detail, content, ai_search_text
                FROM POLICY
                ORDER BY policy_id
                """
            )).fetchall()

        if not rows:
            logger.warning("⚠️ POLICY 테이블에 데이터가 없습니다.")
            return

        POLICIES_CACHE = [
            {
                "policy_id":       row[0],
                "policy_name":     " ".join(row[1].split()),
                "category":        row[2],
                "agency":          row[3],
                "summary":         " ".join(row[4].split()),
                "target_criteria": row[5],   # 지원 대상
                "support_detail":  row[6],   # 지원 내용
                "content":         row[7],   # 자세히 보기 본문
                "ai_search_text":  row[8],   # FAISS 검색용
            }
            for row in rows
        ]

        logger.info(f"⚡ POLICY {len(POLICIES_CACHE)}건 로드 완료. FAISS 인덱싱 시작...")

        texts = [p["ai_search_text"] for p in POLICIES_CACHE]
        embeddings = embedder.encode(texts)

        dimension = embeddings.shape[1]
        faiss_index = faiss.IndexFlatL2(dimension)
        faiss_index.add(np.array(embeddings).astype("float32"))

        logger.info("✅ FAISS 인덱싱 완료! 시맨틱 엔진 준비 완료.")

    except Exception as e:
        logger.error(f"❌ FAISS 인덱스 구축 실패: {e}")
        logger.warning("⚠️ 챗봇 기능을 사용할 수 없습니다.")


# 서버 시작 시 1회 실행
build_faiss_index()


# -------------------------------------------------------------------
# 6. 챗봇 엔드포인트
#
# 흐름:
# [유저 질문]
#   → FAISS 시맨틱 매칭으로 관련 정책 2개 추출
#   → SEARCH_HISTORY DB에 검색 기록 저장
#   → Gemini가 정책 내용 기반으로 따뜻한 말투로 답변 생성
#   → AI 답변 + 추천 정책 카드 반환
# -------------------------------------------------------------------
@router.post("/", response_model=ChatResponse)
async def process_chat(request: ChatRequest):
    message = request.user_message

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해 주세요.")

    if not embedder or faiss_index is None:
        raise HTTPException(status_code=503, detail="AI 엔진이 준비되지 않았습니다.")

    if not POLICIES_CACHE:
        raise HTTPException(status_code=503, detail="정책 데이터가 로드되지 않았습니다.")

    # ------------------------------------------------------------------
    # Step 1: FAISS 시맨틱 매칭 (상위 2개 정책 추출)
    # ------------------------------------------------------------------
    user_vector = embedder.encode([message])
    distances, indices = faiss_index.search(np.array(user_vector).astype("float32"), 2)

    matched_policies = []
    policy_texts_for_gemini = []

    for idx in indices[0]:
        if idx != -1 and idx < len(POLICIES_CACHE):
            policy = POLICIES_CACHE[idx]
            matched_policies.append(policy)
            policy_texts_for_gemini.append(
                f"- 정책명: {policy['policy_name']}\n  상세내용: {policy['ai_search_text']}"
            )

    if not matched_policies:
        return ChatResponse(
            extracted_keyword="알 수 없음",
            ai_confidence="결과 없음",
            ai_response=(
                "죄송합니다. 말씀하신 내용과 연관된 정책 정보를 찾지 못했습니다. "
                "더 자세히 말씀해 주시겠어요?"
            ),
            recommended_policies=[]
        )

    # ------------------------------------------------------------------
    # Step 2: SEARCH_HISTORY DB 저장
    # member_id: 요청에서 받은 값 사용, 없으면 임시 1번
    # DB 저장 실패해도 챗봇 응답은 정상 반환
    # ------------------------------------------------------------------
    member_id = request.member_id or 1

    try:
        if db_engine:
            with db_engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO SEARCH_HISTORY
                            (member_id, query_text, search_date, recommend_policy_id)
                        VALUES
                            (:member_id, :query_text, NOW(), :recommend_policy_id)
                    """),
                    {
                        "member_id":           member_id,
                        "query_text":          message,
                        "recommend_policy_id": matched_policies[0]["policy_id"],
                    }
                )
            logger.info(f"🚀 검색 기록 저장 완료! member_id={member_id}, policy_id={matched_policies[0]['policy_id']}")
    except Exception as e:
        logger.error(f"❌ DB 저장 실패: {e}")

    # ------------------------------------------------------------------
    # Step 3: Gemini 답변 생성
    # ------------------------------------------------------------------
    policies_str = "\n\n".join(policy_texts_for_gemini)
    system_prompt = f"""
너는 취약계층 나눔/기부 플랫폼의 따뜻하고 다정한 복지 전담 상담사 '나눔이'야.
유저가 경제적 어려움이나 고충을 털어놓으면 첫 문장에 반드시 진심 어린 위로와 공감을 건네줘.

[DB에서 엄선해온 실제 지원 정책 정보]
{policies_str}

[답변 원칙]
1. 위 [실제 지원 정책 정보]에 기반해서만 답변할 것. 없는 정책을 지어내지 말 것.
2. 어르신이나 소외계층도 읽기 편하게 친절하고 부드러운 격식체(~습니다, ~해요)를 쓸 것.
3. 정책의 핵심(혜택 및 대상)을 강조하되 3~4문장 내외로 간결하게 요약할 것.
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"사용자 고충: {message}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            )
        )
        ai_answer = response.text
    except Exception as e:
        logger.error(f"Gemini API 통신 실패: {e}")
        raise HTTPException(status_code=500, detail="AI 응답 생성 중 오류가 발생했습니다.")

    # ------------------------------------------------------------------
    # Step 4: 최종 응답 반환
    # ------------------------------------------------------------------
    return ChatResponse(
        extracted_keyword=matched_policies[0]["policy_name"],
        ai_confidence="RAG 시맨틱 매칭 성공",
        ai_response=ai_answer,
        recommended_policies=[PolicyItem(**p) for p in matched_policies]
    )