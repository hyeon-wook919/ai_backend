import io
import re
import logging
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool # 🔥 비동기 논블로킹 처리를 위한 모듈 추가
from PIL import Image

from core.ai_models import get_vit_classifier
from schemas.image_schema import ImageAnalyzeResponse, ImageBatchSafetyResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# -------------------------------------------------------------------
# 환경 설정
# -------------------------------------------------------------------
DANGEROUS_KEYWORDS = [
    "knife", "cleaver", "lighter", "weapon",
    "gun", "rifle", "hatchet", "scissor", "blade",
    "dagger", "sword", "revolver", "shotgun", "grenade"
]

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILES = 5
CONFIDENCE_THRESHOLD = 0.30
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 🔥 파일 용량 제한 (장당 5MB)


def is_dangerous_label(label: str) -> bool:
    """
    AI가 예측한 레이블에 유해물품 키워드가 포함되어 있는지 확인합니다.
    단어 경계(\b)를 사용해 정확한 단어 단위로만 매칭합니다.
    """
    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf'\b{re.escape(keyword)}\b', label):
            return True
    return False


# -------------------------------------------------------------------
# [Step 1] 다중 이미지 일괄 안전 검사 API (Fail-Fast)
# -------------------------------------------------------------------
@router.post("/check-safety", response_model=ImageBatchSafetyResponse)
async def check_images_safety(
    file1: UploadFile = File(...,  description="물품 사진 1장 (필수)"),
    file2: UploadFile = File(None, description="물품 사진 2장 (선택)"),
    file3: UploadFile = File(None, description="물품 사진 3장 (선택)"),
    file4: UploadFile = File(None, description="물품 사진 4장 (선택)"),
    file5: UploadFile = File(None, description="물품 사진 5장 (선택)"),
):
    files: List[UploadFile] = [
        f for f in [file1, file2, file3, file4, file5] if f is not None
    ]

    if not files:
        raise HTTPException(status_code=400, detail="사진을 최소 1장 이상 올려주세요.")

    try:
        classifier = get_vit_classifier()
    except RuntimeError as e:
        logger.error(f"ViT 모델 호출 실패: {e}")
        raise HTTPException(status_code=503, detail=str(e))

    for idx, file in enumerate(files, start=1):
        # 1. 파일 형식 검증
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename}): 지원하지 않는 형식입니다. JPG, PNG, WEBP만 가능합니다."
            )

        # 2. 파일 용량 및 빈 파일 검증 (🔥 서버 다운 방어)
        try:
            image_bytes = await file.read()
            if not image_bytes:
                raise HTTPException(
                    status_code=400, 
                    detail=f"{idx}번째 파일({file.filename}): 비어있는 파일입니다."
                )
            if len(image_bytes) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413, 
                    detail=f"{idx}번째 파일({file.filename}): 용량이 너무 큽니다. (최대 5MB)"
                )
            
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except HTTPException:
            raise  # 위에서 발생한 HTTP 에러는 그대로 던짐
        except Exception as e:
            logger.warning(f"이미지 파일 읽기 실패: {file.filename} - {e}")
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename}): 손상된 파일입니다. 다시 올려주세요."
            )

        # 3. AI 예측 (🔥 비동기 래핑으로 서버 블로킹 방지)
        try:
            # run_in_threadpool을 사용하여 메인 루프를 막지 않음
            ai_result = await run_in_threadpool(classifier, image)
        except Exception as e:
            logger.error(f"이미지 분류 중 예외 발생 ({file.filename}): {e}")
            raise HTTPException(status_code=500, detail="이미지 분석 중 오류가 발생했습니다.")

        top_prediction = ai_result[0]['label'].lower()
        confidence = ai_result[0]['score']
        confidence_percent = round(confidence * 100, 2)

        logger.info(f"[{idx}/{len(files)}] {file.filename} → {top_prediction} ({confidence_percent}%)")

        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(f"낮은 확신도, 판별 불가 통과 처리: {file.filename}")
            continue

        if is_dangerous_label(top_prediction):
            logger.warning(f"유해물품 감지! [{idx}번째] {file.filename} -> {top_prediction} ({confidence_percent}%)")
            return ImageBatchSafetyResponse(
            is_safe=False,
            message=f"⛔ {idx}번째 사진에서 기부 불가 물품(위험물, 흉기류 등)이 감지되어 등록할 수 없습니다.",
            dangerous_file=file.filename,
            dangerous_label=top_prediction, 
    )

    logger.info(f"전체 {len(files)}장 안전 확인 완료.")
    return ImageBatchSafetyResponse(
        is_safe=True,
        message=f"✅ 전체 {len(files)}장 모두 안전한 물품으로 확인되었습니다. AI 글쓰기를 진행할 수 있습니다.",
        dangerous_file=None,
        dangerous_label=None,
    )


# -------------------------------------------------------------------
# [단일 판별] 이미지 1장 빠른 체크 API
# -------------------------------------------------------------------
@router.post("", response_model=ImageAnalyzeResponse)
async def predict_image(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. JPG, PNG, WEBP 이미지만 업로드 가능합니다."
        )

    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="비어있는 파일입니다.")
        if len(image_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="용량이 너무 큽니다. (최대 5MB)")
            
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"이미지 파일 읽기 실패: {file.filename} - {e}")
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없습니다.")

    try:
        classifier = get_vit_classifier()
        # 🔥 비동기 래핑 적용
        ai_result = await run_in_threadpool(classifier, image)
    except RuntimeError as e:
        logger.error(f"ViT 모델 호출 실패: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"이미지 분류 중 예외 발생: {e}")
        raise HTTPException(status_code=500, detail="이미지 분석 중 오류가 발생했습니다.")

    top_prediction = ai_result[0]['label'].lower()
    confidence = ai_result[0]['score']
    confidence_percent = round(confidence * 100, 2)

    if confidence < CONFIDENCE_THRESHOLD:
        return ImageAnalyzeResponse(
            filename=file.filename,
            ai_guess=top_prediction,
            confidence=confidence_percent,
            is_dangerous=False,
            message="⚠️ 이미지를 명확히 판별하기 어렵습니다. 더 선명한 사진으로 다시 시도해 주세요."
        )

    dangerous = is_dangerous_label(top_prediction)
    message = (
        "⛔ [기부 불가] 유해물품이 감지되었습니다." if dangerous
        else "✅ [기부 가능] 안전한 물품으로 확인되었습니다."
    )

    logger.info(f"판별 완료: {file.filename} → {top_prediction} ({confidence_percent}%) / 유해: {dangerous}")

    return ImageAnalyzeResponse(
        filename=file.filename,
        ai_guess=top_prediction,
        confidence=confidence_percent,
        is_dangerous=dangerous,
        message=message
    )