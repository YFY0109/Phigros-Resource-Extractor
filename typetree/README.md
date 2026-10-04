# typetrees

按游戏版本存放的 Unity typetree 转储,供 `gameInformation.py` 解析 MonoBehaviour 使用。

查找规则:

1. `typetree/<完整版本号>.json`(版本专属文件);
2. 否则查 `index.json` 的映射(适合数据结构相同、无需单独存放副本的版本,如 `3.19.5` → `3.20.0.json`);
3. 否则回退 `default.json`(当前游戏版本)。

| 文件 | 适配版本 | 来源 |
| --- | --- | --- |
| `default.json` | 当前游戏版本(4.0.x) | 原项目 7aGiven/Phigros_Resource 提交 `788c346`("4.0.0"),原为仓库根的 `typetree.json` |
| `3.20.0.json` | Phigros 3.20.0 及其同代版本(如 3.19.5,见 `index.json`) | 原项目提交 `9399e410`(2024-12-05),已在 3.20.0 / 3.19.5 APK 上实测通过 |

游戏更新后,如果 `gameInformation.py` 报 typetree 与游戏版本不匹配,需要重新生成对应版本的 typetree:

- 作为当前版本的默认:更新 `default.json`;
- 作为历史版本适配:放入 `<完整版本号>.json`(如 `4.1.0.json`);与已有 typetree 结构相同的版本,在 `index.json` 中指向同一文件即可,无需复制副本。

## 已探测版本记录

| 版本 | 结果 |
| --- | --- |
| 3.19.5 | 与 `3.20.0.json` 兼容(见 `index.json` 映射) |
| 3.0.0 | **与 `3.20.0.json` 不兼容**(GameInformation 字段结构不同),需要单独的 typetree 才能提取游戏信息;资源提取不受影响 |
