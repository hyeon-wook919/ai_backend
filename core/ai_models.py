# 후에 vit, kobert 등 무거운 모델 올려둘 곳
# core = ai 전용 폴더 , 서버 켤때 한번만 로딩 할 예정

from transformers import pipeline

print("🧠 전역 AI 모델 로딩 중... (서버 켤 때 최초 1회)")

# 1. 이미지 판별 모델 (ViT) 로딩
vit_classifier = pipeline("image-classification", model="google/vit-base-patch16-224")

print("✅ 모든 AI 모델 로딩 완료!")