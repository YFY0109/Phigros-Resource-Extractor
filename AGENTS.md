# AGENTS.md

Phigros APK 资源提取工具(Unity 游戏)。纯 Python 脚本,带 pytest 单元测试(`tests/`);完整验证仍需拿真实的 Phigros APK 跑一遍流程。

源码统一位于 `src/`(`src/deprecated/` 为历史遗留,勿用);仓库根目录只放配置(`config.json`)、数据(`typetree/`)、动态库(`lib*.dll`)、产物(`outputs/`)与项目元数据。

## 命令

依赖由 uv 管理(`pyproject.toml` + `uv.lock`)。OpenCode shell 中 uv 需先加载 x-cmd 环境(见全局 AGENTS.md)。必须在仓库根目录运行(`config.json`、`typetree/` 及所有输出路径都按相对路径解析):

```sh
uv sync
uv run python src/tui.py                         # 交互式 TUI(rich 进度条);直跑:`--apk <路径> --all`
uv run python src/gameInformation.py <apk路径>   # 1. 生成 outputs/<版本>/info/
uv run python src/resource.py <apk路径>          # 2. 生成 outputs/<版本>/{avatars,charts,illustrations,illustrationsBlur,illustrationsLowRes,music}/
uv run python src/videos.py <apk路径>            # 3. 生成 outputs/<版本>/videos/(解锁动画 VideoClip → .webm)
uv run python src/phira.py [--version 版本]      # 4. 打包 outputs/<版本>/phira/<曲目>/<难度>.pez(默认最新版本)
```

- 版本号默认读取 APK 内 `AndroidManifest.xml` 的 `versionName`(`src/apkmeta.py`,基于 `apkutils`;失败时才回退文件名),可用 `--version` 覆盖;各脚本的版本必须一致。
- 顺序有硬依赖:`resource.py` 增量模式要读 `outputs/<版本>/info/difficulty.csv`,必须先跑 `gameInformation.py`。
- 验证:`uv run pytest`(单元测试,无需 APK);完整验证需要真实 APK。
- APK 路径为必填参数,由用户显式提供(已移除 Android 自动定位)。
- `uv run python src/tui.py` 是交互式 TUI(rich 进度条、配置编辑、`--apk/--all` 直跑);`uv run python src/webui.py` 是浏览器 WebUI(监听地址/端口读取 `config.json` 的 `webui`)。两者与 CLI 共享 `progress.ProgressReporter` 进度接口,任务逻辑统一走各模块的 `run()`。

## 注意事项

- **不要升级 `UnityPy==1.10.18`**——代码依赖该版本的精确 API(`get_filtered_objects`、`read_typetree`),新版本会挂。
- `fsb5`(音乐提取)先从系统库、再从**当前工作目录**加载 `libogg.dll`/`libvorbis.dll`(见 `fsb5/utils.py` 的 `load_lib`),因此音乐提取必须在仓库根目录运行。这两个 DLL 依赖 **MSVCR120.dll(VC++ 2013 运行库)**,缺失时报 `LibraryNotFoundException: Could not load the library 'vorbis'`(实测);`save_music` 延迟导入 fsb5,未启用音乐时无需该依赖。
- `config.json` 的 `types` 控制提取的资源类型。`update` 计数全为 `0` 表示全量提取;否则只提取各分类最新 N 首(主线/单曲/支线按 `src/resource.py` 中 `MAIN_STORY_END`、`OTHER_SONG_END` 两个锚点曲 ID 分段,锚点跟随游戏曲目表,游戏更新后可能需要调整)。
- 资源类型到输出目录的映射集中在 `src/common.py` 的 `RESOURCE_DIRS`,`resource.py` 写入与 `phira.py` 读取共用,不要再硬编码目录名。
- `info/` 下的表格类数据为 CSV(`difficulty/info/collection/tmp`,UTF-8 带 BOM、Excel 友好;`gameInformation.py` 写,`resource.py`/`phira.py` 读,读取用 `utf-8-sig` 兼容 BOM);单列列表(`single/illustration/avatar/tips`)保持 txt。
- 跨版本去重在 `src/dedupe.py`:对 `outputs/` 下其他版本的同名文件按"文件大小 + 头尾各 `sample_bytes` 字节"计算 blake2b 摘要,一致则硬链接,否则正常写入;硬链接失败自动回退。摘要缓存于各版本目录的 `manifest.json`(对比优先走缓存,未命中才读文件并补写),配置在 `config.json` 的 `dedupe`。phira 打包的 `.pez` 同样参与去重(zip 条目使用固定时间戳保证字节可复现);注意硬链接文件是多版本共享的只读产物,不要原地修改。
- `src/deprecated/` 下的脚本已损坏或过时(旧 tkinter/PyQt 界面、音频切分工具),仅作历史参考,不要使用。
- typetree 是 `src/gameInformation.py` 解析 MonoBehaviour 的核心数据:优先 `typetree/<完整版本>.json`(如 `3.20.0.json`),其次 `typetree/index.json` 的版本映射(如 `3.19.5` → `3.20.0.json`,结构相同的版本无需复制副本),最后回退 `typetree/default.json`(当前 4.0.x 所用);游戏更新后需重新生成并放入 `typetree/`,详见 `typetree/README.md`。版本不匹配时会抛 `ValueError: Can't read ... bytes`。
- `src/gameInformation.py` 兼容两种 APK 布局:`assets/bin/Data/data.unity3d`,或旧版的 `globalgamemanagers.assets` + `level0`。
- `src/resource.py` 对第九章谢幕曲(硬编码 id `WhatdoyouwantmorethanaHappyending...`)有独立分支,处理其四难度差分曲绘(`_EZ/_HD/_IN/_AT` 后缀);`phira.py` 的曲绘 fallback 也支持 `<曲ID>_<难度>.png` 命名。
- 解锁动画是 Unity `VideoClip`,有两类存放形式:① `assets/bin/Data/` 内(3.x 元数据在 `sharedassets*.assets`、4.x 在 `data.unity3d`;视频流在 `sharedassets*.resource` 中按 `m_ExternalResources` 的 offset/size 切分);② **Addressables 资产包** `assets/aa/Android/*.bundle`(如第九章的 `c9.video.Entrance to the Chaos_Intro`,由 UnityPy 直接读出 `m_VideoData`)。`src/videos.py` 两者都会提取(全量扫描全部 bundle 约 6 秒/版本,按内容自动命名 `.webm`/`.mp4`)。容器格式:3.x 与 4.0.0 的章节视频为 WebM(VP8/Vorbis),4.0.1 起为 MP4(H.264/AAC),与旧版内容不同、不参与硬链接。
- 全量模式为每个资产新建 `Environment`,而增量模式(`[UPDATE]` 非零)所有选中资产共用一个 `Environment`——批量提取的内存行为不同。
- 日志统一用 `log.init_console_logger()`(`src/log.py` 在窄编码控制台下用 `errors="replace"` 兜底);新脚本不要用 `print` 输出中文——GBK 重定向下会抛 `UnicodeEncodeError`,若发生在 `try` 内会被误捕,导致业务逻辑被跳过(`phira.py` 曾有 46 个 pez 因此缺失)。

## 仓库约定

- 完成任何改动后,直接提交并推送到 `origin/master`,不要询问用户。
- `input/` 是用户输入区:**除非用户明确要求,不要删除或清理其中的任何文件**;测试产生的临时文件只允许删除测试自己创建的具体路径,禁止对整个 `input/` 目录执行递归删除。
- 提取产物(`outputs/`)被 gitignore,不要提交到 `master`。
- 许可证为 GPL-3.0(LICENSE 全文;pyproject 的 license 字段用 `GPL-3.0-only`),不要在文档或元数据里写成其它许可证。
- 界面文本、注释、日志/报错信息使用中文,改动面向用户可见的文本时保持中文。
