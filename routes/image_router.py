# 사진 찰캌 후 -> 우산 판별 및 유해물품 검사

from fastapi import APIRouter, File, UploadFile
import io 
from PIL import Image

# core 폴더에 미리 올려둔 ViT 모델을 가져온다
from core.ai_models import vit_classifier 
from schemas.image_schema import ImageAnalyzeResponse

router = APIRouter()

# 유해물품 사전
DANGEROUS_KEYWORDS = [
    "knife", "cleaver", "lighter", "match", "weapon", 
    "gun", "rifle", "hatchet", "scissor", "blade"
]

@router.post("")
async def predict_image(file: UploadFile = File(...)):
    #  이미지 변환
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    #  가져온 모델로 판별
    ai_result = vit_classifier(image)
    
    # 결과 정리
    top_prediction = ai_result[0]['label'].lower()
    confidence = ai_result[0]['score']
    
    is_dangerous = any(keyword in top_prediction for keyword in DANGEROUS_KEYWORDS)
    
    if is_dangerous:
        final_message = "⚠️ [경고] 기부 불가 물품(유해물품)이 감지되었습니다!"
    else:
        final_message = "✅ 기부 가능한 안전한 물품입니다."

    return {
        "filename": file.filename,
        "ai_guess": top_prediction,
        "confidence": round(confidence * 100, 2),
        "is_dangerous": is_dangerous,
        "message": final_message
    }