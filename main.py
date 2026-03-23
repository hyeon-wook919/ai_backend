# CORS 설정 및 전체 라우터 연결

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.image_router import router as image_router
from routes.recommend_router import router as recommend_router
from routes.chat_router import router as chat_router

app = FastAPI(title="취약 계층 나눔 플랫폼")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,

    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(image_router, prefix="/api/image", tags=["1. 이미지 판별 (ViT)"])
app.include_router(recommend_router, prefix="/api/recommend", tags=["2. 맞춤 추천"])
app.include_router(chat_router, prefix="/api/chat", tags=["3. 챗봇 텍스트 (KoBERT)"])
