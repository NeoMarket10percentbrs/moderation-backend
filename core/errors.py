from fastapi import HTTPException


STATUS_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    500: "INTERNAL_ERROR",
}


def error_code_for_status(status_code: int) -> str:
    return STATUS_CODE_MAP.get(status_code, "HTTP_ERROR")


def raise_api_error(status_code: int, code: str, message: str, details: dict | None = None) -> None:
    payload: dict = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    raise HTTPException(status_code=status_code, detail=payload)
