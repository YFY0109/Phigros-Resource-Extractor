# Phigros-Resource-Extractor

从 Phigros APK 中提取游戏资源与信息的工具。

## 提取内容

| 类别 | 输出目录 | 说明 |
| --- | --- | --- |
| 游戏信息 | `info/` | 定数、曲目信息(曲 id、曲名、曲师、画师、谱师)、收藏品 id 对应中文标题、头像 id、tips 等 |
| 头像图片 | `avatar/` | PNG |
| 谱面文件 | `chart/` | JSON |
| 曲绘 | `illustration/` | PNG |
| 模糊曲绘 | `illustrationBlur/` | PNG |
| 低质量曲绘 | `illustrationLowRes/` | PNG |
| 音乐文件 | `music/` | OGG |

## 使用方法

1. 安装依赖:

   ```sh
   pip install -r requirements.txt
   ```

2. 提取游戏信息(生成 `info/` 目录):

   ```sh
   python gameInformation.py <Phigros APK 路径>
   ```

3. 提取资源文件:

   ```sh
   python resource.py <Phigros APK 路径>
   ```

> 两步必须按顺序执行:`resource.py` 依赖 `gameInformation.py` 生成的 `info/` 数据。

提取哪些类别可在 `config.ini` 的 `[TYPES]` 中配置(默认全部开启)。

在 Android 设备上不带参数运行时会通过 `pm path com.PigeonGames.Phigros` 自动定位已安装的 APK。

## 许可证

[MIT](LICENSE)
