class APIError(Exception):
    def __init__(self, code: int = 0, message: str = "") -> None:
        super().__init__(message)
        self.code = code


class ClientError(APIError):
    pass


class ServerError(APIError):
    pass
