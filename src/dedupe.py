"""跨版本文件去重:对提取产物计算部分内容摘要(文件大小 + 头/尾采样),
与 outputs/ 下其他版本的同名文件比对;内容一致则创建硬链接以节省空间,
系统不支持硬链接(跨卷、文件系统限制等)时自动回退为普通写入。"""
import hashlib
import os
from io import BytesIO

from common import list_versions, version_dir


def _build_digest(size, head, tail):
    digest = hashlib.blake2b(digest_size=16)
    digest.update(b"%d" % size)
    digest.update(head)
    digest.update(tail)
    return digest.hexdigest()


def buffer_size(data):
    """内存数据的字节数(BytesIO 或 bytes)。"""
    view = data.getbuffer() if isinstance(data, BytesIO) else memoryview(data)
    return len(view)


def digest_buffer(data, sample_bytes):
    """对内存中的数据(BytesIO 或 bytes)计算部分摘要。"""
    view = data.getbuffer() if isinstance(data, BytesIO) else memoryview(data)
    size = len(view)
    head = bytes(view[:sample_bytes])
    tail = bytes(view[max(size - sample_bytes, 0):]) if size > sample_bytes else b""
    return _build_digest(size, head, tail)


def digest_file(path, sample_bytes):
    """对磁盘文件计算部分摘要(只读取文件头/尾各 sample_bytes 字节)。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(min(sample_bytes, size))
        tail = b""
        if size > sample_bytes:
            f.seek(size - sample_bytes)
            tail = f.read(sample_bytes)
    return _build_digest(size, head, tail)


def write_file(path, data):
    """普通写入(BytesIO 或 bytes)。"""
    with open(path, "wb") as f:
        if isinstance(data, BytesIO):
            f.write(data.getbuffer())
        else:
            f.write(data)


class DedupeStore:
    """把新文件与 outputs/ 下其他版本的同名文件对比后写入。

    内容一致时尝试创建硬链接(多个版本共享同一份数据块);
    创建失败(如跨卷、文件系统不支持)或不一致时回退为普通写入。
    """

    def __init__(self, current_version, sample_bytes, logger):
        self._base = version_dir(current_version)
        self._sample_bytes = sample_bytes
        self._logger = logger
        self._other_versions = [v for v in list_versions() if v != current_version]
        self.linked_files = 0
        self.linked_bytes = 0
        self.written_files = 0

    def write(self, path, data):
        source = self._find_duplicate(path, data, buffer_size(data))
        if source is not None and self._try_link(source, path):
            self.linked_files += 1
            self.linked_bytes += os.path.getsize(source)
            return
        write_file(path, data)
        self.written_files += 1

    def _find_duplicate(self, path, data, size):
        """在其它版本中查找内容一致的对应文件,找不到返回 None。"""
        rel = os.path.relpath(path, self._base)
        if rel.startswith(".."):
            return None
        new_digest = digest_buffer(data, self._sample_bytes)
        for version in self._other_versions:
            candidate = os.path.join(version_dir(version), rel)
            try:
                # 大小预筛:大小不同直接跳过,省去读取文件头尾计算摘要
                if os.path.getsize(candidate) != size:
                    continue
            except OSError:
                continue
            try:
                if digest_file(candidate, self._sample_bytes) == new_digest:
                    return candidate
            except OSError:
                continue
        return None

    @staticmethod
    def _try_link(source, target):
        """尝试创建硬链接;失败返回 False(由调用方回退为写入)。"""
        try:
            if os.path.exists(target):
                os.remove(target)
            os.link(source, target)
            return True
        except OSError:
            return False

    def report(self):
        if self.linked_files:
            self._logger.info(
                "去重完成:硬链接 %d 个文件(节省约 %.1f MB),其余 %d 个正常写入",
                self.linked_files, self.linked_bytes / 1024 / 1024, self.written_files,
            )
        else:
            self._logger.info("去重完成:未发现可复用的重复文件,%d 个文件正常写入", self.written_files)
