"""batch.py 的单元测试:APK 校验、hash 与待处理扫描、批量容错。"""
import logging
import os
from zipfile import ZipFile

import pytest

import batch
import common
from progress import ProgressReporter, TaskCancelled


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
    monkeypatch.setattr(batch, "HISTORY_PATH", str(tmp_path / "outputs" / "processed.json"))
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


def _pending_item(tmp_path, version, name):
    path = tmp_path / name
    path.write_bytes(b"x")
    return {"path": str(path), "version": version, "sha256": version}


def test_process_all_isolates_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "HISTORY_PATH", str(tmp_path / "processed.json"))
    items = [_pending_item(tmp_path, "1.0.0", "a.apk"), _pending_item(tmp_path, "1.0.1", "b.apk")]
    monkeypatch.setattr(batch, "find_pending", lambda logger: items)

    calls = []

    def fake_run(path, version, logger, progress):
        calls.append(version)
        if version == "1.0.0":
            raise RuntimeError("模拟失败")

    monkeypatch.setattr(batch.gameInformation, "run", fake_run)
    count = batch.process_all(("info",), {}, _logger(), ProgressReporter())
    assert calls == ["1.0.0", "1.0.1"]  # 失败后继续处理后续 APK
    assert count == 1
    assert len(batch.load_history()) == 1  # 仅成功者入台账


def test_process_all_reraises_cancellation(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "HISTORY_PATH", str(tmp_path / "processed.json"))
    monkeypatch.setattr(batch, "find_pending", lambda logger: [_pending_item(tmp_path, "1.0.0", "a.apk")])

    def fake_run(path, version, logger, progress):
        raise TaskCancelled()

    monkeypatch.setattr(batch.gameInformation, "run", fake_run)
    with pytest.raises(TaskCancelled):
        batch.process_all(("info",), {}, _logger(), ProgressReporter())
