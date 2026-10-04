"""common.py 的单元测试:版本识别、输出路径与配置读写。"""
import json
import os

import pytest

import common


def test_detect_version_from_filename():
    assert common.detect_version("Phigros_4.0.1.apk") == "4.0.1"
    assert common.detect_version("C:/x/Phigros_3.20.0.apk") == "3.20.0"
    assert common.detect_version("Phigros_10.2.30.apk") == "10.2.30"


def test_detect_version_override():
    assert common.detect_version("whatever.apk", "9.9.9") == "9.9.9"


def test_detect_version_failure():
    with pytest.raises(SystemExit):
        common.detect_version("no-version-here.apk")


def test_paths():
    assert common.version_dir("4.0.1") == os.path.join("outputs", "4.0.1")
    assert common.resource_dir("4.0.1", "chart") == os.path.join("outputs", "4.0.1", "charts")


def test_list_versions_sorted_numerically(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path))
    for name in ("1.2.0", "10.0.0", "2.0.0"):
        (tmp_path / name).mkdir()
    (tmp_path / "readme.txt").write_text("x")
    assert common.list_versions() == ["10.0.0", "2.0.0", "1.2.0"]


def test_config_roundtrip(tmp_path):
    path = str(tmp_path / "config.json")
    config = common.load_config(path)
    assert config["types"]["music"] is True
    config["types"]["music"] = False
    config["update"]["main_story"] = 3
    common.save_config(config, path)

    loaded = common.load_config(path)
    assert loaded["types"]["music"] is False
    assert loaded["update"]["main_story"] == 3


def test_config_merges_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"types": {"music": False}, "custom": {"x": 1}}), encoding="utf8")
    config = common.load_config(str(path))
    assert config["types"]["music"] is False
    assert config["types"]["avatar"] is True  # 缺失键用默认补齐
    assert config["custom"] == {"x": 1}       # 自定义键保留
