"""Auth schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class UserInfo(BaseModel):
    id: int
    username: str
    realName: str | None = None
    roleCodes: list[str] = []
    menuKeys: list[str] = []

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    token: str
    user: UserInfo


class RefreshResponse(BaseModel):
    token: str


class DemoAccount(BaseModel):
    username: str
    realName: str | None = None
    roleCodes: list[str] = []

    model_config = {"from_attributes": True}
