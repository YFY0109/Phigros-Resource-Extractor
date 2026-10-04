"""公共工具:版本识别、输出路径与资源目录定义、配置读取。

提取产物统一存放于 outputs/<版本>/ 下,例如 outputs/4.0.1/charts/。
"""
import os
import re
from configparser import ConfigParser

# 提取产物输出根目录
OUTPUT_ROOT = "outputs"

# 资源类型 -> 输出子目录(相对 outputs/<版本>/)
# resource.py 写入与 phira.py 读取共用此映射,避免两侧目录名不一致
RESOURCE_DIRS = {
    "avatar": "avatars",
    "chart": "charts",
    "illustration": "illustrations",
    "illustrationBlur": "illustrationsBlur",
    "illustrationLowRes": "illustrationsLowRes",
    "music": "music",
}

# config.ini [TYPES] 中资源类型对应的配置键
CONFIG_KEYS = {
    "avatar": "avatar",
    "chart": "Chart",
    "illustrationBlur": "IllustrationBlur",
    "illustrationLowRes": "IllustrationLowRes",
    "illustration": "Illustration",
    "music": "music",
}


def detect_version(apk_path, override=None):
    """从 APK 文件名识别版本号(如 Phigros_4.0.1.apk -> 4.0.1),可用 override 覆盖。"""
    if override:
        return override
    match = re.search(r"\d+(?:\.\d+)+", os.path.basename(apk_path))
    if not match:
        raise SystemExit("无法从文件名 %r 识别版本号,请使用 --version 指定" % os.path.basename(apk_path))
    return match.group(0)


def version_dir(version):
    """版本对应的输出目录,如 outputs/4.0.1。"""
    return os.path.join(OUTPUT_ROOT, version)


def resource_dir(version, resource_type):
    """某版本下某类资源的输出目录。"""
    return os.path.join(version_dir(version), RESOURCE_DIRS[resource_type])


def list_versions():
    """列出 outputs/ 下已有的版本目录,按版本号从新到旧排序。"""
    if not os.path.isdir(OUTPUT_ROOT):
        return []
    versions = [
        name for name in os.listdir(OUTPUT_ROOT)
        if os.path.isdir(os.path.join(OUTPUT_ROOT, name))
    ]
    return sorted(versions, key=_version_sort_key, reverse=True)


def _version_sort_key(version):
    """将 x.y.z 版本号转为可比较的数字元组(非数字段按 0 处理)。"""
    return [int(part) if part.isdigit() else 0 for part in version.split(".")]


def load_config(path="config.ini"):
    """读取 config.ini:提取开关(types)与增量提取设置(update)。"""
    parser = ConfigParser()
    parser.read(path, "utf8")
    types = parser["TYPES"]
    return {
        "types": {name: types.getboolean(key) for name, key in CONFIG_KEYS.items()},
        "update": {
            "main_story": parser["UPDATE"].getint("main_story"),
            "side_story": parser["UPDATE"].getint("side_story"),
            "other_song": parser["UPDATE"].getint("other_song"),
        },
    }
