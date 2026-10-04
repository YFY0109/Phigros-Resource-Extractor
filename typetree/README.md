# typetrees

按游戏版本存放的 Unity typetree 转储,供 `gameInformation.py` 解析 MonoBehaviour 使用。

查找规则:`typetree/<完整版本号>.json` 优先;未找到时回退到 `typetree/default.json`(当前游戏版本)。

| 文件 | 适配版本 | 来源 |
| --- | --- | --- |
| `default.json` | 当前游戏版本(4.0.x) | 原项目 7aGiven/Phigros_Resource 提交 `788c346`("4.0.0"),原为仓库根的 `typetree.json` |
| `3.20.0.json` | Phigros 3.20.0(第九章更新前) | 原项目提交 `9399e410`(2024-12-05),已在 3.20.0 APK 上实测通过 |

游戏更新后,如果 `gameInformation.py` 报 typetree 与游戏版本不匹配,需要重新生成对应版本的 typetree:

- 作为当前版本的默认:更新 `default.json`;
- 作为历史版本适配:放入 `<完整版本号>.json`(如 `4.1.0.json`)。
