"""平台的錯誤。每個錯誤帶一個穩定的 code,API 層把它轉成 HTTP 回應。

bot 應該依 code 判斷,message 只給人看,內容可能調整。
"""


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message="", code=None, status=None):
        super().__init__(message)
        self.message = message or self.code
        if code:
            self.code = code
        if status:
            self.status = status

    def to_dict(self):
        return {"error": {"code": self.code, "message": self.message}}


class NotFound(ApiError):
    status, code = 404, "not_found"


class Conflict(ApiError):
    status, code = 409, "conflict"


class Invalid(ApiError):
    status, code = 422, "invalid_request"


class Unauthorized(ApiError):
    status, code = 401, "invalid_token"


class Forbidden(ApiError):
    status, code = 403, "forbidden"


class TooManyRequests(ApiError):
    status, code = 429, "rate_limited"
