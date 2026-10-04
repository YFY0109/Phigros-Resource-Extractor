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
| Phira 自制谱 | `outputs/<版本>/phira/<难度>/` | `.pez` |

## 使用方法

1. 安装依赖(需要 [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv sync
   ```

2. 提取游戏信息:

   ```sh
   uv run python gameInformation.py <Phigros APK 路径>
   ```

3. 提取资源文件:

   ```sh
   uv run python resource.py <Phigros APK 路径>
   ```

4. (可选)打包为 Phira 自制谱:

   ```sh
   uv run python phira.py
   ```

版本号默认从 APK 文件名识别(如 `Phigros_4.0.1.apk` → `4.0.1`),也可以用 `--version` 指定。提取哪些类别可在 `config.ini` 的 `[TYPES]` 中配置(默认全部开启);`[UPDATE]` 可配置只提取各分类最新若干首。

> 第 2、3 步需按顺序执行:`resource.py` 的增量提取依赖 `gameInformation.py` 生成的 `outputs/<版本>/info/` 数据。

在 Android 设备上不带参数运行时会通过 `pm path com.PigeonGames.Phigros` 自动定位已安装的 APK。

## 许可证

[GPL-3.0](LICENSE)
