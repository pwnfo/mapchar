class ExprError(Exception):
    def __init__(self, message: str, error_pos: tuple[str, int] | None = None) -> None:
        if error_pos is not None:
            pattern, char_pos = error_pos
            window = 24

            if pattern:
                char_pos = max(0, min(char_pos - 1, len(pattern) - 1))

                start = max(0, char_pos - window // 2)
                end = min(len(pattern), start + window)
                start = max(0, end - window)

                prefix = "... " if start > 0 else ""
                snippet = pattern[start:end]
                suffix = " ..." if end < len(pattern) else ""

                caret_pos = len(prefix) + (char_pos - start)

                message += f"\n\n{prefix}{snippet}{suffix}\n{' ' * caret_pos}^^^"
            else:
                message += "\n\n^^^"

        super().__init__("[Pattern Error] " + message)
