from app.schemas.pydantic.BaseSchema import BaseResponse, ResponseStatus
from app.services.StatusService import StatusService
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/v1/status", tags=["status"])


# 狀態檢查相關功能
@router.get(
    "/checker",
    response_model=BaseResponse[None],
    summary="狀態檢查",
    description="此端點用於檢查伺服器的相關狀態。",
)
async def checker(statusService: StatusService = Depends()):
    try:
        return BaseResponse(
            status=ResponseStatus.SUCCESS,
            message="",
            data=await statusService.checker(),
        )
    except Exception as e:
        return BaseResponse(
            status=ResponseStatus.ERROR,
            message=str(e),
            data=None,
        )
