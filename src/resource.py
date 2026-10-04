"""从 Phigros APK 提取资源(头像、谱面、曲绘、音乐)。

用法:
    python resource.py <Phigros APK 路径> [--version X.Y.Z]

产物输出到 outputs/<版本>/ 下(目录映射见 common.RESOURCE_DIRS)。
"""
import argparse
import base64
import csv
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from queue import Queue
from zipfile import ZipFile

from UnityPy import Environment
from UnityPy.classes import AudioClip
from UnityPy.enums import ClassIDType

from common import detect_version, load_config, resource_dir, version_dir
from dedupe import DedupeStore, write_file
from log import init_console_logger
from progress import NULL_PROGRESS

# 需要读取的 Unity 资产类型
BUFFER_CLASSES = (ClassIDType.TextAsset, ClassIDType.Sprite, ClassIDType.AudioClip)

# 资产解码/写盘线程数
WORKER_THREADS = 6

APK_ASSETS_ROOT = "assets/aa"
APK_BUNDLE_TEMPLATE = APK_ASSETS_ROOT + "/Android/%s"

# 第九章谢幕曲,含四难度差分曲绘的独立处理分支
CHAPTER9_ENDING_CHART_ID = "WhatdoyouwantmorethanaHappyending.Apo11oHALOprogramft安月名莉子大瀬良あい"

# [UPDATE] 增量提取的区段分界曲 ID(跟随游戏曲目表,游戏更新后可能需要调整)
MAIN_STORY_END = "Doppelganger.LeaF"
OTHER_SONG_END = "Poseidon.1112vsStar"


class ByteReader:
    """按小端读取 catalog 桶数据的极简读取器。"""

    def __init__(self, data):
        self.data = data
        self.position = 0

    def readInt(self):
        self.position += 4
        return self.data[self.position - 4] ^ self.data[self.position - 3] << 8 ^ self.data[self.position - 2] << 16


class AssetWriter:
    """单线程落盘队列,避免多线程同时写文件。close() 会等待队列清空后退出。

    store 提供时(去重功能开启),文件由 DedupeStore 处理(硬链接优先、自动回退写入)。
    """

    def __init__(self, store=None):
        self._store = store
        self._queue = Queue()
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            path, data = item
            if self._store is not None:
                self._store.write(path, data)
            else:
                write_file(path, data)

    def put(self, path, data):
        self._queue.put((path, data))

    def close(self):
        self._queue.put(None)
        self._thread.join()


def save_image(writer, path, image):
    bytes_io = BytesIO()
    image.save(bytes_io, "png")
    writer.put(path, bytes_io)


def save_music(writer, path, music: AudioClip):
    from fsb5 import FSB5  # 仅音乐提取需要,延迟导入,未启用音乐时无需该依赖
    fsb = FSB5(music.m_AudioData)
    writer.put(path, fsb.rebuild_sample(fsb.samples[0]))


def _submit(pool, logger, func, *args):
    """提交后台任务,完成后记录异常(未检查的 Future 会静默丢失产物)。"""
    future = pool.submit(func, *args)
    future.add_done_callback(lambda f: _log_task_error(f, logger))
    return future


def _log_task_error(future, logger):
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error("后台任务失败: %s", error, exc_info=error)


def save_asset(key, entry, writer, pool, config, version, logger):
    """按资源类型匹配 catalog 条目 key,并把资产写入对应输出目录。"""
    types = config["types"]
    obj = next(entry.get_filtered_objects(BUFFER_CLASSES)).read()
    if types["avatar"] and key[:7] == "avatar.":
        key = key[7:]
        bytes_io = BytesIO()
        obj.image.save(bytes_io, "png")
        writer.put(os.path.join(resource_dir(version, "avatar"), "%s.png" % key), bytes_io)
    elif types["chart"] and key[-14:-7] == "/Chart_" and key[-5:] == ".json":
        logger.info(key)
        song_dir = os.path.join(resource_dir(version, "chart"), key[:-14])
        os.makedirs(song_dir, exist_ok=True)
        writer.put(os.path.join(song_dir, "%s.json" % key[-7:-5]), obj.script)
    elif types["illustrationBlur"] and key[-23:-3] == ".0/IllustrationBlur.":
        key = key[:-23]
        bytes_io = BytesIO()
        obj.image.save(bytes_io, "png")
        writer.put(os.path.join(resource_dir(version, "illustrationBlur"), "%s.png" % key), bytes_io)
    elif types["illustrationLowRes"] and key[-25:-3] == ".0/IllustrationLowRes.":
        key = key[:-25]
        _submit(pool, logger, save_image, writer, os.path.join(resource_dir(version, "illustrationLowRes"), "%s.png" % key), obj.image)
    elif types["illustration"] and key[-19:-3] == ".0/Illustration.":
        key = key[:-19]
        _submit(pool, logger, save_image, writer, os.path.join(resource_dir(version, "illustration"), "%s.png" % key), obj.image)
    elif types["music"] and key[-12:] == ".0/music.wav":
        key = key[:-12]
        _submit(pool, logger, save_music, writer, os.path.join(resource_dir(version, "music"), "%s.ogg" % key), obj)
    # 第九章谢幕曲的四难度差分曲绘
    elif key.startswith("%s.0/Illustration" % CHAPTER9_ENDING_CHART_ID):
        level_id = key[-7:-4]  # _EZ/_HD/_IN/_AT
        if level_id[0] == "_":
            if types["illustrationBlur"] and key[-26:-7] == ".0/IllustrationBlur":
                bytes_io = BytesIO()
                obj.image.save(bytes_io, "png")
                writer.put(os.path.join(resource_dir(version, "illustrationBlur"), "%s%s.png" % (CHAPTER9_ENDING_CHART_ID, level_id)), bytes_io)
            elif types["illustrationLowRes"] and key[-28:-7] == ".0/IllustrationLowRes":
                _submit(pool, logger, save_image, writer, os.path.join(resource_dir(version, "illustrationLowRes"), "%s%s.png" % (CHAPTER9_ENDING_CHART_ID, level_id)), obj.image)
            elif types["illustration"] and key[-22:-7] == ".0/Illustration":
                _submit(pool, logger, save_image, writer, os.path.join(resource_dir(version, "illustration"), "%s%s.png" % (CHAPTER9_ENDING_CHART_ID, level_id)), obj.image)


def load_bundle(env, apk, key, entry, logger):
    """加载一个资产包;失败时记录并返回 False,不中断整体提取。"""
    try:
        env.load_file(BytesIO(apk.read(APK_BUNDLE_TEMPLATE % entry)), name=key)
        return True
    except Exception:
        logger.exception("资产包读取失败,已跳过: %s", key)
        return False


def process_bundle(key, entry, apk, pool, writer, config, version, logger):
    """全量模式:每个资产包使用独立 Environment,解析后逐资产保存。"""
    env = Environment()
    if not load_bundle(env, apk, key, entry, logger):
        return
    for i_key, i_entry in env.files.items():
        try:
            save_asset(i_key, i_entry, writer, pool, config, version, logger)
        except Exception:
            logger.exception("资产保存失败,已跳过: %s", i_key)


def parse_catalog(path, logger):
    """解析 APK 内的 Addressables catalog,返回 [key, entry] 表。"""
    with ZipFile(path) as apk:
        with apk.open(APK_ASSETS_ROOT + "/catalog.json") as f:
            data = json.load(f)

    key = base64.b64decode(data["m_KeyDataString"])
    bucket = base64.b64decode(data["m_BucketDataString"])
    entry = base64.b64decode(data["m_EntryDataString"])

    table = []
    reader = ByteReader(bucket)
    for x in range(reader.readInt()):
        key_position = reader.readInt()
        key_type = key[key_position]
        key_position += 1
        if key_type == 0:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode()
        elif key_type == 1:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode("utf16")
        elif key_type == 4:
            key_value = key[key_position]
        else:
            raise ValueError("未知的 catalog 键类型 %s(位置 %s)" % (key_type, key_position))
        entry_value = None
        for i in range(reader.readInt()):
            entry_position = reader.readInt()
            entry_value = entry[4 + 28 * entry_position:4 + 28 * entry_position + 28]
            entry_value = entry_value[8] ^ entry_value[9] << 8
        table.append([key_value, entry_value])
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]
    for i in range(len(table) - 1, -1, -1):
        if type(table[i][0]) == int or table[i][0][:15] == "Assets/Tracks/#" or table[i][0][:14] != "Assets/Tracks/" and \
                table[i][0][:7] != "avatar.":
            del table[i]
        elif table[i][0][:14] == "Assets/Tracks/":
            table[i][0] = table[i][0][14:]
    for i, (key, value) in enumerate(table):
        if '_' in value:
            table[i][1] = value.split('_', 1)[1]
        logger.debug("%s, %s", key, value)
    return table


def load_song_ids(difficulty_path):
    """读取 difficulty.csv 中的歌曲 ID 列表(文件按游戏内曲目顺序排列)。"""
    with open(difficulty_path, encoding="utf-8-sig", newline="") as f:
        return [row[0] for row in csv.reader(f) if row]


def select_songs(all_ids, update):
    """按 [UPDATE] 计数选取主线/单曲/支线各区段最新的若干首,按原顺序返回。"""
    index1 = all_ids.index(MAIN_STORY_END)
    index2 = all_ids.index(OTHER_SONG_END)
    main = all_ids[:index1][-update["main_story"]:] if update["main_story"] else []
    other = all_ids[index1:index2][-update["other_song"]:] if update["other_song"] else []
    side = all_ids[index2:][-update["side_story"]:] if update["side_story"] else []
    return main + other + side


def run(apk_path, version, config, logger, progress=None):
    progress = progress or NULL_PROGRESS
    types = config["types"]

    # 创建启用的资源输出目录;Android 上放置 .nomedia 防止媒体扫描
    for resource_type, enabled in types.items():
        if not enabled:
            continue
        directory = resource_dir(version, resource_type)
        os.makedirs(directory, exist_ok=True)
        if os.path.isdir("/system/") and not os.getcwd().startswith("/data/"):
            with open(os.path.join(directory, ".nomedia"), "wb"):
                pass

    table = parse_catalog(apk_path, logger)

    dedupe_config = config.get("dedupe", {})
    store = None
    if dedupe_config.get("enabled", True):
        store = DedupeStore(version, int(dedupe_config.get("sample_bytes", 65536)), logger)
    writer = AssetWriter(store)
    started = time.time()
    update = config["update"]
    try:
        with ThreadPoolExecutor(WORKER_THREADS) as pool:
            if update["main_story"] == 0 and update["other_song"] == 0 and update["side_story"] == 0:
                # 全量提取
                progress.start("提取资源(全量)", total=len(table))
                with ZipFile(apk_path) as apk:
                    for key, entry in table:
                        progress.check_cancelled()
                        process_bundle(key, entry, apk, pool, writer, config, version, logger)
                        progress.advance(key)
            else:
                # 增量提取:仅处理选中歌曲的资产包
                difficulty_path = os.path.join(version_dir(version), "info", "difficulty.csv")
                try:
                    song_ids = select_songs(load_song_ids(difficulty_path), update)
                except FileNotFoundError:
                    raise SystemExit("增量提取需要 %s,请先运行 gameInformation.py" % difficulty_path)
                except ValueError as e:
                    raise SystemExit("增量分段失败:%s(锚点未在 difficulty.csv 中找到?)" % e)
                logger.info(str(song_ids))
                progress.start("提取资源(增量)", total=None)
                env = Environment()
                with ZipFile(apk_path) as apk:
                    for key, entry in table:
                        progress.check_cancelled()
                        if key[:7] == "avatar.":
                            if load_bundle(env, apk, key, entry, logger):
                                progress.advance(key)
                            continue
                        for song_id in song_ids:
                            if key.startswith("%s.0/" % song_id):
                                if load_bundle(env, apk, key, entry, logger):
                                    progress.advance(key)
                                break
                for i_key, i_entry in env.files.items():
                    progress.check_cancelled()
                    try:
                        save_asset(i_key, i_entry, writer, pool, config, version, logger)
                    except Exception:
                        logger.exception("资产保存失败,已跳过: %s", i_key)
    finally:
        # 队列中可能还有大量待写文件,单独显示一个阶段,避免进度条停住无反馈
        progress.start("写入剩余文件", total=None)
        writer.close()
        if store is not None:
            store.flush()
            store.report()
        progress.finish()
    logger.info("%f秒" % round(time.time() - started, 4))


def parse_args():
    parser = argparse.ArgumentParser(description="从 Phigros APK 提取资源")
    parser.add_argument("apk", help="Phigros APK 路径")
    parser.add_argument("--version", help="游戏版本号(默认从 APK 文件名识别)")
    return parser.parse_args()


def main():
    args = parse_args()
    version = detect_version(args.apk, args.version)
    logger = init_console_logger()
    logger.info("版本 %s,输出目录 %s" % (version, version_dir(version)))
    run(args.apk, version, load_config(), logger)


if __name__ == "__main__":
    main()
