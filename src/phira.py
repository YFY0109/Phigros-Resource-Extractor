"""把 outputs/<版本>/ 下的提取产物打包为 Phira 的 .pez 自制谱文件。

用法:
    python phira.py [--version X.Y.Z]

输入:outputs/<版本>/ 的 info/、charts/、illustrationsLowRes/、music/
输出:outputs/<版本>/phira/<EZ|HD|IN|AT>/*.pez
"""
import argparse
import csv
import os
import shutil
from zipfile import ZipFile, BadZipFile

from common import list_versions, resource_dir, version_dir
from log import init_console_logger
from progress import NULL_PROGRESS

LEVELS = ("EZ", "HD", "IN", "AT")


def parse_args():
    parser = argparse.ArgumentParser(description="把提取产物打包为 Phira 的 .pez 自制谱")
    parser.add_argument("--version", help="要打包的版本(默认取 outputs/ 下最新版本)")
    return parser.parse_args()


def choose_version(override=None):
    versions = list_versions()
    if not versions:
        raise SystemExit("outputs/ 下没有任何版本目录,请先运行 gameInformation.py 与 resource.py")
    if override:
        if override not in versions:
            raise SystemExit("outputs/ 下不存在版本目录:%s" % override)
        return override
    return versions[0]


def load_infos(info_path, logger):
    """读取 info.csv,返回 {歌曲ID: {Name, Composer, Illustrator, Chater}}。"""
    infos = {}
    try:
        with open(info_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                infos[row[0]] = {
                    "Name": row[1],
                    "Composer": row[2],
                    "Illustrator": row[3],
                    "Chater": row[4:],
                }
    except FileNotFoundError:
        raise SystemExit("错误:未找到 %s,请先运行 gameInformation.py" % info_path)
    return infos


def apply_difficulties(infos, difficulty_path, logger):
    """读取 difficulty.csv,为每首歌补充难度列表。"""
    try:
        with open(difficulty_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                if row[0] in infos:
                    infos[row[0]]["difficulty"] = row[1:]
                else:
                    logger.warning("difficulty.csv 中的 ID %s 在 info.csv 中未找到", row[0])
    except FileNotFoundError:
        raise SystemExit("错误:未找到 %s,请先运行 gameInformation.py" % difficulty_path)


def build_pez(version, level, song_id, info, logger):
    """为单个歌曲的单个难度生成 .pez 压缩包(按曲目分目录,与 charts 结构一致)。"""
    level_index = LEVELS.index(level)
    song_dir = os.path.join(version_dir(version), "phira", "%s.0" % song_id)
    os.makedirs(song_dir, exist_ok=True)
    pez_path = os.path.join(song_dir, "%s.pez" % level)
    with ZipFile(pez_path, "x") as pez:
        info_txt_content = (
            "#\n"
            "Name: %s\n" % info["Name"] +
            "Song: %s.ogg\n" % song_id +
            "Picture: %s.png\n" % song_id +
            "Chart: %s.json\n" % song_id +
            "Level: %s Lv.%s\n" % (level, info["difficulty"][level_index]) +
            "Composer: %s\n" % info["Composer"] +
            "Illustrator: %s\n" % info["Illustrator"] +
            "Charter: %s" % info["Chater"][level_index]
        )
        pez.writestr("info.txt", info_txt_content)

        chart_path = os.path.join(resource_dir(version, "chart"), "%s.0" % song_id, "%s.json" % level)
        try:
            pez.write(chart_path, "%s.json" % song_id)
        except FileNotFoundError:
            logger.warning("未找到 %s 的 %s 谱面文件 (%s)", song_id, level, chart_path)

        picture_dir = resource_dir(version, "illustrationLowRes")
        for picture in ("%s.png" % song_id, "%s_%s.png" % (song_id, level)):
            picture_path = os.path.join(picture_dir, picture)
            if os.path.exists(picture_path):
                pez.write(picture_path, "%s.png" % song_id)
                break
        else:
            logger.warning("未找到 %s 的曲绘文件", song_id)

        music_path = os.path.join(resource_dir(version, "music"), "%s.ogg" % song_id)
        try:
            pez.write(music_path, "%s.ogg" % song_id)
        except FileNotFoundError:
            logger.warning("未找到 %s 的音乐文件 (%s)", song_id, music_path)


def run(version, logger, progress=None):
    """执行指定版本的完整打包流程,返回生成的 pez 数量。"""
    progress = progress or NULL_PROGRESS
    logger.info("打包版本 %s" % version)

    infos = load_infos(os.path.join(version_dir(version), "info", "info.csv"), logger)
    apply_difficulties(infos, os.path.join(version_dir(version), "info", "difficulty.csv"), logger)

    # 重建打包输出目录(按曲目分目录,与 charts 结构一致)
    phira_root = os.path.join(version_dir(version), "phira")
    try:
        shutil.rmtree(phira_root, True)
        os.makedirs(phira_root, exist_ok=True)
    except Exception as e:
        logger.error("创建或删除目录时出错 - %s", e)
        raise SystemExit(1)

    progress.start("打包 Phira 自制谱", total=len(infos))
    created = 0
    for song_id, info in infos.items():
        try:
            logger.info("正在处理:%s,作曲者:%s", info["Name"], info["Composer"])
            for level_index in range(len(info.get("difficulty", []))):
                level = LEVELS[level_index]
                try:
                    build_pez(version, level, song_id, info, logger)
                    created += 1
                except BadZipFile as e:
                    logger.error("创建 .pez 文件时出错 - %s", e)
                except Exception as e:
                    logger.error("写入 .pez 文件时出错 - %s", e)
        except KeyError as e:
            logger.error("ID %s 缺少必要的键 %s", song_id, e)
        except Exception as e:
            logger.error("处理 ID %s 时发生意外错误 - %s", song_id, e)
        progress.advance(info.get("Name", song_id))
    progress.finish("共生成 %d 个 pez" % created)
    return created


def main():
    args = parse_args()
    version = choose_version(args.version)
    logger = init_console_logger()
    run(version, logger)


if __name__ == "__main__":
    main()
