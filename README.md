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
| Phira 自制谱 | `outputs/<版本>/phira/<曲目>/` | `<难度>.pez` |

## 使用方法

以下命令需在仓库根目录执行;源码位于 `src/`。

1. 安装依赖(需要 [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv sync
   ```

2. 提取游戏信息:

   ```sh
   uv run python src/gameInformation.py <Phigros APK 路径>
   ```

3. 提取资源文件:

   ```sh
   uv run python src/resource.py <Phigros APK 路径>
   ```

4. (可选)打包为 Phira 自制谱:

   ```sh
   uv run python src/phira.py
   ```

版本号默认从 APK 文件名识别(如 `Phigros_4.0.1.apk` → `4.0.1`),也可以用 `--version` 指定。提取哪些类别可在 `config.json` 的 `types` 中配置(默认全部开启);`update` 可配置只提取各分类最新若干首。

在已有其他版本产物的基础上提取新版本时,内容相同的文件会自动与旧版本建立**硬链接**以节省磁盘空间(判定方式:文件大小 + 头尾各 `sample_bytes` 字节);文件系统不支持硬链接时自动回退为普通写入。该功能可在 `config.json` 的 `dedupe` 中关闭(`enabled`)或调整采样大小(`sample_bytes`,默认 65536 字节)。

> 第 2、3 步需按顺序执行:`resource.py` 的增量提取依赖 `gameInformation.py` 生成的 `outputs/<版本>/info/` 数据。

## 许可证

[GPL-3.0](LICENSE)
