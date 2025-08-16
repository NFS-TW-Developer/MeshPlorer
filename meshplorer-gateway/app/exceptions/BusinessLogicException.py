class BusinessLogicException(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self):
        if self.code:
            return f"[錯誤代碼 {self.code}]: {self.message}"
        return self.message
