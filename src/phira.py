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

开启 config.json 的 `phira.generate_video`(默认开启)时,会为对照表内的曲目额外生成
`<难度>_video.pez`(info.yml 的 `unlockVideo` 字段指向包内视频;多段视频用 ffmpeg 拼接)。
环境缺少 ffmpeg 时提示下载并跳过全部带视频谱面;其余 info.yml 必填字段
(previewStart/aspectRatio/backgroundDim/lineLength/offset/tags/intro/holdPartialCover)
可在 config.json 的 `phira` 段调整。
"""
import argparse
import csv
import os
import shutil
import subprocess
import tempfile
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

# 解锁视频对照表:曲目 songsId 第一段 -> 视频片段基名列表(多个片段按顺序拼接);
# 值为 dict 时按难度取片段。视频取自 outputs/<版本>/videos/(扩展名自动匹配)。
# 与谱面无关的视频(AfterDeductionVideo、QD、ToPhase2 等)不在表内。
UNLOCK_VIDEO_MAP = {
    "Spasmodic": ["Spas_Unlock"],
    "Igallta": ["Iga_Loop", "Iga_Main"],
    "Rrharil": ["TimeReverse_Video", "Rrharil_Unlock"],
    "DESTRUCTION321": ["321_Unlock_Final_Plus"],
    "DistortedFate": ["DF_Touch2Start", "DF_Unlock"],
    "EntrancetotheChaos": ["Entrance_to_the_Chaos_Intro_D1_Compressed"],
    "ExoplanetaryMirage": ["Exoplanetary_Mirage_Intro_D1_Compressed"],
    "DesultorySignals": {
        "EZ": ["ds_unlockIntro_Sound", "ds_unlockDifficulties", "ds_unlockEZ"],
        "HD": ["ds_unlockIntro_Sound", "ds_unlockDifficulties", "ds_unlockHD"],
        "IN": ["ds_unlockIntro_Sound", "ds_unlockDifficulties", "ds_unlockIN"],
        "AT": ["ds_unlockIntro_Sound", "ds_unlockDifficulties", "ds_unlockAT"],
    },
}

# 视频文件候选扩展名(提取产物按内容命名)
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".mkv")

# info.yml 其余必填字段的默认值(对应 config.json 的 phira 段)
CHART_FIELD_DEFAULTS = {
    "preview_start": 0.0,
    "aspect_ratio": 1.7777778,
    "background_dim": 0.6,
    "line_length": 6.0,
    "offset": 0.0,
    "tags": (),
    "intro": "",
    "hold_partial_cover": False,
}


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


def _yaml_tags(tags):
    """YAML 流式字符串数组,如 ['a', 'b'] 或 []。"""
    return "[" + ", ".join(_yaml_quote(item) for item in tags) + "]"


def _yaml_number(value):
    """数字统一为浮点表示,保证输出稳定(便于跨版本去重)。"""
    return repr(float(value))


def _chart_extra_fields(phira_config, logger):
    """从 config.json 的 phira.info 子段读取 info.yml 其余必填字段;非法值回退默认。"""
    info_config = phira_config.get("info", {})
    if not isinstance(info_config, dict):
        logger.warning("config.json 中 phira.info 不是对象,按默认值处理")
        info_config = {}

    def number(key):
        default = CHART_FIELD_DEFAULTS[key]
        try:
            return float(info_config.get(key, default))
        except (TypeError, ValueError):
            logger.warning("config.json 中 phira.info.%s 不是数字,按 %s 处理", key, default)
            return default

    tags = info_config.get("tags", CHART_FIELD_DEFAULTS["tags"])
    if not isinstance(tags, list):
        logger.warning("config.json 中 phira.info.tags 不是列表,按空列表处理")
        tags = []

    return {
        "preview_start": number("preview_start"),
        "aspect_ratio": number("aspect_ratio"),
        "background_dim": number("background_dim"),
        "line_length": number("line_length"),
        "offset": number("offset"),
        "tags": [str(item) for item in tags],
        "intro": str(info_config.get("intro", CHART_FIELD_DEFAULTS["intro"]) or ""),
        "hold_partial_cover": bool(info_config.get("hold_partial_cover", CHART_FIELD_DEFAULTS["hold_partial_cover"])),
    }


def _video_sources_for(song_id, level):
    """返回该曲目难度对应的解锁视频片段基名列表;无映射返回 None。"""
    sources = UNLOCK_VIDEO_MAP.get(song_id.split(".")[0])
    if isinstance(sources, dict):
        return sources.get(level)
    return sources


def _find_video(videos_dir, base):
    """在视频目录中按基名查找视频文件(扩展名自动匹配),找不到返回 None。"""
    for ext in VIDEO_EXTENSIONS:
        path = os.path.join(videos_dir, base + ext)
        if os.path.isfile(path):
            return path
    return None


def _video_size(path):
    """用 ffprobe 读取视频流尺寸 (宽, 高);失败返回 None。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
            capture_output=True, text=True)
        width, height = result.stdout.strip().split("x")
        return (int(width), int(height))
    except Exception:
        return None


def _concat_videos(paths, logger):
    """用 ffmpeg 拼接视频片段;失败返回 None。

    各片段分辨率一致时用 `-c copy` 无损拼接;不一致时以最大片段尺寸为画布,
    其余片段按比例缩放后居中补黑边(#000)再统一重编码(如 ds_unlock* 的
    16:9 开场 + 4:3 难度片段)。
    """
    sizes = [_video_size(path) for path in paths]
    if all(size and size == sizes[0] for size in sizes):
        return _concat_videos_copy(paths, logger)
    return _concat_videos_reencode(paths, sizes, logger)


def _concat_videos_copy(paths, logger):
    """按顺序无损拼接(要求分辨率一致):ffmpeg concat demuxer + -c copy。"""
    temp_dir = tempfile.mkdtemp(prefix="phigros_concat_")
    try:
        list_path = os.path.join(temp_dir, "concat.txt")
        with open(list_path, "w", encoding="utf8") as f:
            for path in paths:
                escaped = os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")
                f.write("file '%s'\n" % escaped)
        out_path = os.path.join(temp_dir, "concat%s" % os.path.splitext(paths[0])[1])
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path]
        return _run_ffmpeg(command, out_path, logger)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _has_audio(path):
    """ffprobe 判断是否存在音频流。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True)
        return bool(result.stdout.strip())
    except Exception:
        return True  # 探测失败按有音频处理,交由 ffmpeg 报错


def _media_duration(path):
    """ffprobe 读取媒体时长(秒);失败返回 None。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True)
        return float(result.stdout.strip())
    except Exception:
        return None


def _concat_videos_reencode(paths, sizes, logger):
    """以最大片段尺寸为画布,其余片段缩放后居中补黑边,统一重编码拼接。

    没有音频流的片段(如 ds_unlockDifficulties)会生成等长静音后一并拼接。
    """
    known = [size for size in sizes if size]
    if not known:
        logger.error("无法读取视频片段分辨率,拼接失败:%s",
                     "、".join(os.path.basename(path) for path in paths))
        return None
    canvas = max(known, key=lambda size: size[0] * size[1])
    temp_dir = tempfile.mkdtemp(prefix="phigros_concat_")
    try:
        out_path = os.path.join(temp_dir, "concat%s" % os.path.splitext(paths[0])[1])
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for path in paths:
            command += ["-i", path]
        audio_inputs = []
        next_index = len(paths)
        for position, path in enumerate(paths):
            if _has_audio(path):
                audio_inputs.append(position)
                continue
            duration = _media_duration(path)
            if duration is None:
                logger.error("无法读取视频时长,拼接失败:%s", os.path.basename(path))
                return None
            command += ["-f", "lavfi", "-t", "%.3f" % duration,
                        "-i", "anullsrc=r=48000:cl=stereo"]
            audio_inputs.append(next_index)
            next_index += 1
        filters = []
        for index in range(len(paths)):
            filters.append(
                "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease,"
                "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p[v%d]" % (
                    index, canvas[0], canvas[1], canvas[0], canvas[1], index))
            filters.append(
                "[%d:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a%d]" % (
                    audio_inputs[index], index))
        concat_inputs = "".join("[v%d][a%d]" % (index, index) for index in range(len(paths)))
        filter_complex = ";".join(filters) + ";" + concat_inputs + "concat=n=%d:v=1:a=1[v][a]" % len(paths)
        command += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"]
        if os.path.splitext(out_path)[1] == ".webm":
            command += ["-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0", "-c:a", "libopus"]
        else:
            command += ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        command += [out_path]
        return _run_ffmpeg(command, out_path, logger)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_ffmpeg(command, out_path, logger):
    """执行 ffmpeg 命令并读回输出文件;失败记录日志并返回 None。"""
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        logger.error("ffmpeg 拼接失败:%s", result.stderr.decode("utf8", "replace").strip()[:300])
        return None
    with open(out_path, "rb") as f:
        return f.read()


def _build_unlock_video(song_id, level, videos_dir, cache, logger):
    """按对照表取出/拼接该曲目难度的解锁视频,返回 (包内文件名, bytes);无映射或失败返回 None。"""
    sources = _video_sources_for(song_id, level)
    if not sources:
        return None
    key = tuple(sources)
    if key not in cache:
        paths = []
        for base in sources:
            path = _find_video(videos_dir, base)
            if path is None:
                logger.warning("未找到解锁视频片段 %s(曲目 %s),跳过该曲目的带视频谱面", base, song_id)
                break
            paths.append(path)
        if len(paths) == len(sources):
            if len(paths) == 1:
                with open(paths[0], "rb") as f:
                    data = f.read()
            else:
                data = _concat_videos(paths, logger)
            if data is not None:
                name = "%s_unlock%s" % (song_id, os.path.splitext(paths[0])[1])
                cache[key] = (name, data)
        cache.setdefault(key, None)
    return cache[key]


def build_pez_bytes(version, level, song_id, info, logger, level_index=None, info_format="yml",
                    extra_fields=None, video=None):
    """在内存中构建单个难度的 .pez,返回 bytes。

    所有 zip 条目使用固定时间戳,使内容相同的 pez 字节级可复现(便于跨版本去重)。
    level_index=None 表示 SP 等未登记进信息表的难度:难度标识用 "SP Lv.?"
    (定数视为 0.0);谱师等未知信息用 UK 代替。
    info_format="yml"(默认)写 Phira 官方 info.yml(含独立 difficulty 定数);
    "txt" 写 RPE 风格的 info.txt(info.txt 无定数字段,Phira 只能从 level 推断,小数会失真)。
    extra_fields 为 info.yml 其余必填字段的取值(默认 CHART_FIELD_DEFAULTS);
    video 为 (包内文件名, bytes),提供时写入包内并填 unlockVideo(仅 yml 生效)。
    """
    if info_format == "txt":
        video = None  # info.txt 没有 unlockVideo 字段
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
            extra = extra_fields if extra_fields is not None else CHART_FIELD_DEFAULTS
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
                ("unlockVideo: %s\n" % _yaml_quote(video[0]) if video is not None else "") +
                "previewStart: %s\n" % _yaml_number(extra["preview_start"]) +
                "aspectRatio: %s\n" % _yaml_number(extra["aspect_ratio"]) +
                "backgroundDim: %s\n" % _yaml_number(extra["background_dim"]) +
                "lineLength: %s\n" % _yaml_number(extra["line_length"]) +
                "offset: %s\n" % _yaml_number(extra["offset"]) +
                "tags: %s\n" % _yaml_tags(extra["tags"]) +
                "intro: %s\n" % _yaml_quote(extra["intro"]) +
                "holdPartialCover: %s\n" % ("true" if extra["hold_partial_cover"] else "false")
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

        if video is not None:
            pez.writestr(ZipInfo(video[0], date_time=FIXED_ZIP_TIME), video[1])

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
    phira_config = config.get("phira", {})
    info_format = str(phira_config.get("info_format", "yml")).strip().lower()
    if info_format == "yaml":
        info_format = "yml"
    if info_format not in ("yml", "txt"):
        logger.warning("config.json 中 phira.info_format=%r 无法识别,按 yml 处理", info_format)
        info_format = "yml"
    extra_fields = _chart_extra_fields(phira_config, logger)
    generate_video = bool(phira_config.get("generate_video", True))
    if generate_video and info_format != "yml":
        logger.warning("info.txt 格式不支持 unlockVideo 字段,已跳过带视频的谱面(phira.info_format 设为 yml 可生成)")
        generate_video = False
    if generate_video and not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        logger.warning("未找到 ffmpeg/ffprobe,已跳过全部带解锁视频的谱面;请安装 ffmpeg 后重试:https://ffmpeg.org/download.html")
        generate_video = False

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

    videos_dir = os.path.join(version_dir(version), "videos")
    created = 0
    for song_id, info in infos.items():
        progress.check_cancelled()
        try:
            logger.info("正在处理:%s,作曲者:%s", info["Name"], info["Composer"])
            video_cache = {}
            for level_index, value in enumerate(info.get("difficulty", [])):
                if not value:
                    continue  # 空槽位(如无 AT/Legacy)
                level = LEVELS[level_index]
                song_dir = os.path.join(phira_root, "%s.0" % song_id)
                try:
                    data = build_pez_bytes(version, level, song_id, info, logger, level_index,
                                           info_format, extra_fields)
                    os.makedirs(song_dir, exist_ok=True)
                    _write_pez(store, os.path.join(song_dir, "%s.pez" % level), data)
                    created += 1
                except BadZipFile as e:
                    logger.error("创建 .pez 文件时出错 - %s", e)
                    continue
                except Exception as e:
                    logger.error("写入 .pez 文件时出错 - %s", e)
                    continue
                if generate_video:
                    video = _build_unlock_video(song_id, level, videos_dir, video_cache, logger)
                    if video is not None:
                        try:
                            data = build_pez_bytes(version, level, song_id, info, logger, level_index,
                                                   info_format, extra_fields, video)
                            _write_pez(store, os.path.join(song_dir, "%s_video.pez" % level), data)
                            created += 1
                        except BadZipFile as e:
                            logger.error("创建 .pez 文件时出错 - %s", e)
                        except Exception as e:
                            logger.error("写入 .pez 文件时出错 - %s", e)
            # SP 谱面:不登记在信息表中(如 4.0.1 的 Message),以谱面文件是否存在判断
            sp_chart = os.path.join(resource_dir(version, "chart"), "%s.0" % song_id, "SP.json")
            if os.path.isfile(sp_chart):
                try:
                    data = build_pez_bytes(version, "SP", song_id, info, logger, info_format=info_format,
                                           extra_fields=extra_fields)
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
