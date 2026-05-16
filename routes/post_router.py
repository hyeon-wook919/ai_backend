import os
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.post_schema import PostGenerationResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# -------------------------------------------------------------------
# 1. 환경변수 및 Gemini 클라이언트 초기 세팅
# -------------------------------------------------------------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


# -------------------------------------------------------------------
# 2. 프롬프트 생성 함수
# -------------------------------------------------------------------
def build_prompt(item_name: Optional[str]) -> str:
    if item_name and item_name.strip():
        hint_sentence = (
            f"사용자가 이 물품의 이름을 '{item_name.strip()}'이라고 알려줬어. "
            f"이 힌트를 최대한 반영해서 제목과 본문을 작성해줘."
        )
    else:
        hint_sentence = (
            "사용자가 물품 이름을 따로 입력하지 않았어. "
            "사진만 보고 물품의 종류와 특징을 스스로 파악해서 작성해줘."
        )

    return f"""
너는 취약계층 기부 플랫폼의 따뜻하고 친절한 기부 물품 큐레이터야.
내가 올린 사진들을 꼼꼼히 분석해서 기부글을 작성해줘.

[중요 규칙 - 반드시 지켜줘]
1. 사진이 여러 장이더라도 이건 '동일한 물품 하나'를 다양한 각도에서 찍은 거야.
   절대로 사진 장수만큼 여러 물품이 있다고 착각하면 안 돼.
   사진들이 다른 물품이면 is_same_item: false로 반환하라
   모든 사진을 종합해서 물품 하나에 대한 글을 써줘.
2. {hint_sentence}
3. 인사말, 설명, 마크다운 코드블록(```json) 등 JSON 외의 텍스트는
   단 한 글자도 출력하면 안 돼. 오직 JSON만 반환해.
4. confidence는 사진과 분석 결과에 대한 너의 확신도를 0.0~100.0 사이 숫자로 줘.

[출력 형식 - 아래 JSON 구조 그대로 반환]
{{
  "is_same_item": true,
  "category": "다음 10개 중 사진과 가장 잘 맞는 1개만 정확히 선택: [의류/잡화, 디지털/소형가전, 유아동/장난감, 도서/음반, 생활/주방용품, 가공식품, 위생/생필품, 문구/학용품, 건강/의료기구, 기타]",
  "suggested_title": "물건의 특징이 잘 드러나는 따뜻하고 매력적인 제목 (20자 이내)",
  "extracted_features": ["사진에서 파악한 특징1", "특징2", "특징3"],
  "ai_generated_post": "당근마켓 스타일의 친절하고 상세한 기부글 본문. 이모지를 자연스럽게 포함하고, 어떤 분이 필요할지 안내하며, 받아가는 분이 편하게 느낄 수 있게 따뜻한 말투로 써줘.",
  "confidence": 95.5
}}
"""


# -------------------------------------------------------------------
# 3. AI 기부글 생성 API
#
# [Swagger UI 파일 선택창 정상화]
# Annotated[List[UploadFile]] 방식이 array<string>으로 잘못 렌더링되는
# FastAPI Swagger 버그를 우회하기 위해 file1~file5를 각각 받습니다.
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
    """
    Step 1(유해물 검사)을 통과한 사진 1~5장을 받아
    Gemini AI로 당근마켓 스타일의 기부글을 자동 생성합니다.
    """

    # None이 아닌 파일만 리스트로 모읍니다
    files: List[UploadFile] = [
        f for f in [file1, file2, file3, file4, file5] if f is not None
    ]

    if not files:
        raise HTTPException(status_code=400, detail="사진을 최소 1장 이상 올려주세요.")

    # ------------------------------------------------------------------
    # 각 이미지 파일 읽기 (for 루프로 개별 순회)
    # ------------------------------------------------------------------
    image_parts = []
    for idx, file in enumerate(files, start=1):
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename}): JPG, PNG, WEBP만 가능합니다."
            )
        try:
            file_bytes = await file.read()
            image_parts.append(
                types.Part.from_bytes(data=file_bytes, mime_type=file.content_type)
            )
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {file.filename} - {e}")
            raise HTTPException(
                status_code=400,
                detail=f"{idx}번째 파일({file.filename})을 읽을 수 없습니다."
            )

    logger.info(f"Gemini 호출 시작: {len(image_parts)}장, item_name='{item_name}'")

    # ------------------------------------------------------------------
    # Gemini API 호출
    # ------------------------------------------------------------------
    try:
        prompt = build_prompt(item_name)
        contents = image_parts + [types.Part.from_text(text=prompt)]

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        result = json.loads(response.text)
        logger.info(f"Gemini 응답 성공: category='{result.get('category')}'")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Gemini 응답 JSON 파싱 실패: {e}\n원문: {response.text}")
        raise HTTPException(
            status_code=500,
            detail="AI 응답을 처리하는 중 오류가 발생했습니다. 다시 시도해 주세요."
        )
    except Exception as e:
        logger.error(f"Gemini API 호출 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI 글쓰기 중 오류가 발생했습니다: {str(e)}"
        )