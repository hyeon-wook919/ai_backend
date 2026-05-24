import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.image_router import router as image_router
<<<<<<< HEAD
=======
from routes.recommend_router import router as recommend_router
>>>>>>> c54ff4be60edae1ccc9c817c1eb3e3182d869de3
from routes.chat_router import router as chat_router
from routes.post_router import router as post_router


# -------------------------------------------------------------------
# 로깅 설정
<<<<<<< HEAD
=======
# 각 라우터와 모델 파일에서 logger.info(), logger.error() 등을 쓸 때
# 이 설정 덕분에 터미널에 시간/레벨/메시지가 찍힙니다.
>>>>>>> c54ff4be60edae1ccc9c817c1eb3e3182d869de3
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="취약 계층 나눔 플랫폼",
    description="기부 물품 유해성 판별 및 취약계층 맞춤 정책 추천 API",
    version="1.0.0",
)

# -------------------------------------------------------------------
<<<<<<< HEAD
# CORS 설정 (배포 시 allow_origins를 실제 도메인으로 교체)
=======
# CORS 설정
# allow_origins=["*"] 은 개발 단계에서만 사용하세요.
# 실제 배포 시에는 프론트엔드 도메인으로 좁혀야 합니다.
# 예) allow_origins=["https://your-frontend.com"]
>>>>>>> c54ff4be60edae1ccc9c817c1eb3e3182d869de3
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# 라우터 등록
#
# 전체 API 흐름:
# [Step 1] POST /api/image/check-safety  → 다중 이미지 유해물 일괄 검사 (Fail-Fast)
#          POST /api/image               → 단일 이미지 빠른 판별
# [Step 2] POST /api/post/generate-post  → AI 기부글 자동 생성 (Gemini 2.5 Flash)
<<<<<<< HEAD
# [Step 3] POST /api/chat                → 챗봇 정책 추천 (RAG + Gemini)
# -------------------------------------------------------------------
app.include_router(image_router, prefix="/api/image", tags=["1. 이미지 판별 (ViT)"])
app.include_router(post_router,  prefix="/api/post",  tags=["2. AI 기부글 생성 (Gemini)"])
app.include_router(chat_router,  prefix="/api/chat",  tags=["3. 챗봇 (RAG + Gemini)"])


# -------------------------------------------------------------------
# 헬스체크
=======
# [기타]   GET  /api/recommend           → 정책 키워드 검색
#          POST /api/chat                → 챗봇 정책 추천 (NLP)
# -------------------------------------------------------------------
app.include_router(image_router,     prefix="/api/image",     tags=["1. 이미지 판별 (ViT)"])
app.include_router(post_router,      prefix="/api/post",      tags=["2. AI 기부글 생성 (Gemini)"])
app.include_router(recommend_router, prefix="/api/recommend", tags=["3. 정책 추천"])
app.include_router(chat_router,      prefix="/api/chat",      tags=["4. 챗봇 (NLP)"])


# -------------------------------------------------------------------
# 헬스체크 엔드포인트
# 배포 환경에서 로드밸런서, 모니터링 도구가 주기적으로 호출합니다.
>>>>>>> c54ff4be60edae1ccc9c817c1eb3e3182d869de3
# -------------------------------------------------------------------
@app.get("/health", tags=["서버 상태"])
async def health_check():
    return {"status": "ok", "service": "취약 계층 나눔 플랫폼"}