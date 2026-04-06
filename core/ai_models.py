from transformers import pipeline

# 1. 기존 비전 모델 (ViT - 이미지 판별용)
vit_classifier = pipeline("image-classification", model="google/vit-base-patch16-224")

# 2. 새롭게 추가할 자연어 처리 모델 (NLP - 의도 파악용)
# 한국어를 포함한 다국어를 지원하며, 문맥을 파악해 카테고리를 분류해 주는 모델입니다.
nlp_classifier = pipeline(
    "zero-shot-classification",
    model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
)