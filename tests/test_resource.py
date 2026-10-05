"""resource.py 的单元测试:线程池任务异常记录、音乐本地库检查。"""
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

import resource


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _capture_logger():
    logger = logging.getLogger("test-resource")
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()
    handler = _CaptureHandler()
    logger.addHandler(handler)
    logger.propagate = False
    return logger, handler.records


def _boom():
    raise RuntimeError("模拟失败")


def test_submit_logs_task_error():
    logger, records = _capture_logger()
    with ThreadPoolExecutor(1) as pool:
        future = resource._submit(pool, logger, _boom)
    assert future.exception() is not None
    assert any("后台任务失败" in record.getMessage() for record in records)


def test_prepare_music_libs_ok(monkeypatch):
    import native_libs
    monkeypatch.setattr(native_libs, "ensure_patched", lambda: None)
    monkeypatch.setattr(native_libs, "check_available", lambda: None)
    assert resource._prepare_music_libs() is None


def test_prepare_music_libs_reports_missing(monkeypatch):
    import native_libs

    def boom():
        raise RuntimeError("缺少音乐提取所需的本地库 vorbis")

    monkeypatch.setattr(native_libs, "ensure_patched", lambda: None)
    monkeypatch.setattr(native_libs, "check_available", boom)
    with pytest.raises(SystemExit) as exc:
        resource._prepare_music_libs()
    assert "vorbis" in str(exc.value)
    assert "types.music" in str(exc.value)
