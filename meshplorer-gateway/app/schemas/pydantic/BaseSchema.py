import json
from enum import Enum
from pydantic import BaseModel, model_validator, Field
from typing import Any, TypeVar, Generic, Optional

T = TypeVar("T")


# 定義 Response 狀態碼相關的 Enum
class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


# 允許 JSON 字串解析的相關 Model
class JsonStringModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def validate_to_json(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("無效的 JSON 字串格式")
        return value


# 泛型 API 回應相關的 schema
class BaseResponse(BaseModel, Generic[T]):
    status: ResponseStatus = Field(
        default=ResponseStatus.SUCCESS, description="Response status"
    )
    message: str = Field(default="", description="Response message")
    data: Optional[T] = Field(default=None, description="Response data")
