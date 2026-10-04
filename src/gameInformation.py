"""从 Phigros APK 提取游戏信息(定数、曲目、收藏品、头像映射、tips 等)。

用法:
    python gameInformation.py <Phigros APK 路径> [--version X.Y.Z]

产物输出到 outputs/<版本>/info/。
"""
import argparse
import csv
import json
import os
import zipfile
from io import BytesIO

from UnityPy import Environment

from common import detect_version, version_dir
from log import init_console_logger
from progress import NULL_PROGRESS

# typetree 目录:版本专属 <版本>.json 优先,其次 index.json 的版本映射,最后回退 default.json
TYPETREE_DIR = "typetree"
TYPETREE_INDEX = os.path.join(TYPETREE_DIR, "index.json")
DEFAULT_TYPETREE = os.path.join(TYPETREE_DIR, "default.json")


def load_typetree_index():
    """读取版本映射文件(如 {"3.19.5": "3.20.0.json"});不可用时返回空表。"""
    try:
        with open(TYPETREE_INDEX, encoding="utf8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def find_typetree(version, logger):
    """按游戏版本查找 typetree:专属文件 → index.json 映射 → default.json。"""
    versioned = os.path.join(TYPETREE_DIR, "%s.json" % version)
    if os.path.isfile(versioned):
        logger.info("使用版本专属 typetree: %s" % versioned)
        return versioned
    mapped = load_typetree_index().get(version)
    if mapped:
        candidate = os.path.join(TYPETREE_DIR, mapped)
        if os.path.isfile(candidate):
            logger.info("使用版本映射的 typetree: %s -> %s" % (version, candidate))
            return candidate
    logger.info("未找到 %s 的专属 typetree,使用默认 %s" % (version, DEFAULT_TYPETREE))
    return DEFAULT_TYPETREE


def write_csv(path, rows):
    """写 CSV(UTF-8 带 BOM,便于 Excel 直接打开;逗号/引号由 csv 模块自动转义)。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def read_typetree(obj, typetree_data, script_name, read_monobehaviour=False):
    """解析 MonoBehaviour typetree;失败时给出与游戏版本相关的明确错误。"""
    try:
        return obj.read_typetree(typetree_data, read_monobehaviour)
    except Exception as e:
        raise RuntimeError("解析 %s 失败,typetree 可能与游戏版本不匹配:%s" % (script_name, e))


def run(path, version, logger, progress=None):
    progress = progress or NULL_PROGRESS
    progress.start("解析游戏信息")
    progress.check_cancelled()
    output_dir = os.path.join(version_dir(version), "info")
    os.makedirs(output_dir, exist_ok=True)

    with open(find_typetree(version, logger), encoding="utf8") as f:
        typetree = json.load(f)
    env = Environment()
    with zipfile.ZipFile(path) as apk:
        if "assets/bin/Data/data.unity3d" in apk.NameToInfo:
            with apk.open("assets/bin/Data/data.unity3d") as f:
                env.load_file(BytesIO(f.read()), name="assets/bin/Data/data.unity3d")
        else:
            with apk.open("assets/bin/Data/globalgamemanagers.assets") as f:
                env.load_file(BytesIO(f.read()), name="assets/bin/Data/globalgamemanagers.assets")
            with apk.open("assets/bin/Data/level0") as f:
                env.load_file(BytesIO(f.read()))
    progress.advance("已加载 Unity 数据")

    game_information = None
    collections = None
    tips = None
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        try:
            script = data.m_Script.get_obj()
            if script is None:
                continue
            script_name = script.read().name
        except Exception:
            continue  # 无法读取脚本的 MonoBehaviour 直接跳过

        if script_name == "GameInformation":
            game_information = read_typetree(obj, typetree["GameInformation"], script_name)
        elif script_name == "GetCollectionControl":
            collections = read_typetree(obj, typetree["GetCollectionControl"], script_name, True)
        elif script_name == "TipsProvider":
            tips = read_typetree(obj, typetree["TipsProvider"], script_name, True)

    if game_information is None or collections is None or tips is None:
        raise RuntimeError(
            "APK 中缺少必要的 MonoBehaviour(GameInformation/GetCollectionControl/TipsProvider),"
            "typetree 可能与游戏版本不匹配"
        )

    difficulty = []
    table = []
    for key, songs in game_information["song"].items():
        if key == "otherSongs":
            continue
        for song in songs:
            if len(song["difficulty"]) == 5:
                song["difficulty"].pop()
            if song["difficulty"][-1] == 0.0:
                song["difficulty"].pop()
                song["charter"].pop()
            for i in range(len(song["difficulty"])):
                song["difficulty"][i] = str(round(song["difficulty"][i], 1))
            song["songsId"] = song["songsId"][:-2]
            difficulty.append([song["songsId"]] + song["difficulty"])
            table.append((song["songsId"], song["songsName"], song["composer"], song["illustrator"], *song["charter"]))

    progress.check_cancelled()
    logger.debug(difficulty)
    logger.debug(table)
    progress.advance("已解析游戏数据")

    write_csv(os.path.join(output_dir, "difficulty.csv"), difficulty)
    write_csv(os.path.join(output_dir, "info.csv"), table)

    single = []
    illustration = []
    for key in game_information["keyStore"]:
        if key["kindOfKey"] == 0:
            single.append(key["keyName"])
        elif key["kindOfKey"] == 2 and key["keyName"] != "Introduction" and key["keyName"] not in single:
            illustration.append(key["keyName"])

    with open(os.path.join(output_dir, "single.txt"), "w", encoding="utf8") as f:
        for item in single:
            f.write("%s\n" % item)

    with open(os.path.join(output_dir, "illustration.txt"), "w", encoding="utf8") as f:
        for item in illustration:
            f.write("%s\n" % item)
    logger.info(single)
    logger.info(illustration)

    collection_titles = {}
    for item in collections.collectionItems:
        if item.key in collection_titles:
            collection_titles[item.key][1] = item.subIndex
        else:
            collection_titles[item.key] = [item.multiLanguageTitle.chinese, item.subIndex]

    write_csv(
        os.path.join(output_dir, "collection.csv"),
        ([key, value[0], value[1]] for key, value in collection_titles.items()),
    )

    write_csv(
        os.path.join(output_dir, "tmp.csv"),
        ([item.name, item.addressableKey[7:]] for item in collections.avatars),
    )
    with open(os.path.join(output_dir, "avatar.txt"), "w", encoding="utf8") as avatar:
        for item in collections.avatars:
            avatar.write(item.name)
            avatar.write("\n")

    with open(os.path.join(output_dir, "tips.txt"), "w", encoding="utf8") as f:
        for tip in tips.tips[0].tips:
            f.write(tip)
            f.write("\n")
    progress.finish("完成")


def parse_args():
    parser = argparse.ArgumentParser(description="从 Phigros APK 提取游戏信息")
    parser.add_argument("apk", help="Phigros APK 路径")
    parser.add_argument("--version", help="游戏版本号(默认从 APK 文件名识别)")
    return parser.parse_args()


def main():
    args = parse_args()
    version = detect_version(args.apk, args.version)
    logger = init_console_logger()
    logger.info("版本 %s,输出目录 %s" % (version, version_dir(version)))
    try:
        run(args.apk, version, logger)
    except RuntimeError as e:
        # 版本不匹配等可预期的失败:输出清晰错误并以非零码退出
        logger.error(str(e))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
