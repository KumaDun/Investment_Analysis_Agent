from datetime import datetime
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

class LoginResponse(BaseModel):
    token: str
    user_id: str
    expires_at: datetime

class SessionResponse(BaseModel):
    user_id: str
    expires_at: datetime

class OKResponse(BaseModel):
    ok: bool
