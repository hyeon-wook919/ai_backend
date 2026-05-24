import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.image_router import router as image_router
from routes.chat_router import router as chat_router
from routes.post_router import router as post_router


# -------------------------------------------------------------------
# 로깅 설정
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
# CORS 설정 (배포 시 allow_origins를 실제 도메인으로 교체)
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
# [Step 1] POST /api/image/check-safety  → 다중 이미지 유해물 일괄 검사
#          POST /api/image               → 단일 이미지 빠른 판별
# [Step 2] POST /api/post/generate-post  → AI 기부글 자동 생성 (Gemini)
# [Step 3] POST /api/chat                → 챗봇 정책 추천 (RAG + Gemini)
# -------------------------------------------------------------------
app.include_router(image_router, prefix="/api/image", tags=["1. 이미지 판별 (ViT)"])
app.include_router(post_router,  prefix="/api/post",  tags=["2. AI 기부글 생성 (Gemini)"])
app.include_router(chat_router,  prefix="/api/chat",  tags=["3. 챗봇 (RAG + Gemini)"])


# -------------------------------------------------------------------
# 헬스체크
# -------------------------------------------------------------------
@app.get("/health", tags=["서버 상태"])
async def health_check():
    return {"status": "ok", "service": "취약 계층 나눔 플랫폼"}