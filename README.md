# Phigros-Resource-Extractor

从 Phigros APK 中提取游戏资源与信息,并可打包为 Phira 的 `.pez` 自制谱。

## 提取内容

产物按游戏版本存放于 `outputs/<版本>/` 下(例如 `outputs/4.0.1/`):

| 类别 | 输出目录 | 说明 |
| --- | --- | --- |
| 游戏信息 | `outputs/<版本>/info/` | 定数、曲目信息(曲 id、曲名、曲师、画师、谱师)、收藏品、头像映射、tips 等 |
| 头像图片 | `outputs/<版本>/avatars/` | PNG |
| 谱面文件 | `outputs/<版本>/charts/` | JSON |
| 曲绘 | `outputs/<版本>/illustrations/` | PNG |
| 模糊曲绘 | `outputs/<版本>/illustrationsBlur/` | PNG |
| 低质量曲绘 | `outputs/<版本>/illustrationsLowRes/` | PNG |
| 音乐文件 | `outputs/<版本>/music/` | OGG |
| 解锁动画视频 | `outputs/<版本>/videos/` | WebM / MP4(来自游戏 VideoClip) |
| Phira 自制谱 | `outputs/<版本>/phira/<曲目>/` | `<难度>.pez`(含 SP / Legacy 特殊难度) |

解锁动画视频(章节解锁 PV 等)有两类来源,都会被提取:

- **Unity 数据文件**内的 `VideoClip`:视频流按 `m_ExternalResources` 的偏移/长度从 `.resource` 中切分(3.x 为 `sharedassets*.assets`,4.x 为 `data.unity3d`);
- **Addressables 资产包** `assets/aa/Android/*.bundle`:如第九章的 `c9.video.*` 章节视频(4.0.0 起)。

容器格式:3.x 与 4.0.0 为 WebM,4.0.1 起为 MP4;文件扩展名按视频内容自动识别,文件名取自游戏内资产名。

## 批量处理(input/)

将待处理 APK 放入仓库根目录的 `input/`(文件名建议包含版本号,如 `Phigros_4.0.1.apk`),然后运行:

```sh
uv run python src/tui.py --input
```

也可以在 TUI 菜单选择「批量处理 input/ 文件夹」,或在 WebUI 点击同名按钮。批量流程会:

- 校验 APK 是否为 Phigros(检查 Addressables 目录与 Unity 数据文件),非 Phigros 文件自动跳过;
- 计算完整 SHA-256,已处理过的 APK(见 `outputs/processed.json` 台账)不会重复处理;
- 对每个新 APK 执行完整流程(信息 → 资源 → 解锁动画视频 → Phira 打包)。

## 运行环境

跨平台(Windows / Linux / macOS),依赖统一由 [uv](https://docs.astral.sh/uv/) 管理。

音乐提取(`music`)会通过 `fsb5` 调用本地库 `libogg` 与 `libvorbis`(`libvorbisenc`
缺失时会回退到 `libvorbis`,Windows 官方 DLL 已含编码符号);不启用音乐时无需这些库。
缺失时会在提取开始前给出包含安装命令的错误提示(也可在 `config.json` 中关闭 `types.music` 跳过):

| 平台 | 获取方式 |
| --- | --- |
| Windows | 仓库根目录已附带 `libogg.dll`、`libvorbis.dll`,另需安装 MSVCR120.dll(VC++ 2013 运行库) |
| Debian/Ubuntu | `sudo apt install libogg0 libvorbis0a libvorbisenc2` |
| Fedora | `sudo dnf install libogg libvorbis` |
| Arch | `sudo pacman -S libogg libvorbis` |
| macOS | `brew install libogg libvorbis` |

也可把对应平台的动态库文件(`libogg.so*`/`libvorbis.so*` 或 `libogg.dll`/`libvorbis.dll`)
放到仓库根目录,程序会优先使用系统库,找不到时再从当前工作目录与仓库根目录加载。

## 使用方法

以下命令需在仓库根目录执行;源码位于 `src/`。

1. 安装依赖(需要 [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv sync
   ```

2. 使用交互式界面(推荐):

   ```sh
   uv run python src/tui.py     # 终端 TUI:菜单 + rich 进度条,可编辑配置
   uv run python src/webui.py   # 浏览器 WebUI:默认 http://127.0.0.1:8000
   ```

   > TUI 也支持直跑,如 `uv run python src/tui.py --apk <路径> --all`。

3. 或按步骤命令行直跑:

   ```sh
   uv run python src/gameInformation.py <Phigros APK 路径>   # 提取游戏信息
   uv run python src/resource.py <Phigros APK 路径>          # 提取资源
   uv run python src/videos.py <Phigros APK 路径>            # 提取解锁动画视频
   uv run python src/phira.py                                # 打包 Phira 自制谱
   ```

版本号默认从 APK 内 `AndroidManifest.xml` 的 `versionName` 读取(不依赖文件名),读取失败时才回退文件名中的 `x.y.z`;也可以用 `--version` 直接指定。提取哪些类别可在 `config.json` 的 `types` 中配置(默认全部开启);`update` 可配置只提取各分类最新若干首。

在已有其他版本产物的基础上提取新版本时,内容相同的文件(包括 Phira 打包产物 `.pez`)会自动与旧版本建立**硬链接**以节省磁盘空间(判定方式:文件大小 + 头尾各 `sample_bytes` 字节);文件系统不支持硬链接时自动回退为普通写入。该功能可在 `config.json` 的 `dedupe` 中关闭(`enabled`)或调整采样大小(`sample_bytes`,默认 65536 字节)。

游戏版本适配数据(typetree)存放于 `typetree/`:`default.json` 为当前游戏版本,历史版本按完整版本号命名(如 `3.20.0.json`);游戏更新后需重新生成,详见 `typetree/README.md`。WebUI 的监听地址与端口可在 `config.json` 的 `webui` 中配置(端口被占用时会自动更换)。

> 第 2、3 步需按顺序执行:`resource.py` 的增量提取依赖 `gameInformation.py` 生成的 `outputs/<版本>/info/` 数据。

## 测试

```sh
uv run pytest
```

## 许可证

[GPL-3.0](LICENSE)
