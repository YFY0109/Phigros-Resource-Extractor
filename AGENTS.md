# AGENTS.md

Phigros APK 资源提取工具(Unity 游戏)。纯 Python 脚本,无测试/lint/CI——验证方式就是拿真实的 Phigros APK 跑一遍脚本。

## 命令

依赖由 uv 管理(`pyproject.toml` + `uv.lock`)。OpenCode shell 中 uv 需先加载 x-cmd 环境(见全局 AGENTS.md)。必须在仓库根目录运行(`config.ini`、`typetree.json` 及所有输出路径都按相对路径解析):

```sh
uv sync
uv run python gameInformation.py <apk路径>   # 1. 生成 outputs/<版本>/info/
uv run python resource.py <apk路径>          # 2. 生成 outputs/<版本>/{avatars,charts,illustrations,illustrationsBlur,illustrationsLowRes,music}/
uv run python phira.py [--version 版本]      # 3. 打包 outputs/<版本>/phira/<EZ|HD|IN|AT>/*.pez(默认最新版本)
```

- 版本号默认从 APK 文件名识别(如 `Phigros_4.0.1.apk` → `4.0.1`),可用 `--version` 覆盖;各脚本的版本必须一致。
- 顺序有硬依赖:`resource.py` 增量模式要读 `outputs/<版本>/info/difficulty.tsv`,必须先跑 `gameInformation.py`。
- 快速验证(无需 APK):`uv run python -m py_compile common.py gameInformation.py resource.py phira.py`;完整验证需要真实 APK。
- 在 Android 上(存在 `/data/` 目录)且不带参数运行时,脚本会通过 `pm path com.PigeonGames.Phigros` 自动定位 APK。
- `uv run python gui.py` 是 PyQt5 图形界面(先 `uv sync --extra gui`);内部经 `subprocess` 调用当前解释器执行上述脚本。
- `uv run python taptap.py` 是独立工具,用于从 TapTap 获取 Phigros APK 下载信息。

## 注意事项

- **不要升级 `UnityPy==1.10.18`**——代码依赖该版本的精确 API(`get_filtered_objects`、`read_typetree`),新版本会挂。
- `fsb5`(音乐提取)先从系统库、再从**当前工作目录**加载 `libogg.dll`/`libvorbis.dll`(见 `fsb5/utils.py` 的 `load_lib`),因此音乐提取必须在仓库根目录运行。这两个 DLL 依赖 **MSVCR120.dll(VC++ 2013 运行库)**,缺失时报 `LibraryNotFoundException: Could not load the library 'vorbis'`(实测);`save_music` 延迟导入 fsb5,未启用音乐时无需该依赖。
- `config.ini` 的 `[TYPES]` 控制提取的资源类型。`[UPDATE]` 计数全为 `0` 表示全量提取;否则只提取各分类最新 N 首(主线/单曲/支线按 `resource.py` 中 `MAIN_STORY_END`、`OTHER_SONG_END` 两个锚点曲 ID 分段,锚点跟随游戏曲目表,游戏更新后可能需要调整)。
- 资源类型到输出目录的映射集中在 `common.RESOURCE_DIRS`,`resource.py` 写入与 `phira.py` 读取共用,不要再硬编码目录名。
- `main.py` 已腐烂/无法运行(`from . import resource` 相对导入错误、旧接口签名),不要以它为范本;用 CLI 脚本或 `gui.py`。
- `split.py`/`split.sh` 处理的是 `music/*.wav`,与当前 `.ogg` 输出不匹配——视为已过时。
- `untitled.py` 看起来是 pyuic5 生成的,但里面有手写的槽函数(`extract_apk_file`、`checkboxstate`)——**不要**从 `.ui` 文件重新生成。
- typetree 是 `gameInformation.py` 解析 MonoBehaviour 的核心数据:优先使用 `typetree/<完整版本>.json`(已内置 `typetree/3.20.0.json` 适配旧版),未找到则回退根目录 `typetree.json`(当前 4.0.x 所用);游戏更新后需重新生成并放入 `typetree/`,详见 `typetree/README.md`。版本不匹配时会抛 `ValueError: Can't read ... bytes`。
- `gameInformation.py` 兼容两种 APK 布局:`assets/bin/Data/data.unity3d`,或旧版的 `globalgamemanagers.assets` + `level0`。
- `resource.py` 对第九章谢幕曲(硬编码 id `WhatdoyouwantmorethanaHappyending...`)有独立分支,处理其四难度差分曲绘(`_EZ/_HD/_IN/_AT` 后缀);`phira.py` 的曲绘 fallback 也支持 `<曲ID>_<难度>.png` 命名。
- 全量模式为每个资产新建 `Environment`,而增量模式(`[UPDATE]` 非零)所有选中资产共用一个 `Environment`——批量提取的内存行为不同。
- 日志统一用 `log.init_console_logger()`(`log.py` 在窄编码控制台下用 `errors="replace"` 兜底);新脚本不要用 `print` 输出中文——GBK 重定向下会抛 `UnicodeEncodeError`,若发生在 `try` 内会被误捕,导致业务逻辑被跳过(`phira.py` 曾有 46 个 pez 因此缺失)。

## 仓库约定

- 完成任何改动后,直接提交并推送到 `origin/master`,不要询问用户。
- 提取产物(`outputs/`)被 gitignore,不要提交到 `master`。
- 许可证为 GPL-3.0(LICENSE 全文;pyproject 的 license 字段用 `GPL-3.0-only`),不要在文档或元数据里写成其它许可证。
- 界面文本、注释、日志/报错信息使用中文,改动面向用户可见的文本时保持中文。
