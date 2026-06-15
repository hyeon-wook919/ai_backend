import os
import io
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

from schemas.post_schema import PostGenerationResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# 1. 환경변수 및 기본 세팅
# -------------------------------------------------------------------
load_dotenv(override=True)  # 🔥 괄호 안에 override=True 를 꼭 넣어주세요!
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 서버가 켜질 때 새 키를 잘 물고 왔는지 터미널에서 눈으로 확인하기 위한 코드
print(f"👀 현재 적용된 API 키 앞자리: {GEMINI_API_KEY[:10]}...") 

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 파일 용량 제한 (5MB)


# -------------------------------------------------------------------
# 2. JSON 정제 함수
# -------------------------------------------------------------------
def clean_and_parse_json(text: str) -> dict:
    """Gemini가 뱉어내는 JSON을 안전하게 딕셔너리로 파싱합니다."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    data = json.loads(text)
    if isinstance(data, list):
        if len(data) > 0:
            return data[0]
        else:
            raise ValueError("비어있는 JSON 배열이 반환되었습니다.")
    return data


# -------------------------------------------------------------------
# -------------------------------------------------------------------
# 3. 프롬프트 생성 함수 (🔥 화자 변경 및 자연스러운 나눔 멘트 추가)
# -------------------------------------------------------------------
def build_prompt(item_name: Optional[str]) -> str:
    if item_name and item_name.strip():
        hint_sentence = f"사용자가 이 물품을 '{item_name.strip()}'이라고 알려줬어."
    else:
        hint_sentence = "사용자가 물품 이름을 따로 입력하지 않았어."

    return f"""
너는 취약계층 기부 플랫폼에서 '기부자(Donor)'의 입장이 되어 나눔글을 대신 작성해주는 훌륭한 대필 작가야.

[거절 규칙 - 아래 중 하나라도 해당하면 즉시 is_safe나 is_same_item을 false로 처리해]
1. 유해물품: 칼, 무기, 가위, 폭발물 등 기부하기 부적절하고 위험한 물건이 1장이라도 섞여 있으면 is_safe: false.
2. 다중물품: 1~5장의 사진이 '동일한 하나의 물품(또는 한 세트)'이 아니라면 is_same_item: false.
3. {hint_sentence}

[🔥 기부글 본문(ai_generated_post) 작성 핵심 규칙]
1. 화자 설정: 글을 쓰는 사람은 '물건을 무료로 나누어주는 기부자 본인'이야. 절대 스스로에게 "따뜻한 마음에 감사드립니다" 같은 말을 쓰지 마.
2. 자연스러운 나눔 이유: 사진을 보고 상황에 맞는 자연스러운 나눔 이유를 1개 지어내서 문장에 섞어줘.
   (예시: "선물 받았는데 저랑은 안 쓰는 브랜드라 나눔해요~", "사놓고 보관만 하다가 제게는 안 맞는 타입이라 연락해요~", "옷장 정리하다가 상태 좋은 물건 발견해서 나눔합니다!")
3. 말투: 당근마켓 무료 나눔처럼 친근하고 부드러운 말투(~해요, ~합니다)를 써줘.
4. 맺음말: "필요하신 분이 유용하게 쓰셨으면 좋겠어요!", "편하게 연락주세요~" 같이 따뜻하게 마무리해줘.
5. 분량: 너무 길지 않게 3~4문장 이내로 작성해.

[출력 형식 - 반드시 아래 JSON 구조만 반환]
{{
  "is_safe": true,
  "is_same_item": true,
  "rejection_reason": "만약 false라면 사용자에게 보여줄 친절한 거절 사유 (true면 null)",
  "category": "다음 11개 중 사진과 가장 잘 맞는 1개만 정확히 선택: [의류/잡화, 디지털/소형가전, 가구/인테리어, 유아동/장난감, 도서/음반, 생활/주방용품, 가공식품, 위생/생필품, 문구/학용품, 건강/의료기구, 기타]",
  "suggested_title": "매력적인 제목 (20자 이내)", "제품이름만 들어가게 하고 나눔해요 같은 서술어는 들어가지 않게 할 것",
  "extracted_features": ["사진에서 파악한 특징1", "특징2", "특징3"],
  "ai_generated_post": "위 [작성 핵심 규칙]을 완벽하게 적용한 나눔글 본문",
  "confidence": 95.5
}}
"""


# -------------------------------------------------------------------
# 4. AI 기부글 생성 API
# -------------------------------------------------------------------
@router.post("/generate-post", response_model=PostGenerationResponse)
async def generate_market_post(
    file1: UploadFile = File(...,  description="물품 사진 1장 (필수)"),
    file2: UploadFile = File(None, description="물품 사진 2장 (선택)"),
    file3: UploadFile = File(None, description="물품 사진 3장 (선택)"),
    file4: UploadFile = File(None, description="물품 사진 4장 (선택)"),
    file5: UploadFile = File(None, description="물품 사진 5장 (선택)"),
    item_name: Optional[str] = Form(default=None, description="물품 이름 힌트 (선택 입력)"),
):
    files: List[UploadFile] = [
        f for f in [file1, file2, file3, file4, file5] if f is not None
    ]

    if not files:
        raise HTTPException(status_code=400, detail="사진을 최소 1장 이상 올려주세요.")

    image_parts = []
    for idx, file in enumerate(files, start=1):
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"{idx}번째 파일({file.filename}): JPG, PNG, WEBP만 가능합니다.")
        
        try:
            file_bytes = await file.read()
            if not file_bytes:
                raise HTTPException(status_code=400, detail=f"{idx}번째 파일({file.filename}): 비어있는 파일입니다.")
            if len(file_bytes) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(status_code=413, detail=f"{idx}번째 파일({file.filename}): 용량이 너무 큽니다. (최대 5MB)")
            
            # 🔥 이미지 압축 및 리사이징 로직 추가
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            
            # 해상도를 최대 1024x1024로 줄임 (비율 유지)
            img.thumbnail((300, 300)) 
            
            # 화질을 85%로 낮춰서 메모리에 저장
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=50)
            compressed_bytes = output.getvalue()

            image_parts.append(
                types.Part.from_bytes(data=compressed_bytes, mime_type="image/jpeg")
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"파일 처리 실패: {file.filename} - {e}")
            raise HTTPException(status_code=400, detail=f"{idx}번째 파일({file.filename})을 읽을 수 없습니다.")

    logger.info(f"Gemini 호출 시작: {len(image_parts)}장, item_name='{item_name}'")

    try:
        prompt = build_prompt(item_name)
        contents = image_parts + [types.Part.from_text(text=prompt)]

        response = await run_in_threadpool(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        result = clean_and_parse_json(response.text)

        # 🔥 비즈니스 로직 1: 유해물품 차단
        if not result.get("is_safe", True):
            reason = result.get("rejection_reason", "유해물품이 포함되어 있습니다.")
            logger.warning(f"기부글 작성 차단 (유해물품): {reason}")
            raise HTTPException(status_code=400, detail=f"⛔ 작성 불가: {reason}")

        # 🔥 비즈니스 로직 2: 다중물품 차단
        if not result.get("is_same_item", True):
            reason = result.get("rejection_reason", "여러 종류의 물품이 섞여 있습니다.")
            logger.warning(f"기부글 작성 차단 (다중물품): {reason}")
            raise HTTPException(status_code=400, detail=f"⛔ 작성 불가: {reason}")

        logger.info(f"Gemini 응답 성공 (안전 검증 통과): category='{result.get('category')}'")
        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Gemini API 호출 실패: {error_msg}")
        
        # 🔥 구글 서버 일시적 과부하 (503) 방어
        if "503" in error_msg or "UNAVAILABLE" in error_msg:
            raise HTTPException(
                status_code=503, 
                detail="현재 AI 서버에 접속자가 몰려 처리가 지연되고 있습니다. 1~2분 뒤에 다시 시도해 주세요."
            )
        # 🔥 구글 무료 API 한도 초과 (429) 방어
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            raise HTTPException(
                status_code=429, 
                detail="현재 접속자가 많아 AI 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요."
            )
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"AI 글쓰기 중 오류가 발생했습니다: {error_msg}"
            )