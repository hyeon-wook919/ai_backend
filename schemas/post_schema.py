from pydantic import BaseModel
from typing import List, Optional

# (기존) 1. 단순 이미지 분석용 양식
class ImageAnalyzeResponse(BaseModel):
    filename: str
    ai_guess: str
    confidence: float
    is_dangerous: bool
    message: str

# (신규) 2. 당근마켓형 다중 이미지 AI 글쓰기 응답 양식
class PostGenerationResponse(BaseModel):
    is_same_item: bool = True           # 사진들이 동일한 물품인지 여부
    category: str                     # 카테고리 (예: 패션잡화/지갑)
    suggested_title: str              # AI가 추천한 매력적인 제목
    extracted_features: list[str]     # 뽑아낸 특징들 (리스트 형태)
    ai_generated_post: str            # 최종 완성된 판매글 본문
    confidence: float                 # AI의 확신도

class ImageBatchSafetyResponse(BaseModel):
    is_safe: bool               # True = 모든 사진 안전 / False = 유해물품 감지
    message: str                # 사용자에게 보여줄 안내 문구
    dangerous_file: Optional[str] = None   # 유해물품이 감지된 파일 이름 (안전 시 None)
    dangerous_label: Optional[str] = None  # AI가 감지한 유해물품 레이블 (안전 시 None)