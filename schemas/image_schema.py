from pydantic import BaseModel
from typing import Optional


# -------------------------------------------------------------------
# 1. 단일 이미지 판별 응답 (POST /api/image)
# -------------------------------------------------------------------
class ImageAnalyzeResponse(BaseModel):
    filename: str       # 업로드된 파일 이름 (예: "knife.jpg")
    ai_guess: str       # AI가 예측한 물건 이름 (예: "cleaver")
    confidence: float   # AI의 확신도, 0.0 ~ 100.0 (예: 97.53)
    is_dangerous: bool  # 유해물품 여부 (True = 기부 불가)
    message: str        # 프론트엔드 화면에 띄워줄 안내 문구


# -------------------------------------------------------------------
# 2. 다중 이미지 일괄 안전 검사 응답 (POST /api/image/check-safety)
#
# [추가 이유]
# Step 1 Fail-Fast 검사는 "전체가 안전한가 아닌가"라는 단일 판단을
# 내리므로, 단일 이미지 응답(ImageAnalyzeResponse)과 구조가 다릅니다.
# - is_safe: 프론트엔드가 Step 2(글쓰기)로 넘어갈지 판단하는 핵심 필드
# - dangerous_file / dangerous_label: 어떤 사진이 왜 걸렸는지 디버깅용
# -------------------------------------------------------------------
class ImageBatchSafetyResponse(BaseModel):
    is_safe: bool               # True = 모든 사진 안전 / False = 유해물품 감지
    message: str                # 사용자에게 보여줄 안내 문구
    dangerous_file: Optional[str] = None   # 유해물품이 감지된 파일 이름 (안전 시 None)
    dangerous_label: Optional[str] = None  # AI가 감지한 유해물품 레이블 (안전 시 None)