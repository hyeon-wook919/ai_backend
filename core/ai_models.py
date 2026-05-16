import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 전략: 지연 로딩(Lazy Loading)
#
# 모듈이 import될 때 바로 모델을 올리지 않고,
# 실제로 API가 처음 호출되는 순간에 모델을 메모리에 올립니다.
#
# 이유:
# 1. 서버 시작 속도가 빨라집니다. (모델 2개 동시 로딩 = 수십 초 대기 방지)
# 2. 모델 로딩 실패 시 서버 전체가 죽지 않고, 해당 엔드포인트만 에러 반환합니다.
# 3. 실제로 사용하지 않는 모델은 메모리를 낭비하지 않습니다.
# -------------------------------------------------------------------

_vit_classifier = None
_nlp_classifier = None


def get_vit_classifier():
    """
    이미지 분류 모델 (ViT) 반환 함수.
    최초 호출 시 모델을 로드하고, 이후에는 캐시된 인스턴스를 반환합니다.
    - 모델: google/vit-base-patch16-224
    - 역할: 이미지를 보고 물체 종류를 분류 (유해물품 판별에 사용)
    """
    global _vit_classifier
    if _vit_classifier is None:
        try:
            logger.info("ViT 이미지 분류 모델 로딩 중... (최초 1회만 실행됩니다)")
            _vit_classifier = pipeline(
                "image-classification",
                model="google/vit-base-patch16-224"
            )
            logger.info("ViT 모델 로딩 완료.")
        except Exception as e:
            logger.error(f"ViT 모델 로딩 실패: {e}")
            # 호출한 라우터에서 HTTPException으로 변환해서 처리합니다.
            raise RuntimeError(f"이미지 분류 모델을 불러올 수 없습니다: {e}")
    return _vit_classifier


def get_nlp_classifier():
    """
    자연어 처리 모델 (Zero-shot classification) 반환 함수.
    최초 호출 시 모델을 로드하고, 이후에는 캐시된 인스턴스를 반환합니다.
    - 모델: MoritzLaurer/mDeBERTa-v3-base-mnli-xnli
    - 역할: 사용자의 말을 듣고 어떤 정책 카테고리가 필요한지 분류 (챗봇에 사용)
    - 한국어 포함 다국어 지원
    """
    global _nlp_classifier
    if _nlp_classifier is None:
        try:
            logger.info("NLP 텍스트 분류 모델 로딩 중... (최초 1회만 실행됩니다)")
            _nlp_classifier = pipeline(
                "zero-shot-classification",
                model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
            )
            logger.info("NLP 모델 로딩 완료.")
        except Exception as e:
            logger.error(f"NLP 모델 로딩 실패: {e}")
            raise RuntimeError(f"텍스트 분류 모델을 불러올 수 없습니다: {e}")
    return _nlp_classifier