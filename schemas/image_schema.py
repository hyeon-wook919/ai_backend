from pydantic import BaseModel

# AI가 사진을 보고 "이거 우산이야!" 라고 프론트에 알려줄 때 쓸 양식
class ImageAnalyzeResponse(BaseModel):
    ai_guess: str          # AI가 예상한 물건 이름 (예: umbrella)
    confidence: str        # AI의 확신도 (예: 98.5%)
    message: str           # 프론트엔드 화면에 띄워줄 안내 문구