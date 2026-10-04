"""公共工具:版本识别、输出路径与资源目录定义、JSON 配置读写。

配置文件为仓库根目录的 config.json。
"""
import copy
import json
import os
import re

# 提取产物输出根目录
OUTPUT_ROOT = "outputs"

# 配置文件路径
CONFIG_PATH = "config.json"

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

# 默认配置;load_config 会与用户配置递归合并(用户配置优先)
DEFAULT_CONFIG = {
    "types": {
        "avatar": True,
        "chart": True,
        "illustrationBlur": True,
        "illustrationLowRes": True,
        "illustration": True,
        "music": True,
    },
    "update": {
        "main_story": 0,
        "other_song": 0,
        "side_story": 0,
    },
    "dedupe": {
        "enabled": True,
        "sample_bytes": 65536,
    },
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


def load_config(path=CONFIG_PATH):
    """读取 JSON 配置并与默认值合并;文件不存在时生成默认配置。"""
    if os.path.isfile(path):
        with open(path, encoding="utf8") as f:
            config = json.load(f)
    else:
        config = copy.deepcopy(DEFAULT_CONFIG)
        save_config(config, path)
    return _merge_defaults(config, DEFAULT_CONFIG)


def save_config(config, path=CONFIG_PATH):
    """把配置写回 JSON 文件(UTF-8、两空格缩进)。"""
    with open(path, "w", encoding="utf8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _merge_defaults(config, defaults):
    """递归合并默认值:用户配置缺失的键用默认值补齐,自定义的键保留。"""
    merged = copy.deepcopy(defaults)
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(value, merged[key])
        else:
            merged[key] = value
    return merged
