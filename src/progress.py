"""提取流程的进度报告与取消接口。

TUI(src/tui.py)与 WebUI(src/webui.py)各自实现具体的展示方式;
核心脚本只依赖本接口,未传入时使用空实现(保持脚本可独立运行)。
"""


class TaskCancelled(Exception):
    """任务被用户取消。"""


class ProgressReporter:
    """默认实现:不展示进度,也不响应取消。"""

    cancelled = False

    def start(self, description, total=None):
        """开始一个阶段;total 为 None 表示总量不确定。"""

    def advance(self, message=""):
        """推进一格;message 为当前处理条目的描述。"""

    def finish(self, message=""):
        """阶段结束。"""

    def overall_start(self, description, total=None):
        """批量任务的总进度(可选):description 为总任务名,如"批量处理 input/"。"""

    def overall_advance(self, message=""):
        """推进总进度一格;message 为当前处理对象的描述。"""

    def overall_finish(self, message=""):
        """总进度结束。"""

    def check_cancelled(self):
        """在可取消的循环中调用;任务被取消时抛出 TaskCancelled。"""
        if self.cancelled:
            raise TaskCancelled()


NULL_PROGRESS = ProgressReporter()
