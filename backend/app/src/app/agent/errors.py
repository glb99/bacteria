class BacteriaException(Exception):
    """Base class for exceptions related to bacteria."""

    def __init__(self, message: str):
        super().__init__(message)


class UnknownSessionError(BacteriaException):
    """Raised when a session is requested that does not exist."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Unknown session: {session_id}")


class CredentialsError(BacteriaException):
    """Raised when there is an error with the credentials."""

    def __init__(self, message: str):
        super().__init__(f"Credentials error: {message}")


class ModelError(BacteriaException):
    """Raised when there is an error with the model."""

    def __init__(self, message: str):
        super().__init__(f"Model error: {message}")


class ServingError(BacteriaException):
    """Raised when there is an error serving the model."""

    def __init__(self, message: str):
        super().__init__(f"Serving error: {message}")


class ContractError(BacteriaException):
    """Raised when there is a contract violation with the model."""

    def __init__(self, message: str):
        super().__init__(f"Contract error: {message}")


class AssetError(BacteriaException):
    """Raised when there is an error related to assets."""

    def __init__(self, message: str):
        super().__init__(f"Asset error: {message}")


class UnknownToolError(BacteriaException):
    """Raised when a tool is requested that does not exist."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Unknown tool: {tool_name}")


class ToolExecutionError(BacteriaException):
    """Raised when there is an error executing a tool."""

    def __init__(self, message: str, reason: str):
        self.reason = reason
        super().__init__(f"Tool execution error: {message} (reason: {reason})")
