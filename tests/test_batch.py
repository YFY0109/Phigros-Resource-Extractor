"""batch.py 的单元测试:APK 校验、hash 与待处理扫描。"""
import logging
import os
from zipfile import ZipFile

import batch
import common


def _make_apk(path, entries):
    with ZipFile(str(path), "w") as z:
        for name in entries:
            z.writestr(name, "x")
    return str(path)


def _logger():
    return logging.getLogger("test-batch")


def test_is_phigros_apk_true(tmp_path):
    apk = _make_apk(tmp_path / "ok.apk", [batch.CATALOG_PATH, batch.DATA_PATHS[0]])
    assert batch.is_phigros_apk(apk) is True


def test_is_phigros_apk_false(tmp_path):
    apk = _make_apk(tmp_path / "no.apk", ["assets/other.txt"])
    assert batch.is_phigros_apk(apk) is False


def test_is_phigros_apk_not_zip(tmp_path):
    path = tmp_path / "bad.apk"
    path.write_bytes(b"not a zip")
    assert batch.is_phigros_apk(str(path)) is False


def test_sha256_file(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    assert batch.sha256_file(str(path)) == \
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_find_pending_and_history(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_apk(input_dir / "Phigros_1.0.0.apk", [batch.CATALOG_PATH, batch.DATA_PATHS[0]])

    monkeypatch.setattr(batch, "INPUT_DIR", str(input_dir))
    monkeypatch.setattr(batch, "HISTORY_PATH", str(tmp_path / "outputs" / ".processed.json"))
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))

    logger = _logger()
    pending = batch.find_pending(logger)
    assert len(pending) == 1
    assert pending[0]["version"] == "1.0.0"

    # 台账命中且版本目录存在 -> 跳过
    digest = pending[0]["sha256"]
    os.makedirs(common.version_dir("1.0.0"))
    batch.save_history({digest: {"version": "1.0.0"}})
    assert batch.find_pending(logger) == []

    # 版本目录被删除 -> 重新处理
    os.rmdir(common.version_dir("1.0.0"))
    assert len(batch.find_pending(logger)) == 1
