"""交互式 CLI/TUI:引导用户提供 APK 并执行提取,以 rich 进度条展示实时状态。

用法:
    python src/tui.py                                        # 交互菜单
    python src/tui.py --apk <路径> --all                     # 直跑:完整流程
    python src/tui.py --apk <路径> --info --resource         # 直跑:指定步骤
    python src/tui.py --apk <路径> --video                   # 直跑:仅提取解锁动画视频
    python src/tui.py --phira --version 4.0.1                # 仅打包(无需 APK)

APK 必须由用户显式提供(文件名需包含版本号,如 Phigros_4.0.1.apk,或用 --version 指定)。
"""
import argparse
import logging
import os

from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn,
)

import batch
import gameInformation
import phira
import resource as resource_module
import videos
from common import detect_version, list_versions, load_config, save_config
from progress import ProgressReporter

console = Console()

STEPS = ("info", "resource", "video", "phira")


class RichProgress(ProgressReporter):
    """把进度事件映射到 rich:批量总进度一行、当前阶段一行(阶段间复用同一行)。

    阶段/总任务完成时移除对应行,避免残留进度条与旋转动画。
    """

    def __init__(self, progress):
        self._progress = progress
        self._overall_task = None
        self._stage_task = None
        self._stage = ""

    def overall_start(self, description, total=None):
        self._overall_task = self._progress.add_task(escape(description), total=total)

    def overall_advance(self, message=""):
        if self._overall_task is not None:
            self._progress.update(self._overall_task, advance=1, description=escape(message))

    def overall_finish(self, message=""):
        if self._overall_task is not None:
            self._progress.remove_task(self._overall_task)
            self._overall_task = None

    def start(self, description, total=None):
        self._stage = description
        if self._stage_task is None:
            self._stage_task = self._progress.add_task(escape(description), total=total)
        else:
            self._progress.update(self._stage_task, description=escape(description), total=total, completed=0)

    def advance(self, message=""):
        if self._stage_task is None:
            return
        text = escape(self._stage)
        if message:
            label = message if len(message) <= 64 else message[:61] + "..."
            text = "%s  [dim]%s[/dim]" % (text, escape(label))
        self._progress.update(self._stage_task, advance=1, description=text)

    def finish(self, message=""):
        if self._stage_task is not None:
            self._progress.remove_task(self._stage_task)
            self._stage_task = None


def make_rich_logger():
    """创建与 rich 进度条兼容的日志器。"""
    logger = logging.getLogger("tui")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(RichHandler(console=console, show_path=False, rich_tracebacks=True))
    logger.propagate = False
    return logger


def resolve_version(apk_path, override=None):
    """识别版本号;文件名无法识别时交互询问。"""
    if override:
        return override
    try:
        return detect_version(apk_path)
    except SystemExit:
        return Prompt.ask("无法自动识别版本号,请手动输入(如 4.0.1)")


def ask_apk_path():
    """询问 APK 路径并校验文件存在。"""
    while True:
        path = Prompt.ask("请输入 Phigros APK 完整路径").strip().strip('"')
        if not path:
            console.print("[yellow]路径不能为空[/yellow]")
            continue
        if not os.path.isfile(path):
            console.print("[yellow]文件不存在:%s[/yellow]" % escape(path))
            continue
        return os.path.abspath(path)


def execute(steps, apk_path, version, config, logger):
    """按顺序执行指定步骤,全程展示进度条;异常不退出菜单。"""
    console.rule("[bold]开始执行[/bold]")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            reporter = RichProgress(progress)
            if "info" in steps:
                gameInformation.run(apk_path, version, logger, reporter)
            if "resource" in steps:
                resource_module.run(apk_path, version, config, logger, reporter)
            if "video" in steps:
                videos.run(apk_path, version, logger, reporter)
            if "phira" in steps:
                phira.run(version, logger, reporter)
        console.print("[bold green]执行完成[/bold green]")
    except KeyboardInterrupt:
        console.print("[bold yellow]已取消[/bold yellow]")
    except SystemExit as e:
        console.print("[bold red]执行中断:%s[/bold red]" % escape(str(e)))
    except Exception:
        console.print("[bold red]执行出错:[/bold red]")
        console.print_exception()


def execute_batch(config, logger):
    """批量处理 input/ 目录(完整流程);异常不退出菜单。"""
    console.rule("[bold]批量处理 input/[/bold]")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            count = batch.process_all(("info", "resource", "video", "phira"), config, logger, RichProgress(progress))
        console.print("[bold green]批量处理完成,共 %d 个 APK[/bold green]" % count)
    except KeyboardInterrupt:
        console.print("[bold yellow]已取消[/bold yellow]")
    except SystemExit as e:
        console.print("[bold red]批量处理中断:%s[/bold red]" % escape(str(e)))
    except Exception:
        console.print("[bold red]批量处理出错:[/bold red]")
        console.print_exception()


def edit_config(config):
    """交互修改 config.json 的常用项。"""
    console.rule("修改配置")
    for name in list(config["types"]):
        config["types"][name] = Confirm.ask("提取 %s" % name, default=config["types"][name])
    for key in ("main_story", "other_song", "side_story"):
        config["update"][key] = IntPrompt.ask("增量 %s(0 表示全量)" % key, default=config["update"][key])
    config["dedupe"]["enabled"] = Confirm.ask("启用跨版本去重(硬链接)", default=config["dedupe"]["enabled"])
    webui = config.setdefault("webui", {})
    webui["host"] = Prompt.ask("WebUI 监听地址", default=webui.get("host", "127.0.0.1"))
    webui["port"] = IntPrompt.ask("WebUI 监听端口", default=int(webui.get("port", 8000)))
    save_config(config)
    console.print("[green]配置已保存到 config.json[/green]")


def show_header(config, apk_path):
    enabled = ", ".join(name for name, on in config["types"].items() if on) or "无"
    lines = [
        "APK: %s" % (apk_path or "(未设置)"),
        "启用类型: %s" % enabled,
    ]
    console.print(Panel("\n".join(lines), title="Phigros 资源提取器", subtitle="TUI"))


def interactive(args):
    config = load_config()
    logger = make_rich_logger()
    apk_path = args.apk
    version = args.version

    while True:
        console.print()
        show_header(config, apk_path)
        console.print(
            "[1] 完整流程(信息 → 资源 → 视频 → Phira 打包)\n"
            "[2] 仅提取游戏信息\n"
            "[3] 仅提取资源\n"
            "[4] 仅提取解锁动画视频\n"
            "[5] 仅打包 Phira 谱面\n"
            "[6] 修改配置\n"
            "[7] 批量处理 input/ 文件夹\n"
            "[0] 退出"
        )
        choice = Prompt.ask("请选择", choices=["0", "1", "2", "3", "4", "5", "6", "7"], default="1")
        if choice == "0":
            break
        if choice == "6":
            edit_config(config)
            continue
        if choice == "7":
            execute_batch(config, logger)
            continue

        steps = {
            "1": ("info", "resource", "video", "phira"),
            "2": ("info",),
            "3": ("resource",),
            "4": ("video",),
            "5": ("phira",),
        }[choice]
        if steps & {"info", "resource", "video"}:
            if not apk_path:
                apk_path = ask_apk_path()
            version = resolve_version(apk_path, version)
        elif version is None:
            # 仅打包 Phira:未指定过版本时,默认取最新版本;无版本目录则询问
            versions = list_versions()
            if versions:
                version = versions[0]
                console.print("使用 outputs/ 下最新版本:%s" % version)
            else:
                version = Prompt.ask("outputs/ 下没有版本目录,请输入要打包的版本号(如 4.0.1)")
        execute(steps, apk_path, version, config, logger)
        Prompt.ask("按回车返回菜单", default="")


def parse_args():
    parser = argparse.ArgumentParser(description="Phigros 资源提取器(交互式 TUI)")
    parser.add_argument("--apk", help="Phigros APK 路径(交互模式下可省略)")
    parser.add_argument("--version", help="游戏版本号(默认从 APK 文件名识别)")
    parser.add_argument("--all", action="store_true", help="直跑完整流程")
    parser.add_argument("--info", action="store_true", help="直跑:仅提取游戏信息")
    parser.add_argument("--resource", action="store_true", help="直跑:仅提取资源")
    parser.add_argument("--phira", action="store_true", help="直跑:仅打包 Phira 谱面")
    parser.add_argument("--video", action="store_true", help="直跑:仅提取解锁动画视频")
    parser.add_argument("--input", action="store_true", help="批量处理 input/ 目录(完整流程)")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.input:
        execute_batch(load_config(), make_rich_logger())
        return
    steps = set()
    if args.all:
        steps.update(STEPS)
    for step in STEPS:
        if getattr(args, step):
            steps.add(step)

    if not steps:
        interactive(args)
        return

    if steps & {"info", "resource", "video"} and not args.apk:
        console.print("[red]该步骤需要 --apk 提供 APK 路径[/red]")
        raise SystemExit(1)
    version = resolve_version(args.apk, args.version) if steps & {"info", "resource", "video"} else args.version
    if "phira" in steps and not version and not (steps & {"info", "resource", "video"}):
        raise SystemExit("仅打包时需要 --version 指定版本号")
    execute(steps, args.apk, version, load_config(), make_rich_logger())


if __name__ == "__main__":
    main()
