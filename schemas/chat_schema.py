from pydantic import BaseModel

# 1. 프론트엔드 -> 백엔드로 보낼 때 쓸 양식 (요청)
class ChatRequest(BaseModel):
    user_message: str

# (나중에는 백엔드 -> 프론트엔드로 줄 '응답 양식'도 여기에 추가하게 됩니다!)