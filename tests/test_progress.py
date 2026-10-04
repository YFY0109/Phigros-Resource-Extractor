"""progress.py 的单元测试:取消检查。"""
import pytest

from progress import NULL_PROGRESS, ProgressReporter, TaskCancelled


def test_null_progress_never_cancels():
    assert NULL_PROGRESS.cancelled is False
    NULL_PROGRESS.check_cancelled()
    assert NULL_PROGRESS.cancelled is False


def test_cancelled_raises():
    reporter = ProgressReporter()
    reporter.cancelled = True
    with pytest.raises(TaskCancelled):
        reporter.check_cancelled()
