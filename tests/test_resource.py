"""resource.py 的单元测试:线程池任务异常记录。"""
import logging
from concurrent.futures import ThreadPoolExecutor

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
