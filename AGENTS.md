# AGENTS.md

Phigros APK 资源提取工具(Unity 游戏)。纯 Python 脚本,无测试/lint/CI——验证方式就是拿真实的 Phigros APK 跑一遍脚本。

## 命令

必须在仓库根目录运行(`config.ini`、`typetree.json`、`info/` 及所有输出目录都按相对路径解析):

```sh
pip install -r requirements.txt
python gameInformation.py <apk路径>   # 1. 生成 info/*.tsv、info/*.txt
python resource.py <apk路径>          # 2. 生成 avatar/ chart/ illustration*/ music/
python phira.py                       # 3. 用以上产物打包 phira/<EZ|HD|IN|AT>/*.pez
```

- 顺序有硬依赖:`resource.py` 要读 `info/tmp.tsv`(头像映射)和 `info/difficulty.tsv`(增量模式),必须先跑 `gameInformation.py`。
- 在 Android 上(存在 `/data/` 目录)且不带参数运行时,脚本会通过 `pm path com.PigeonGames.Phigros` 自动定位 APK。
- `python gui.py` 是 PyQt5 图形界面,内部就是依次调用上面三条命令。PyQt5 **不在** `requirements.txt` 里,需单独安装。
- `python taptap.py` 是独立工具,用于从 TapTap 获取 Phigros APK 下载信息。

## 注意事项

- **不要升级 `UnityPy==1.10.18`**——代码依赖该版本的精确 API(`get_filtered_objects`、`read_typetree`),新版本会挂。
- `fsb5`(音乐提取)在 Windows 上依赖仓库根目录自带的 `libogg.dll`/`libvorbis.dll`,勿删。仅当 `config.ini` 中 `music = true` 时才惰性导入。
- `config.ini` 的 `[TYPES]` 控制提取的资源类型。`[UPDATE]` 计数器:全为 `0` 表示全量提取;否则按类别只提取最新 N 首——通过对 `info/difficulty.tsv` 列表在两个硬编码锚点曲 ID(`Doppelganger.LeaF`、`Poseidon.1112vsStar`)之间切片实现,游戏大更新后锚点可能需要人工更新。
- `main.py` 已腐烂/无法运行(`from . import resource` 相对导入错误、`resource.run` 签名不符)。不要以它为范本修调用方;用 `resource.py` 命令行或 `gui.py`。
- `resource.py` 只能作为 `__main__` 运行:`save()` 读取的全局量(`config`、`FSB5`)只在 `if __name__ == "__main__"` 块里赋值。
- 大小写不一致:`resource.py` 写出的是小写目录(`illustrationLowRes/`、`illustration/`),但 `phira.py` 读的是 `IllustrationLowRes/`,`.gitignore` 里也是大写。Windows/macOS 上没事,Linux 上会崩。
- `split.py`/`split.sh` 处理的是 `music/*.wav`,而流水线现在输出 `.ogg`——视为已过时。
- `untitled.py` 看起来是 pyuic5 生成的,但里面有手写的槽函数(`extract_apk_file`、`checkboxstate`)——**不要**从 `.ui` 文件重新生成。
- `typetree.json` 是 `gameInformation.py` 解析的 3 个 MonoBehaviour 脚本的 Unity typetree 转储;它跟随游戏版本(参考 "fix: Extraction logic for 4.0.1" 这类提交),游戏数据结构变更时必须同步更新。

## 仓库约定

- 提取产物(`avatar/`、`chart/`、`music/`、`phira/`、除 `requirements.txt` 外的 `*.txt` 等)在 `master` 上被 gitignore;上游把它们发布到按类型划分的独立分支(`info`、`avatar`、`chart`、`illustration`、`illustrationBlur`、`illustrationLowRes`、`music`)——见 README 链接。不要把产物提交到 `master`。
- 界面文本、注释、日志/报错信息使用中文,改动面向用户可见的文本时保持中文。
