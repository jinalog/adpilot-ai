class ApplicationError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResourceNotFoundError(ApplicationError):
    status_code = 404
    code = "not_found"


class BusinessRuleError(ApplicationError):
    status_code = 422
    code = "business_rule_violation"


class ConflictError(ApplicationError):
    status_code = 409
    code = "conflict"
