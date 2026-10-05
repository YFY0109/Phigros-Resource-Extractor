"""phira.py 的单元测试:SP 谱面打包与未知信息回退。"""
import csv
import logging
import os
from io import BytesIO
from zipfile import ZipFile

import common
import phira
from progress import ProgressReporter


def _logger():
    logger = logging.getLogger("test-phira")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return logger


def _write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def test_build_pez_sp_uses_placeholder_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Test"
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    with open(os.path.join(chart_dir, "SP.json"), "w", encoding="utf8") as f:
        f.write('{"lv": "SP"}')
    info = {"Name": "Song", "Composer": "Composer", "Illustrator": "Illustrator",
            "Chater": [], "difficulty": []}

    data = phira.build_pez_bytes(version, "SP", song_id, info, _logger())
    with ZipFile(BytesIO(data)) as pez:
        info_txt = pez.read("info.txt").decode("utf8")
        chart = pez.read("%s.json" % song_id).decode("utf8")
    assert "Level: SP Lv.?\n" in info_txt
    assert "Charter: UK" in info_txt
    assert chart == '{"lv": "SP"}'


def test_run_packages_sp_pez(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Test"
    _write_csv(os.path.join(common.version_dir(version), "info", "info.csv"),
               [[song_id, "Song", "Composer", "Illustrator", "C1", "C2", "C3", "C4"]])
    _write_csv(os.path.join(common.version_dir(version), "info", "difficulty.csv"),
               [[song_id, "1.0", "2.0", "3.0", "4.0"]])
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    for level in ("EZ", "SP"):
        with open(os.path.join(chart_dir, "%s.json" % level), "w", encoding="utf8") as f:
            f.write('{"lv": "%s"}' % level)

    created = phira.run(version, _logger(), ProgressReporter())
    assert created == 5  # EZ/HD/IN/AT + SP

    sp_pez = os.path.join(common.version_dir(version), "phira", "%s.0" % song_id, "SP.pez")
    assert os.path.isfile(sp_pez)
    with ZipFile(sp_pez) as pez:
        names = set(pez.namelist())
        info_txt = pez.read("info.txt").decode("utf8")
    assert "Level: SP Lv.?" in info_txt
    assert "Charter: UK" in info_txt
    assert "%s.json" % song_id in names
