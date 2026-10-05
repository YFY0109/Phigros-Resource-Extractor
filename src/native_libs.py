"""fsb5 音乐提取所需本地动态库(ogg/vorbis)的跨平台解析。

fsb5 在导入其 vorbis 模块时,用 `ctypes.util.find_library` 查找系统库,
找不到时只在**当前工作目录**查找 `lib<name>.dll`(Windows 命名)。这在
Linux 上不够用:动态库名是 `lib<name>.so` / `lib<name>.so.N`,而且不一定
装在系统默认搜索路径下。

本模块在导入 fsb5 之前接管 `ctypes.util.find_library`,按以下顺序解析:

1. 系统库(交给原始 find_library,覆盖 Linux 的 .so 与 Windows 的 .dll);
2. 当前工作目录下的 `lib<name>.so*`(Linux)/ `.dylib`(macOS)/ `.dll`;
3. 仓库根目录(本文件所在目录的上一级)下的同名库文件。

这样既能在已安装 libogg/libvorbis 的 Linux 上直接工作,也允许把库文件
放到仓库根目录离线随包携带。找不到时给出可直接照做的中文安装提示。
"""
import ctypes.util
import glob
import os
import sys

# fsb5 需要的库:libvorbis / libvorbisenc(编码控制)/ libogg
LIB_NAMES = ("vorbis", "vorbisenc", "ogg")

_ORIGINAL_FIND_LIBRARY = ctypes.util.find_library
_PATCHED = False


def _candidate_patterns(name):
    """各平台下本地库文件的候选文件名(按优先级排列)。"""
    if sys.platform == "win32":
        return ["lib%s.dll" % name, "%s.dll" % name]
    if sys.platform == "darwin":
        return ["lib%s.dylib" % name, "lib%s.*.dylib" % name]
    return ["lib%s.so" % name, "lib%s.so.*" % name]


def _search_dirs():
    """本地库搜索目录:当前工作目录 + 仓库根目录。"""
    dirs = [os.getcwd()]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in dirs:
        dirs.append(repo_root)
    return dirs


def find_library(name):
    """查找本地库:先系统库,再当前目录/仓库根目录下的库文件;找不到返回 None。"""
    found = _ORIGINAL_FIND_LIBRARY(name)
    if found or name not in LIB_NAMES:
        return found
    for directory in _search_dirs():
        for pattern in _candidate_patterns(name):
            matches = sorted(glob.glob(os.path.join(directory, pattern)))
            if matches:
                return matches[-1]
    return None


def ensure_patched():
    """把上述查找逻辑接入 fsb5 依赖的 ctypes.util.find_library(幂等)。"""
    global _PATCHED
    if not _PATCHED:
        ctypes.util.find_library = find_library
        _PATCHED = True


def _has_encode_symbol(lib_path):
    """vorbis 库是否带编码符号(Windows 官方 libvorbis.dll 一并包含 vorbisenc 的函数)。"""
    try:
        ctypes.CDLL(lib_path).vorbis_encode_setup_vbr
        return True
    except (OSError, AttributeError):
        return False


def missing_libraries():
    """返回当前环境找不到的库名列表。

    与 fsb5 的加载方式(vorbis.py)保持一致:`vorbis`/`ogg` 必需;
    `vorbisenc` 缺失时会回退到 `vorbis`,因此单独缺 vorbisenc 不算缺失,
    仅当 `vorbis` 也不带编码符号时才算缺失。
    """
    missing = []
    vorbis = find_library("vorbis")
    if vorbis is None:
        missing.append("vorbis")
    if find_library("vorbisenc") is None and not (vorbis and _has_encode_symbol(vorbis)):
        missing.append("vorbisenc")
    if find_library("ogg") is None:
        missing.append("ogg")
    return missing


def install_hint():
    """按平台返回安装/放置本地库的建议。"""
    if sys.platform == "win32":
        return (
            "请把 libogg.dll、libvorbis.dll 放到仓库根目录(随仓库提供),"
            "并安装 MSVCR120.dll(VC++ 2013 运行库)"
        )
    if sys.platform == "darwin":
        return "请安装 libogg 与 libvorbis(如:brew install libogg libvorbis)"
    return (
        "请安装系统库 libogg 与 libvorbis(需包含 libvorbisenc),"
        "Debian/Ubuntu: sudo apt install libogg0 libvorbis0a libvorbisenc2;"
        "Fedora: sudo dnf install libogg libvorbis;"
        "Arch: sudo pacman -S libogg libvorbis"
    )


def check_available():
    """音乐提取前检查本地库;缺失时抛出带安装建议的中文错误。"""
    missing = missing_libraries()
    if not missing:
        return
    raise RuntimeError(
        "缺少音乐提取所需的本地库 %s。%s" % ("、".join(missing), install_hint())
    )
