import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50, examples=["learner1"])
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    native_language: str = Field(default="zh", max_length=10)
    learning_language: str = Field(default="en", max_length=10)
    level: str = Field(default="beginner", max_length=20)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    native_language: str
    learning_language: str
    level: str
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse