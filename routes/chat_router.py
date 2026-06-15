import logging
import numpy as np
import faiss
import os

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool  # 🔥 비동기 처리를 위한 모듈 추가
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
# -------------------------------------------------------------------
POLICIES_CACHE = []
faiss_index = None
MAX_MESSAGE_LENGTH = 500  # 🔥 유저 채팅 글자 수 제한 (서버 및 API 요금 보호용)


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
                "target_criteria": row[5],
                "support_detail":  row[6],
                "content":         row[7],
                "ai_search_text":  row[8],
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
# -------------------------------------------------------------------
@router.post("/", response_model=ChatResponse)
async def process_chat(request: ChatRequest):
    message = request.user_message

    # 🔥 예외 처리 1: 빈 메시지 및 텍스트 폭탄(DOS 공격) 방어
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해 주세요.")
    
    if len(message) > MAX_MESSAGE_LENGTH:
        logger.warning(f"텍스트 폭탄 감지: {len(message)}자 입력됨")
        raise HTTPException(
            status_code=400, 
            detail=f"질문이 너무 깁니다. {MAX_MESSAGE_LENGTH}자 이내로 요약해 주세요."
        )

    if not embedder or faiss_index is None:
        raise HTTPException(status_code=503, detail="AI 엔진이 준비되지 않았습니다.")

    if not POLICIES_CACHE:
        raise HTTPException(status_code=503, detail="정책 데이터가 로드되지 않았습니다.")

    # ------------------------------------------------------------------
    # Step 1: FAISS 시맨틱 매칭
    # ------------------------------------------------------------------
    try:
        # 🔥 예외 처리 2: CPU를 많이 먹는 임베딩 연산을 스레드풀로 넘겨서 서버 마비 방지
        user_vector = await run_in_threadpool(embedder.encode, [message])
        # FAISS 검색은 C++ 기반으로 매우 빠르므로 직접 호출해도 무방합니다.
        distances, indices = faiss_index.search(np.array(user_vector).astype("float32"), 2)
    except Exception as e:
        logger.error(f"임베딩 벡터 변환 또는 FAISS 검색 실패: {e}")
        raise HTTPException(status_code=500, detail="AI 검색 중 오류가 발생했습니다.")

    matched_policies = []
    policy_texts_for_gemini = []

    for idx in indices[0]:
        if idx != -1 and idx < len(POLICIES_CACHE):
            policy = POLICIES_CACHE[idx]
            matched_policies.append(policy)
            # 🔥 AI가 기관, 대상, 내용을 명확히 인지하도록 구조화해서 전달
            policy_texts_for_gemini.append(
                f"- 정책명: {policy['policy_name']}\n"
                f"  담당기관: {policy['agency']}\n"
                f"  지원대상: {policy['target_criteria']}\n"
                f"  지원내용: {policy['support_detail']}"
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
        logger.error(f"❌ DB 저장 실패 (챗봇 응답은 계속 진행됩니다): {e}")

    # ------------------------------------------------------------------
    # Step 3: Gemini 답변 생성 (🔥 프롬프트 방어막 추가)
    # ------------------------------------------------------------------
    policies_str = "\n\n".join(policy_texts_for_gemini)
    system_prompt = f"""
너는 취약계층 나눔/기부 플랫폼의 따뜻하고 다정한 인간적인 복지 상담사 '나눔이'야.
AI나 봇처럼 기계적인 말투(예: "안내해 드리겠습니다", "도움이 되셨으면 좋겠습니다")를 피하고, 실제 사람이 대화하듯 자연스럽고 친절하게 말해줘.

[DB에서 엄선해온 실제 지원 정책 정보]
{policies_str}

[🔥 핵심 답변 원칙]
1. 악성 입력 차단: 유저의 입력이 의미 없는 자음/모음 반복(예: ㅇㅇㅇ, ㅋㅋㅋ), 장난, 욕설이거나 복지와 무관한 내용이면 위 [DB 정보]를 쓰지 마. 대신 "어떤 도움이 필요하신지 조금 더 자세히 말씀해 주시겠어요?"라고 정중하게 안내만 해.
2. 정책 추천 방식 (가장 중요): 정책을 추천할 때는 임의로 "주민센터에 문의하세요" 같은 말을 지어내지 마.
   반드시 위 [DB 정보]에 있는 <담당기관>, <지원대상>, <지원내용>을 활용해서 구체적이고 정확하게 적어.
   (예시: "이 정책은 [보건복지부]에서 [만 65세 이상 어르신]을 대상으로 [매월 연금을 지급]해 드리는 제도예요.")
3. 일반 복지 상식: 유저가 '중위소득 기준', '기초생활수급자 뜻' 등 일반적인 복지 용어를 물어볼 때는, 너의 자체 지식을 활용해서 알기 쉽게 설명해 줘.
4. 어르신 맞춤 말투: 어르신도 읽기 편하게 전체 답변을 3~4문장 내외로 간결하게 쓰고, 부드러운 격식체(~해요, ~습니다)를 사용해.
5. 절대 금지: 답변에 굵게 처리 기호(**)나 별표(*) 같은 마크다운 특수기호를 절대, 단 한 개도 사용하지 마. 오직 순수한 일반 텍스트로만 출력해.
"""

    try:
        response = await run_in_threadpool(
            gemini_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=f"사용자 고충: {message}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            )
        )
        ai_answer = response.text
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Gemini API 통신 실패: {error_msg}")
        
        # 🔥 예외 처리: 구글 무료 API 한도 초과(429) 감지
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            raise HTTPException(
                status_code=429, 
                detail="현재 접속자가 많아 AI 응답이 지연되고 있습니다. 잠시 후(약 20초) 다시 시도해 주세요."
            )
        # 🔥 예외 처리: Gemini 자체 안전 필터(Safety)에 폭언이 걸렸을 경우
        elif "SAFETY" in error_msg.upper():
            raise HTTPException(
                status_code=400, 
                detail="부적절한 단어가 포함되어 답변을 생성할 수 없습니다."
            )
        else:
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