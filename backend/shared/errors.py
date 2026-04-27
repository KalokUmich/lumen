"""Domain error taxonomy. Use these instead of bare HTTPExceptions where possible."""

from __future__ import annotations

from fastapi import HTTPException, status


class DomainError(HTTPException):
    code: str = "DOMAIN_ERROR"

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail={"code": self.code, "detail": detail})


class CubeQueryInvalid(DomainError):
    code = "CUBE_QUERY_INVALID"

    def __init__(self, detail: str):
        super().__init__(detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class CubeQueryFailed(DomainError):
    code = "CUBE_QUERY_FAILED"

    def __init__(self, detail: str):
        super().__init__(detail, status_code=status.HTTP_502_BAD_GATEWAY)


class WorkspaceNotFound(DomainError):
    code = "WORKSPACE_NOT_FOUND"

    def __init__(self, workspace_id: str):
        super().__init__(f"Workspace {workspace_id} not found", status_code=status.HTTP_404_NOT_FOUND)


class PermissionDenied(DomainError):
    code = "PERMISSION_DENIED"

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(detail, status_code=status.HTTP_403_FORBIDDEN)


class MaxAIHopsExceeded(DomainError):
    code = "AI_MAX_HOPS_EXCEEDED"

    def __init__(self):
        super().__init__(
            "AI exhausted reasoning steps without final answer",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
