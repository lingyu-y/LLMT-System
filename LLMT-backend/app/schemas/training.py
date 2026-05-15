"""Training schemas."""

from pydantic import BaseModel, Field


class PrivacyConfigRequest(BaseModel):
    epsilon: float = Field(..., ge=0.01, le=100.0, description="隐私预算 ε")
    delta: float = Field(default=1e-5, ge=0, le=1.0, description="隐私保证 δ")
    noise_multiplier: float = Field(default=1.0, ge=0, description="噪声乘数")
    max_grad_norm: float = Field(default=1.0, gt=0, description="梯度裁剪阈值")
    target_epsilon: float | None = Field(default=None, ge=0.01, le=100.0)
    target_delta: float | None = Field(default=None, ge=0, le=1.0)
    algorithm: str = Field(default="dp-sgd", description="差分隐私算法")
