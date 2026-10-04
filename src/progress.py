"""提取流程的进度报告接口。

TUI(src/tui.py)与 WebUI(src/webui.py)各自实现具体的展示方式;
核心脚本只依赖本接口,未传入时使用空实现(保持脚本可独立运行)。
"""


class ProgressReporter:
    """默认空实现:不做任何展示。"""

    def start(self, description, total=None):
        """开始一个阶段;total 为 None 表示总量不确定。"""

    def advance(self, message=""):
        """推进一格;message 为当前处理条目的描述。"""

    def finish(self, message=""):
        """阶段结束。"""


NULL_PROGRESS = ProgressReporter()
