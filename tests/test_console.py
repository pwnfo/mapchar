from threading import Event
from unittest.mock import patch

from mapchar.console import get_progress


class DummyTask:
    def __init__(self, time_remaining=None, speed=None):
        self.time_remaining = time_remaining
        self.speed = speed


class DummyValue:
    def __init__(self, value=0):
        self.value = value


class TestGetProgress:
    @patch("mapchar.console.sleep")
    def test_get_progress_completes(self, mock_sleep):
        e = Event()
        r = DummyValue(100)
        get_progress(e, r, total=100)
        assert mock_sleep.call_count == 0

    @patch("mapchar.console.sleep")
    def test_get_progress_updates(self, mock_sleep):
        e = Event()
        r = DummyValue(0)

        def update_value(*args, **kwargs):
            r.value += 50

        mock_sleep.side_effect = update_value

        get_progress(e, r, total=100)
        assert mock_sleep.call_count > 0

    @patch("mapchar.console.sleep")
    def test_get_progress_keyboard_interrupt(self, mock_sleep):
        e = Event()
        r = DummyValue(50)
        mock_sleep.side_effect = KeyboardInterrupt
        get_progress(e, r, total=100)
        assert e.is_set()
