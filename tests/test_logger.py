import logging

from mapchar.logger import MapcharRichHandler, log


class TestLogger:
    def test_log_is_logger(self):
        assert isinstance(log, logging.Logger)

    def test_log_level_is_info(self):
        assert log.level == logging.INFO

    def test_has_mapchar_handler(self):
        handlers = [h for h in log.handlers if isinstance(h, MapcharRichHandler)]
        assert len(handlers) >= 1

    def test_propagate_disabled(self):
        assert log.propagate is False
