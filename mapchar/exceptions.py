class InvalidSyntaxError(Exception):
    """Raised on invalid mapchar file syntax."""

    def __init__(self, message: str) -> None:
        super().__init__("invalid file: " + message)
