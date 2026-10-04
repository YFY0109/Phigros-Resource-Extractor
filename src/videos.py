"""从 Phigros APK 提取解锁动画视频(VideoClip → .webm)。

用法:
    python src/videos.py <Phigros APK 路径> [--version X.Y.Z]

视频数据存放在 Unity 数据文件的 .resource 流中(sharedassets*.resource),
由场景中的 VideoPlayer 通过 VideoClip 资产引用;本脚本按 VideoClip 的
m_ExternalResources(m_Source/m_Offset/m_Size)精确切分,输出到
outputs/<版本>/videos/<VideoClip 名>.webm。
"""
import argparse
import os
from io import BytesIO
from zipfile import ZipFile

from UnityPy import Environment

from common import detect_version, load_config, version_dir
from dedupe import DedupeStore, write_file
from log import init_console_logger
from progress import NULL_PROGRESS

DATA_PREFIX = "assets/bin/Data/"


def _read_data(apk, names, base):
    """读取 Data 文件内容(自动拼接 .splitN 拆分文件)。"""
    parts = [n for n in names if n == base or n.startswith(base + ".split")]
    parts.sort(key=lambda n: int(n.rsplit(".split", 1)[1]) if ".split" in n else -1)
    return b"".join(apk.read(n) for n in parts)


def _sharedassets_bases(names):
    """sharedassets*.assets 基名列表(含被 split 拆分的)。"""
    bases = {
        n.rsplit(".split", 1)[0] if ".split" in n else n
        for n in names
        if n.startswith(DATA_PREFIX + "sharedassets") and ".resource" not in n
    }
    return sorted(bases)


def find_video_clips(apk, logger):
    """扫描数据文件中的 VideoClip,返回 [{name, source, offset, size}]。

    3.x 布局:VideoClip 在 sharedassets*.assets 中;
    4.x 布局:对象表合并进 data.unity3d(资源流仍在 sharedassets*.resource)。
    """
    names = apk.namelist()
    bases = _sharedassets_bases(names)
    if not bases and DATA_PREFIX + "data.unity3d" in names:
        bases = [DATA_PREFIX + "data.unity3d"]
    clips = []
    for base in bases:
        try:
            env = Environment()
            env.load_file(BytesIO(_read_data(apk, names, base)), name=base)
        except Exception:
            logger.warning("跳过无法解析的数据文件: %s", base)
            continue
        for obj in env.objects:
            if obj.type.name != "VideoClip":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                logger.warning("VideoClip 解析失败: %s", base)
                continue
            external = tree.get("m_ExternalResources")
            if isinstance(external, dict):
                items = [external]
            elif isinstance(external, list):
                items = [item for item in external if isinstance(item, dict)]
            else:
                items = []
            for item in items:
                clips.append({
                    "name": str(tree.get("m_Name") or "video"),
                    "source": item.get("m_Source"),
                    "offset": item.get("m_Offset") or 0,
                    "size": item.get("m_Size") or 0,
                })
    return clips


def run(apk_path, version, logger, progress=None):
    """提取指定 APK 中的所有解锁动画视频;返回提取数量。"""
    progress = progress or NULL_PROGRESS
    output_dir = os.path.join(version_dir(version), "videos")
    os.makedirs(output_dir, exist_ok=True)

    dedupe_config = load_config().get("dedupe", {})
    store = None
    if dedupe_config.get("enabled", True):
        store = DedupeStore(version, int(dedupe_config.get("sample_bytes", 65536)), logger)

    with ZipFile(apk_path) as apk:
        names = apk.namelist()
        progress.start("扫描解锁动画", total=None)
        clips = find_video_clips(apk, logger)
        progress.start("提取解锁动画", total=len(clips))
        created = 0
        for clip in clips:
            progress.check_cancelled()
            source = clip["source"]
            if not source:
                logger.warning("跳过(无数据来源): %s", clip["name"])
                continue
            try:
                blob = _read_data(apk, names, DATA_PREFIX + source)
                data = blob[clip["offset"]:clip["offset"] + clip["size"]] if clip["size"] else blob[clip["offset"]:]
            except Exception as e:
                logger.warning("视频数据读取失败 %s: %s", clip["name"], e)
                continue
            safe_name = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in clip["name"])
            path = os.path.join(output_dir, safe_name + ".webm")
            if store is not None:
                store.write(path, data)
            else:
                write_file(path, data)
            logger.info("已提取: %s(%.2f MB)", safe_name, len(data) / 1024 / 1024)
            created += 1
            progress.advance(clip["name"])

    if store is not None:
        store.flush()
        store.report()
    progress.finish("共提取 %d 段视频" % created)
    return created


def parse_args():
    parser = argparse.ArgumentParser(description="从 Phigros APK 提取解锁动画视频")
    parser.add_argument("apk", help="Phigros APK 路径")
    parser.add_argument("--version", help="游戏版本号(默认从 APK 读取)")
    return parser.parse_args()


def main():
    args = parse_args()
    version = detect_version(args.apk, args.version)
    logger = init_console_logger()
    logger.info("版本 %s,输出目录 %s" % (version, os.path.join(version_dir(version), "videos")))
    run(args.apk, version, logger)


if __name__ == "__main__":
    main()
