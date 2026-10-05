"""把 outputs/<版本>/ 下的提取产物打包为 Phira 的 .pez 自制谱文件。

用法:
    python phira.py [--version X.Y.Z]

输入:outputs/<版本>/ 的 info/、charts/、illustrationsLowRes/、music/
输出:outputs/<版本>/phira/<曲目>.0/<难度>.pez

SP 谱面(如 4.0.1 的 Message)不登记在信息表中,以谱面文件 charts/<曲目>.0/SP.json
是否存在判断;难度标识固定为 `SP Lv.?`(定数视为 0.0),谱师等未知信息用 UK 代替。
Legacy 旧谱(如 Aleph-0、ESM)取 difficulty.csv 中对应槽位的实际定数,标识为 `Legacy Lv.定数`。

谱面信息文件默认写 `info.yml`(Phira 官方格式,difficulty 为独立定数字段);
可用 config.json 的 `phira.info_format` 切换为 RPE 风格的 `info.txt`——注意 info.txt
没有定数字段,Phira 只会截取 `level` 字符串末尾的连续数字(如 `AT Lv.17.9` 会读成 9.0)。
"""
import argparse
import csv
import os
import shutil
from io import BytesIO
from zipfile import ZipFile, ZipInfo, BadZipFile

from common import list_versions, load_config, resource_dir, version_dir
from dedupe import DedupeStore, write_file
from log import init_console_logger
from progress import NULL_PROGRESS

# 难度槽位,与 difficulty.csv 的值列一一对应(空字符串表示该槽位无谱面)
LEVELS = ("EZ", "HD", "IN", "AT", "Legacy")

# zip 条目固定时间戳:保证内容相同的 pez 字节级可复现,从而参与跨版本硬链接去重
FIXED_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


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


def _yaml_quote(value):
    """把字符串转为安全的 YAML 单引号标量(单引号写两遍转义)。"""
    return "'%s'" % str(value).replace("'", "''")


def build_pez_bytes(version, level, song_id, info, logger, level_index=None, info_format="yml"):
    """在内存中构建单个难度的 .pez,返回 bytes。

    所有 zip 条目使用固定时间戳,使内容相同的 pez 字节级可复现(便于跨版本去重)。
    level_index=None 表示 SP 等未登记进信息表的难度:难度标识用 "SP Lv.?"
    (定数视为 0.0);谱师等未知信息用 UK 代替。
    info_format="yml"(默认)写 Phira 官方 info.yml(含独立 difficulty 定数);
    "txt" 写 RPE 风格的 info.txt(info.txt 无定数字段,Phira 只能从 level 推断,小数会失真)。
    """
    if level_index is None:
        difficulty_text = "0.0"
        level_text = "%s Lv.?" % level
        charter = "UK"
    else:
        difficulty_text = str(info["difficulty"][level_index])
        level_text = "%s Lv.%s" % (level, difficulty_text)
        charters = info.get("Chater") or []
        charter = (charters[level_index] if level_index < len(charters) else "") or "UK"
    name = info["Name"] or "UK"
    composer = info["Composer"] or "UK"
    illustrator = info["Illustrator"] or "UK"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as pez:
        if info_format == "txt":
            info_content = (
                "#\n"
                "Name: %s\n" % name +
                "Song: %s.ogg\n" % song_id +
                "Picture: %s.png\n" % song_id +
                "Chart: %s.json\n" % song_id +
                "Level: %s\n" % level_text +
                "Composer: %s\n" % composer +
                "Illustrator: %s\n" % illustrator +
                "Charter: %s" % charter
            )
            pez.writestr(ZipInfo("info.txt", date_time=FIXED_ZIP_TIME), info_content)
        else:
            info_content = (
                "name: %s\n" % _yaml_quote(name) +
                "difficulty: %s\n" % difficulty_text +
                "level: %s\n" % _yaml_quote(level_text) +
                "charter: %s\n" % _yaml_quote(charter) +
                "composer: %s\n" % _yaml_quote(composer) +
                "illustrator: %s\n" % _yaml_quote(illustrator) +
                "chart: %s\n" % _yaml_quote("%s.json" % song_id) +
                "music: %s\n" % _yaml_quote("%s.ogg" % song_id) +
                "illustration: %s\n" % _yaml_quote("%s.png" % song_id) +
                # 其余必需字段先按 Phira 默认值填全,便于其它工具读取完整信息
                "previewStart: 0.0\n" +
                "aspectRatio: 1.7777778\n" +
                "backgroundDim: 0.6\n" +
                "lineLength: 6.0\n" +
                "offset: 0.0\n" +
                "tags: []\n" +
                "intro: ''\n" +
                "holdPartialCover: false\n"
            )
            pez.writestr(ZipInfo("info.yml", date_time=FIXED_ZIP_TIME), info_content)

        chart_path = os.path.join(resource_dir(version, "chart"), "%s.0" % song_id, "%s.json" % level)
        try:
            with open(chart_path, "rb") as f:
                chart_data = f.read()
            pez.writestr(ZipInfo("%s.json" % song_id, date_time=FIXED_ZIP_TIME), chart_data)
        except FileNotFoundError:
            logger.warning("未找到 %s 的 %s 谱面文件 (%s)", song_id, level, chart_path)

        picture_dir = resource_dir(version, "illustrationLowRes")
        for picture in ("%s.png" % song_id, "%s_%s.png" % (song_id, level)):
            picture_path = os.path.join(picture_dir, picture)
            if os.path.exists(picture_path):
                with open(picture_path, "rb") as f:
                    picture_data = f.read()
                pez.writestr(ZipInfo("%s.png" % song_id, date_time=FIXED_ZIP_TIME), picture_data)
                break
        else:
            logger.warning("未找到 %s 的曲绘文件", song_id)

        music_path = os.path.join(resource_dir(version, "music"), "%s.ogg" % song_id)
        try:
            with open(music_path, "rb") as f:
                music_data = f.read()
            pez.writestr(ZipInfo("%s.ogg" % song_id, date_time=FIXED_ZIP_TIME), music_data)
        except FileNotFoundError:
            logger.warning("未找到 %s 的音乐文件 (%s)", song_id, music_path)

    return buffer.getvalue()


def _write_pez(store, pez_path, data):
    """写入一个 pez 文件(去重开启时经 DedupeStore 处理)。"""
    if store is not None:
        store.write(pez_path, data)
    else:
        write_file(pez_path, data)


def run(version, logger, progress=None):
    """执行指定版本的完整打包流程,返回生成的 pez 数量。"""
    progress = progress or NULL_PROGRESS
    logger.info("打包版本 %s" % version)

    config = load_config()
    info_format = str(config.get("phira", {}).get("info_format", "yml")).strip().lower()
    if info_format == "yaml":
        info_format = "yml"
    if info_format not in ("yml", "txt"):
        logger.warning("config.json 中 phira.info_format=%r 无法识别,按 yml 处理", info_format)
        info_format = "yml"

    infos = load_infos(os.path.join(version_dir(version), "info", "info.csv"), logger)
    apply_difficulties(infos, os.path.join(version_dir(version), "info", "difficulty.csv"), logger)

    # 先启动进度(重建输出目录可能耗时较长),再重建打包输出目录
    progress.start("打包 Phira 自制谱", total=len(infos))
    phira_root = os.path.join(version_dir(version), "phira")
    try:
        shutil.rmtree(phira_root, True)
        if os.path.isdir(phira_root):
            raise OSError("输出目录无法完整清理,文件可能正被其它程序占用(关闭后重试)")
        os.makedirs(phira_root, exist_ok=True)
    except Exception as e:
        logger.error("创建或删除目录时出错 - %s", e)
        raise SystemExit(1)

    dedupe_config = config.get("dedupe", {})
    store = None
    if dedupe_config.get("enabled", True):
        store = DedupeStore(version, int(dedupe_config.get("sample_bytes", 65536)), logger)

    created = 0
    for song_id, info in infos.items():
        progress.check_cancelled()
        try:
            logger.info("正在处理:%s,作曲者:%s", info["Name"], info["Composer"])
            for level_index, value in enumerate(info.get("difficulty", [])):
                if not value:
                    continue  # 空槽位(如无 AT/Legacy)
                level = LEVELS[level_index]
                try:
                    data = build_pez_bytes(version, level, song_id, info, logger, level_index, info_format)
                    song_dir = os.path.join(phira_root, "%s.0" % song_id)
                    os.makedirs(song_dir, exist_ok=True)
                    _write_pez(store, os.path.join(song_dir, "%s.pez" % level), data)
                    created += 1
                except BadZipFile as e:
                    logger.error("创建 .pez 文件时出错 - %s", e)
                except Exception as e:
                    logger.error("写入 .pez 文件时出错 - %s", e)
            # SP 谱面:不登记在信息表中(如 4.0.1 的 Message),以谱面文件是否存在判断
            sp_chart = os.path.join(resource_dir(version, "chart"), "%s.0" % song_id, "SP.json")
            if os.path.isfile(sp_chart):
                try:
                    data = build_pez_bytes(version, "SP", song_id, info, logger, info_format=info_format)
                    song_dir = os.path.join(phira_root, "%s.0" % song_id)
                    os.makedirs(song_dir, exist_ok=True)
                    _write_pez(store, os.path.join(song_dir, "SP.pez"), data)
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
    if store is not None:
        store.flush()
        store.report()
    progress.finish("共生成 %d 个 pez" % created)
    return created


def main():
    args = parse_args()
    version = choose_version(args.version)
    logger = init_console_logger()
    run(version, logger)


if __name__ == "__main__":
    main()
