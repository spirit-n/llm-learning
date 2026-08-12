class HarnessError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable


class TransientToolError(HarnessError):
    def __init__(self, message: str = "工具暂时不可用"):
        super().__init__("TOOL_TRANSIENT", message, retryable=True)


class ToolGuardError(HarnessError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, retryable=False)

