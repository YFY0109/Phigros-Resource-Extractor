"""dedupe.py 的单元测试:摘要计算、硬链接写入与缓存。"""
import logging
import os
from io import BytesIO

import common
import dedupe


def _logger():
    logger = logging.getLogger("test-dedupe")
    logger.addHandler(logging.NullHandler())
    return logger


def test_digest_buffer_consistency():
    data = BytesIO(b"0123456789" * 1000)
    assert dedupe.digest_buffer(data, 128) == dedupe.digest_buffer(BytesIO(b"0123456789" * 1000), 128)


def test_digest_differs_on_content_and_size():
    assert dedupe.digest_buffer(BytesIO(b"a" * 5000), 128) != dedupe.digest_buffer(BytesIO(b"a" * 5001), 128)
    changed = bytearray(b"a" * 5000)
    changed[-1] = ord("b")  # 仅尾部不同
    assert dedupe.digest_buffer(BytesIO(b"a" * 5000), 128) != dedupe.digest_buffer(BytesIO(bytes(changed)), 128)


def test_digest_file_matches_buffer(tmp_path):
    path = tmp_path / "f.bin"
    dedupe.write_file(str(path), BytesIO(b"hello" * 100))
    assert dedupe.digest_file(str(path), 64) == dedupe.digest_buffer(BytesIO(b"hello" * 100), 64)


def test_buffer_size():
    assert dedupe.buffer_size(b"12345") == 5
    assert dedupe.buffer_size(BytesIO(b"1234567")) == 7


def test_write_file_roundtrip(tmp_path):
    path = str(tmp_path / "out.bin")
    dedupe.write_file(path, b"bytes data")
    with open(path, "rb") as f:
        assert f.read() == b"bytes data"


def test_try_link_missing_source(tmp_path):
    assert dedupe.DedupeStore._try_link(str(tmp_path / "none.bin"), str(tmp_path / "t.bin")) is False


def test_dedupe_links_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    payload = b"same-content" * 100

    base = common.version_dir("1.0.0")
    os.makedirs(base)
    dedupe.write_file(os.path.join(base, "a.bin"), payload)

    target_dir = common.version_dir("2.0.0")
    os.makedirs(target_dir)
    target = os.path.join(target_dir, "a.bin")

    store = dedupe.DedupeStore("2.0.0", 1024, _logger())
    store.write(target, payload)
    assert store.linked_files == 1
    assert os.stat(target).st_ino == os.stat(os.path.join(base, "a.bin")).st_ino
    store.flush()
    assert os.path.isfile(os.path.join(base, "manifest.json"))
    assert os.path.isfile(os.path.join(target_dir, "manifest.json"))

    # 第二个 store 应命中摘要缓存(不再读取旧文件)
    store2 = dedupe.DedupeStore("2.0.0", 1024, _logger())
    store2.write(target, payload)
    assert store2.linked_files == 1
    assert store2.cache_compared > 0
    assert store2.cache_computes == 0
