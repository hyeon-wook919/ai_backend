import io
import re
import logging
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from core.ai_models import get_vit_classifier
from schemas.image_schema import ImageAnalyzeResponse, ImageBatchSafetyResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# -------------------------------------------------------------------
# 유해물품 키워드 목록
# 단어 경계(\b) 정규식으로 매칭 → "stomach"에 "match"가 걸리는 오탐 방지
# -------------------------------------------------------------------
DANGEROUS_KEYWORDS = [
    "knife", "cleaver", "lighter", "weapon",
    "gun", "rifle", "hatchet", "scissor", "blade",
    "dagger", "sword", "revolver", "shotgun", "grenade"
]

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILES = 5
CONFIDENCE_THRESHOLD = 0.30


def is_dangerous_label(label: str) -> bool:
    """
    AI가 예측한 레이블에 유해물품 키워드가 포함되어 있는지 확인합니다.
    단어 경계(\b)를 사용해 정확한 단어 단위로만 매칭합니다.
    예) "stomach" → "match" 키워드에 걸리지 않음 ✅
    예) "cleaver"  → "cleaver" 키워드에 정확히 걸림 ✅
    """
    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf'\b{re.escape(keyword)}\b', label):
            return True
    return False


# -------------------------------------------------------------------
# [Step 1] 다중 이미지 일괄 안전 검사 API (Fail-Fast)
#
# 설계 의도:
# - 동일 물품의 다양한 각도 사진을 1~5장 올립니다.
# - 단 1장이라도 유해물품으로 판독되면 즉시 루프를 멈추고
#   {"is_safe": false}를 반환 → Step 2(글쓰기)로 진행 차단.
# - 모든 사진이 안전할 때만 {"is_safe": true}를 반환합니다.
#
# [Swagger UI 파일 선택창 정상화]
# Annotated[List[UploadFile], File()] 방식은 이 FastAPI 버전에서
# Swagger가 array<string>으로 잘못 렌더링합니다.
# files1~files5를 각각 Optional로 받아서 합치는 방식으로 해결합니다.
# 프론트엔드 실제 연동 시에는 files[] 키로 여러 장 한번에 보내면 됩니다.
# -------------------------------------------------------------------
@router.post("/check-safety", response_model=ImageBatchSafetyResponse)
async def check_images_safety(
    file1: UploadFile = File(...,  description="물품 사진 1장 (필수)"),
    file2: UploadFile = File(None, description="물품 사진 2장 (선택)"),
    file3: UploadFile = File(None, description="물품 사진 3장 (선택)"),
    file4: UploadFile = File(None, description="물품 사진 4장 (선택)"),
    file5: UploadFile = File(None, description="물품 사진 5장 (선택)"),
):
    """
    기부 물품 사진 1~5장을 받아 유해물품 여부를 일괄 검사합니다. (Fail-Fast)

    - 단 1장이라도 유해물품 감지 시 → 즉시 중단, is_safe=false 반환
    - 모든 사진 통과 시 → is_safe=true 반환 (Step 2 진행 가능)
    """

    # None이 아닌 파일만 리스트로 모읍니다
    files: List[UploadFile] = [
        f for f in [file1, file2, file3, file4, file5] if f is not None
    ]

    if not files:
        raise HTTPException(status_code=400, detail="사진을 최소 1장 이상 올려주세요.")

    # 모델 로딩 (최초 1회만 실제 로딩, 이후 캐시 반환)
    try:
        classifier = get_vit_classifier()
    except RuntimeError as e:
        logger.error(f"ViT 모델 호출 실패: {e}")
        raise HTTPException(status_code=503, detail=str(e))

    # ------------------------------------------------------------------
    # Fail-Fast 루프: 사진 한 장씩 검사
    # ------------------------------------------------------------------
    for idx, file in enumerate(files, start=1):

        # 파일 형식 검증
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename}): 지원하지 않는 형식입니다. JPG, PNG, WEBP만 가능합니다."
            )

        # 이미지 읽기
        try:
            image_bytes = await file.read()
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            logger.warning(f"이미지 파일 읽기 실패: {file.filename} - {e}")
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename}): 손상된 파일입니다. 다시 올려주세요."
            )

        # AI 예측
        try:
            ai_result = classifier(image)
        except Exception as e:
            logger.error(f"이미지 분류 중 예외 발생 ({file.filename}): {e}")
            raise HTTPException(status_code=500, detail="이미지 분석 중 오류가 발생했습니다.")

        top_prediction = ai_result[0]['label'].lower()
        confidence = ai_result[0]['score']
        confidence_percent = round(confidence * 100, 2)

        logger.info(f"[{idx}/{len(files)}] {file.filename} → {top_prediction} ({confidence_percent}%)")

        # 확신도가 너무 낮으면 해당 장만 통과 (판별 불가 = 위험하다고 단정 못 함)
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(f"낮은 확신도, 판별 불가 통과 처리: {file.filename}")
            continue

        # ★ 핵심: 유해물품 감지 즉시 루프 탈출 후 차단 응답 반환
        if is_dangerous_label(top_prediction):
            logger.warning(
                f"유해물품 감지! [{idx}번째] {file.filename} → {top_prediction} ({confidence_percent}%)"
            )
            return ImageBatchSafetyResponse(
                is_safe=False,
                message=(
                    f"⛔ {idx}번째 사진에서 기부 불가 물품이 감지되었습니다. "
                    f"해당 물품은 기부할 수 없습니다. (감지 항목: {top_prediction})"
                ),
                dangerous_file=file.filename,
                dangerous_label=top_prediction,
            )

    # 전체 통과
    logger.info(f"전체 {len(files)}장 안전 확인 완료.")
    return ImageBatchSafetyResponse(
        is_safe=True,
        message=f"✅ 전체 {len(files)}장 모두 안전한 물품으로 확인되었습니다. AI 글쓰기를 진행할 수 있습니다.",
        dangerous_file=None,
        dangerous_label=None,
    )


# -------------------------------------------------------------------
# [단일 판별] 이미지 1장 빠른 체크 API
# AI 글쓰기 없이 단순 유해물 여부만 빠르게 확인할 때 사용합니다.
# -------------------------------------------------------------------
@router.post("", response_model=ImageAnalyzeResponse)
async def predict_image(file: UploadFile = File(...)):
    """이미지 1장을 받아 유해물품 여부를 판별합니다."""

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. JPG, PNG, WEBP 이미지만 업로드 가능합니다."
        )

    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.warning(f"이미지 파일 읽기 실패: {file.filename} - {e}")
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없습니다.")

    try:
        classifier = get_vit_classifier()
        ai_result = classifier(image)
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