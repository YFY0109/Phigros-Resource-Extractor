"""input/ 目录批量处理:校验 APK 是否为 Phigros、按 hash 跳过已处理项,逐个执行完整流程。

用法(通常经 TUI/WebUI 触发):
    python src/tui.py --input        # 批量处理 input/ 目录(完整流程)
"""
import hashlib
import json
import os
import time
from zipfile import ZipFile, BadZipFile

import gameInformation
import phira
import resource as resource_module
from common import detect_version, version_dir

INPUT_DIR = "input"
HISTORY_PATH = os.path.join("outputs", "processed.json")

# Phigros APK 的特征文件(Unity Addressables 结构)
CATALOG_PATH = "assets/aa/catalog.json"
DATA_PATHS = (
    "assets/bin/Data/data.unity3d",
    "assets/bin/Data/globalgamemanagers.assets",
)


def is_phigros_apk(path):
    """通过 APK 内部特征文件判断是否为 Phigros。"""
    try:
        with ZipFile(path) as apk:
            if CATALOG_PATH not in apk.NameToInfo:
                return False
            return any(data_path in apk.NameToInfo for data_path in DATA_PATHS)
    except (BadZipFile, OSError):
        return False


def sha256_file(path, chunk_size=1024 * 1024):
    """计算文件完整 SHA-256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_history():
    """读取已处理台账(outputs/processed.json):{sha256: 记录}。"""
    try:
        with open(HISTORY_PATH, encoding="utf8") as f:
            history = json.load(f)
        return history if isinstance(history, dict) else {}
    except (OSError, ValueError):
        return {}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH) or ".", exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


def find_pending(logger):
    """扫描 input/,返回 [{path, version, sha256}];跳过非 Phigros、无法识别版本与已处理的 APK。"""
    if not os.path.isdir(INPUT_DIR):
        logger.info("input/ 目录不存在,请创建并放入 APK")
        return []
    history = load_history()
    pending = []
    for name in sorted(os.listdir(INPUT_DIR)):
        if not name.lower().endswith(".apk"):
            continue
        path = os.path.join(INPUT_DIR, name)
        if not os.path.isfile(path):
            continue
        if not is_phigros_apk(path):
            logger.warning("跳过(不是有效的 Phigros APK):%s", name)
            continue
        try:
            version = detect_version(name)
        except SystemExit:
            logger.warning("跳过(文件名中未找到版本号,请重命名如 Phigros_4.0.1.apk):%s", name)
            continue
        digest = sha256_file(path)
        record = history.get(digest)
        if record and os.path.isdir(version_dir(record.get("version", ""))):
            logger.info("跳过(已处理过):%s", name)
            continue
        pending.append({"path": path, "version": version, "sha256": digest})
    return pending


def process_all(steps, config, logger, progress):
    """按顺序对 input/ 下所有待处理 APK 执行指定步骤;返回处理数量。"""
    pending = find_pending(logger)
    if not pending:
        logger.info("input/ 下没有待处理的 APK")
        return 0
    logger.info("共 %d 个 APK 待处理", len(pending))
    history = load_history()
    for index, item in enumerate(pending, 1):
        progress.check_cancelled()
        path, version, digest = item["path"], item["version"], item["sha256"]
        logger.info("=== [%d/%d] %s(版本 %s)===", index, len(pending), os.path.basename(path), version)
        if "info" in steps:
            gameInformation.run(path, version, logger, progress)
        if "resource" in steps:
            resource_module.run(path, version, config, logger, progress)
        if "phira" in steps:
            phira.run(version, logger, progress)
        history[digest] = {
            "apk": os.path.basename(path),
            "version": version,
            "sha256": digest,
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_history(history)
    return len(pending)
