"""跨版本文件去重:对新提取的文件计算部分内容摘要(文件大小 + 头/尾采样),
与 outputs/ 下其他版本的同名文件比对;内容一致则创建硬链接以节省空间,
系统不支持硬链接(跨卷、文件系统限制等)时自动回退为普通写入。

每个版本目录内维护 .dedupe.json 摘要缓存(相对路径 -> "大小:摘要"):
对比旧版本时优先查缓存,未命中才读取文件计算,并把结果补写回缓存,
避免版本增多后反复读取旧文件重新计算摘要。
"""
import hashlib
import json
import os
from io import BytesIO

from common import list_versions, version_dir

# 摘要缓存文件名(存放于各版本目录内)
MANIFEST_NAME = ".dedupe.json"


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

    摘要缓存在各版本目录的 .dedupe.json 中:
    - 提取结束时记录本版本所有输出文件的摘要;
    - 对比旧版本时优先查缓存,未命中才读取文件计算并补记,下次即可直接命中。
    """

    def __init__(self, current_version, sample_bytes, logger):
        self._current_version = current_version
        self._base = version_dir(current_version)
        self._sample_bytes = sample_bytes
        self._logger = logger
        self._other_versions = [v for v in list_versions() if v != current_version]
        # version -> {相对路径: "大小:摘要"} 或 None(缓存不可用)
        self._catalogs = {}
        # version -> 本次新计算出的待回写条目
        self._pending = {}
        # 本版本输出文件的摘要
        self._new_entries = {}
        self.linked_files = 0
        self.linked_bytes = 0
        self.written_files = 0
        self.cache_compared = 0
        self.cache_computes = 0

    def write(self, path, data):
        size = buffer_size(data)
        digest = digest_buffer(data, self._sample_bytes)
        rel = self._rel_key(path)
        if rel is not None:
            self._new_entries[rel] = "%d:%s" % (size, digest)
        source = self._find_duplicate(rel, size, digest)
        if source is not None and self._try_link(source, path):
            self.linked_files += 1
            self.linked_bytes += os.path.getsize(source)
            return
        write_file(path, data)
        self.written_files += 1

    def _rel_key(self, path):
        """输出路径相对当前版本目录的键(统一用 / 分隔);不在目录内时返回 None。"""
        rel = os.path.relpath(path, self._base)
        if rel.startswith(".."):
            return None
        return rel.replace(os.sep, "/")

    def _find_duplicate(self, rel, size, digest):
        """在其它版本中查找内容一致的对应文件,找不到返回 None。"""
        if rel is None:
            return None
        wanted = "%d:%s" % (size, digest)
        for version in self._other_versions:
            catalog = self._load_catalog(version)
            if catalog is not None and rel in catalog:
                self.cache_compared += 1
                if catalog[rel] != wanted:
                    continue
                candidate = self._candidate_path(version, rel)
                if os.path.isfile(candidate):
                    return candidate
                continue  # 缓存过期(文件已不存在),检查其他版本
            # 缓存未命中:实时读取计算摘要,并补记以待回写
            candidate = self._candidate_path(version, rel)
            try:
                # 大小预筛:大小不同直接跳过,省去读取文件头尾计算摘要
                if os.path.getsize(candidate) != size:
                    continue
            except OSError:
                continue
            try:
                actual = digest_file(candidate, self._sample_bytes)
            except OSError:
                continue
            self.cache_computes += 1
            self._pending.setdefault(version, {})[rel] = "%d:%s" % (size, actual)
            if actual == digest:
                return candidate
        return None

    def _load_catalog(self, version):
        """加载某版本的摘要缓存;不可用时返回 None(每次查询会实时计算)。"""
        if version in self._catalogs:
            return self._catalogs[version]
        catalog = None
        path = os.path.join(version_dir(version), MANIFEST_NAME)
        try:
            with open(path, encoding="utf8") as f:
                data = json.load(f)
            if data.get("sample_bytes") == self._sample_bytes and isinstance(data.get("files"), dict):
                catalog = data["files"]
        except (OSError, ValueError):
            catalog = None
        self._catalogs[version] = catalog
        return catalog

    @staticmethod
    def _candidate_path(version, rel):
        return os.path.join(version_dir(version), *rel.split("/"))

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

    def flush(self):
        """把本次新计算的摘要合并写回各版本的 .dedupe.json 缓存。"""
        self._write_manifest(self._current_version, self._new_entries)
        for version, entries in self._pending.items():
            self._write_manifest(version, entries)

    def _write_manifest(self, version, entries):
        if not entries:
            return
        path = os.path.join(version_dir(version), MANIFEST_NAME)
        manifest = {"sample_bytes": self._sample_bytes, "files": {}}
        try:
            with open(path, encoding="utf8") as f:
                existing = json.load(f)
            if existing.get("sample_bytes") == self._sample_bytes and isinstance(existing.get("files"), dict):
                manifest = existing
        except (OSError, ValueError):
            pass
        manifest["sample_bytes"] = self._sample_bytes
        manifest["files"].update(entries)
        try:
            with open(path, "w", encoding="utf8") as f:
                json.dump(manifest, f, ensure_ascii=False, separators=(",", ":"))
        except OSError as e:
            self._logger.warning("写入摘要缓存失败: %s (%s)", path, e)

    def report(self):
        cache_info = "摘要缓存命中 %d 次/实时计算 %d 次" % (self.cache_compared, self.cache_computes)
        if self.linked_files:
            self._logger.info(
                "去重完成:硬链接 %d 个文件(节省约 %.1f MB),其余 %d 个正常写入;%s",
                self.linked_files, self.linked_bytes / 1024 / 1024, self.written_files, cache_info,
            )
        else:
            self._logger.info(
                "去重完成:未发现可复用的重复文件,%d 个文件正常写入;%s",
                self.written_files, cache_info,
            )
