import logging
import numpy as np
import faiss
from fastapi import APIRouter, HTTPException
from sentence_transformers import SentenceTransformer

from schemas.recommend_schema import PolicyItem, RecommendResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================================================
# [중요] 단일 진실 공급원 (Single Source of Truth) - Vector DB 버전
#
# 기존의 단순 딕셔너리(POLICY_DB)를 대체합니다.
# 사용자 문장의 '의미'를 파악해 정책을 추천하는 FAISS 인덱스를 구동합니다.
# 
# * 주의: 실제 운영 환경에서는 앱 시작 시(lifespan) 한 번만 로드하고,
# DB 팀원이 제공하는 MySQL 데이터를 긁어와서 embeddings를 만들어야 합니다.
# 현재는 테스트 및 데모를 위해 라우터 내부에 가짜 데이터를 세팅합니다.
# =====================================================================

logger.info("AI 임베딩 모델 및 FAISS 인덱스 로드 중... (약 10~20초 소요)")
try:
    # 한국어 문장 임베딩에 특화된 가벼운 모델
    embedder = SentenceTransformer('jhgan/ko-sroberta-multitask')
except Exception as e:
    logger.error(f"NLP 모델 로드 실패: {e}")
    embedder = None

# DB 팀원이 나중에 MySQL에서 넘겨줄 데이터 포맷 (임시 세팅)
MOCK_DB_POLICIES = [
    {"id": 1, "이름": "동절기 에너지 바우처 지원", "내용": "취약계층 대상 가구당 15만원 난방비(도시가스, 연탄) 지원"},
    {"id": 2, "이름": "희망 반찬 배달 사업", "내용": "거동이 불편한 독거노인 및 중증 장애인 주 2회 밑반찬 배달"},
    {"id": 3, "이름": "아름다운 옷장 겨울나기", "내용": "저소득층 대상 기부받은 방한복, 겨울 패딩 무상 제공"},
    {"id": 4, "이름": "결식우려 아동 급식카드", "내용": "결식 우려가 있는 18세 미만 아동에게 월 15만원 급식카드 지급"}
]

# 서버 켜질 때 FAISS 인덱스 구축 (1회 실행)
if embedder:
    # 정책 이름과 내용을 합쳐서 AI가 의미를 파악할 수 있는 텍스트로 만듦
    texts_to_embed = [f"{p['이름']}. {p['내용']}" for p in MOCK_DB_POLICIES]
    embeddings = embedder.encode(texts_to_embed)
    
    dimension = embeddings.shape[1] # 차원 수 (일반적으로 768)
    faiss_index = faiss.IndexFlatL2(dimension)
    faiss_index.add(np.array(embeddings).astype('float32'))
else:
    faiss_index = None

# =====================================================================
# API 엔드포인트
# =====================================================================

@router.get("/", response_model=RecommendResponse)
async def get_recommendation(keyword: str, top_k: int = 3):
    """
    사용자의 문장(keyword)을 분석하여 가장 의미가 비슷한 정책을 추천합니다.
    예) GET /api/recommend/?keyword=요즘 너무 춥고 가스비가 비싸서 힘들어
    """
    if not embedder or not faiss_index:
        raise HTTPException(status_code=503, detail="AI 검색 엔진이 아직 준비되지 않았습니다.")

    if not keyword or not keyword.strip():
        return RecommendResponse(
            keyword=keyword, 
            message="검색어나 상황을 입력해주세요.", 
            policies=[]
        )

    # 1. 사용자가 입력한 자연어 문장을 벡터(숫자)로 변환
    user_vector = embedder.encode([keyword])

    # 2. FAISS 검색 (가장 의미가 비슷한 top_k 개의 정책 인덱스 추출)
    # 거리가 짧을수록(distances가 낮을수록) 유사도가 높음
    distances, indices = faiss_index.search(np.array(user_vector).astype('float32'), top_k)

    # 3. 매칭된 인덱스를 바탕으로 DB에서 실제 정책 정보 매핑
    matched_policies = []
    for idx in indices[0]:
        if idx != -1 and idx < len(MOCK_DB_POLICIES): # 안전장치 (유효한 인덱스인지 확인)
            matched_policies.append(MOCK_DB_POLICIES[idx])

    # 4. 결과 반환 (프론트엔드 스키마 형태 유지)
    if not matched_policies:
        logger.info(f"정책 검색 결과 없음: keyword='{keyword}'")
        return RecommendResponse(
            keyword=keyword,
            message="관련된 맞춤 정책을 찾지 못했습니다.",
            policies=[]
        )

    logger.info(f"정책 시맨틱 검색 성공: '{keyword}' -> {len(matched_policies)}건 반환")
    return RecommendResponse(
        keyword=keyword,
        message=f"입력하신 상황에 맞는 정책 {len(matched_policies)}개를 찾았습니다.",
        policies=[PolicyItem(**p) for p in matched_policies]
    )