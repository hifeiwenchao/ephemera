class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    code = "validation_error"


class UnauthorizedError(AppError):
    status = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status = 403
    code = "forbidden"


class NotFoundError(AppError):
    status = 404
    code = "not_found"


def positive_integer(value, name="id"):
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise ValidationError(f"{name} 必须是正整数")
    return value


def integer_text(value, name="id"):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise ValidationError(f"{name} 必须是正整数")
    return positive_integer(int(value), name)
