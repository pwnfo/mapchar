import logging
import sys


class MapcharHandler(logging.Handler):
    """Writes warnings and errors to sys.stderr"""

    def __init__(self) -> None:
        super().__init__()
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)

            if record.levelno < logging.WARNING:
                stream = self.stdout
            else:
                stream = self.stderr

            stream.write(msg + "\n")
            stream.flush()

        except Exception:
            self.handleError(record)


class MapcharFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == logging.WARNING:
            return f"\033[1;33mWARN:\033[0m {record.getMessage()}"
        if record.levelno == logging.ERROR:
            return f"\033[1;31mERROR:\033[0m {record.getMessage()}"
        return record.getMessage()


def setup_logger() -> logging.Logger:
    log = logging.getLogger(__name__)

    handler = MapcharHandler()

    handler.setFormatter(MapcharFormatter())

    log.setLevel(logging.INFO)
    log.addHandler(handler)
    log.propagate = False

    return log


log = setup_logger()
