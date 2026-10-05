"""phira.py 的单元测试:谱面信息格式(yml/txt)、SP/Legacy 打包与未知信息回退。"""
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
        names = set(pez.namelist())
        info_yml = pez.read("info.yml").decode("utf8")
        chart = pez.read("%s.json" % song_id).decode("utf8")
    assert "info.yml" in names and "info.txt" not in names
    for line in ("difficulty: 0.0", "level: 'SP Lv.?'", "charter: 'UK'",
                 "previewStart: 0.0", "aspectRatio: 1.7777778", "backgroundDim: 0.6",
                 "lineLength: 6.0", "offset: 0.0", "tags: []", "intro: ''",
                 "holdPartialCover: false"):
        assert line in info_yml
    assert "unlockVideo" not in info_yml
    assert chart == '{"lv": "SP"}'


def test_run_packages_legacy_pez(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Legacy"
    # 槽位 EZ/HD/IN/AT/Legacy:无 AT、有旧谱(定数 15.6)
    _write_csv(os.path.join(common.version_dir(version), "info", "info.csv"),
               [[song_id, "Song", "Composer", "Illustrator", "C1", "C2", "C3", "", "旧谱师"]])
    _write_csv(os.path.join(common.version_dir(version), "info", "difficulty.csv"),
               [[song_id, "3.5", "12.2", "16.0", "", "15.6"]])
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    for level in ("EZ", "HD", "IN", "Legacy"):
        with open(os.path.join(chart_dir, "%s.json" % level), "w", encoding="utf8") as f:
            f.write('{"lv": "%s"}' % level)

    created = phira.run(version, _logger(), ProgressReporter())
    assert created == 4  # EZ/HD/IN/Legacy(跳过空槽位 AT)

    song_dir = os.path.join(common.version_dir(version), "phira", "%s.0" % song_id)
    assert not os.path.exists(os.path.join(song_dir, "AT.pez"))
    legacy_pez = os.path.join(song_dir, "Legacy.pez")
    assert os.path.isfile(legacy_pez)
    with ZipFile(legacy_pez) as pez:
        info_yml = pez.read("info.yml").decode("utf8")
    assert "difficulty: 15.6" in info_yml
    assert "level: 'Legacy Lv.15.6'" in info_yml
    assert "charter: '旧谱师'" in info_yml


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
        info_yml = pez.read("info.yml").decode("utf8")
    assert "difficulty: 0.0" in info_yml
    assert "level: 'SP Lv.?'" in info_yml
    assert "%s.json" % song_id in names


def test_build_pez_txt_format(tmp_path, monkeypatch):
    """info_format="txt":仍可输出 RPE 兼容格式(无 difficulty 字段)。"""
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Txt"
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    with open(os.path.join(chart_dir, "EZ.json"), "w", encoding="utf8") as f:
        f.write('{"lv": "EZ"}')
    info = {"Name": "Song", "Composer": "Composer", "Illustrator": "Illustrator",
            "Chater": ["Charter"], "difficulty": ["3.0"]}

    data = phira.build_pez_bytes(version, "EZ", song_id, info, _logger(), 0, info_format="txt")
    with ZipFile(BytesIO(data)) as pez:
        names = set(pez.namelist())
        info_txt = pez.read("info.txt").decode("utf8")
    assert "info.txt" in names and "info.yml" not in names
    assert "Level: EZ Lv.3.0" in info_txt
    assert "Charter: Charter" in info_txt


def test_build_pez_yaml_escapes_special_values(tmp_path, monkeypatch):
    """info.yml 字符串一律单引号包裹,值内的单引号写两遍转义。"""
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Yaml"
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    with open(os.path.join(chart_dir, "HD.json"), "w", encoding="utf8") as f:
        f.write('{"lv": "HD"}')
    info = {"Name": "It's: a test", "Composer": "C", "Illustrator": "I",
            "Chater": ["O'Brien"], "difficulty": ["7.5"]}

    data = phira.build_pez_bytes(version, "HD", song_id, info, _logger(), 0)
    with ZipFile(BytesIO(data)) as pez:
        info_yml = pez.read("info.yml").decode("utf8")
    assert "name: 'It''s: a test'" in info_yml
    assert "charter: 'O''Brien'" in info_yml
    assert "difficulty: 7.5" in info_yml
    assert "level: 'HD Lv.7.5'" in info_yml


def test_video_sources_mapping():
    assert phira._video_sources_for("Spasmodic.姜米條", "AT") == ["Spas_Unlock"]
    assert phira._video_sources_for("DesultorySignals.technoplanet", "EZ") == [
        "ds_unlockIntro_Sound", "ds_unlockDifficulties", "ds_unlockEZ"]
    assert phira._video_sources_for("DesultorySignals.technoplanet", "Legacy") is None
    assert phira._video_sources_for("SomeOtherSong.test", "EZ") is None


def test_build_pez_with_video(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Video"
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    with open(os.path.join(chart_dir, "EZ.json"), "w", encoding="utf8") as f:
        f.write('{"lv": "EZ"}')
    info = {"Name": "Song", "Composer": "C", "Illustrator": "I",
            "Chater": ["Charter"], "difficulty": ["1.0"]}

    data = phira.build_pez_bytes(version, "EZ", song_id, info, _logger(), 0,
                                 video=("Song.Video_unlock.mp4", b"FAKEVIDEO"))
    with ZipFile(BytesIO(data)) as pez:
        info_yml = pez.read("info.yml").decode("utf8")
        video_data = pez.read("Song.Video_unlock.mp4")
    assert "unlockVideo: 'Song.Video_unlock.mp4'" in info_yml
    assert video_data == b"FAKEVIDEO"


def test_build_pez_custom_extra_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUT_ROOT", str(tmp_path / "outputs"))
    version = "9.9.9"
    song_id = "Song.Extra"
    chart_dir = os.path.join(common.resource_dir(version, "chart"), "%s.0" % song_id)
    os.makedirs(chart_dir)
    with open(os.path.join(chart_dir, "EZ.json"), "w", encoding="utf8") as f:
        f.write('{"lv": "EZ"}')
    info = {"Name": "Song", "Composer": "C", "Illustrator": "I",
            "Chater": ["Charter"], "difficulty": ["1.0"]}
    extra = {"preview_start": 1.5, "aspect_ratio": 2.0, "background_dim": 0.3,
             "line_length": 5.0, "offset": 0.25, "tags": ["a", "b"],
             "intro": "hello", "hold_partial_cover": True}

    data = phira.build_pez_bytes(version, "EZ", song_id, info, _logger(), 0, extra_fields=extra)
    with ZipFile(BytesIO(data)) as pez:
        info_yml = pez.read("info.yml").decode("utf8")
    for line in ("previewStart: 1.5", "aspectRatio: 2.0", "backgroundDim: 0.3",
                 "lineLength: 5.0", "offset: 0.25", "tags: ['a', 'b']",
                 "intro: 'hello'", "holdPartialCover: true"):
        assert line in info_yml


def test_chart_extra_fields_reads_nested_config():
    extra = phira._chart_extra_fields(
        {"info": {"preview_start": 2.5, "tags": ["x"], "hold_partial_cover": True}}, _logger())
    assert extra["preview_start"] == 2.5
    assert extra["tags"] == ["x"]
    assert extra["hold_partial_cover"] is True


def test_chart_extra_fields_fallbacks():
    extra = phira._chart_extra_fields({"info": {"preview_start": "bad", "tags": "not-a-list"}}, _logger())
    assert extra["preview_start"] == 0.0
    assert extra["tags"] == []
    assert extra["hold_partial_cover"] is False
    # 非法 info 段整体回退默认
    extra = phira._chart_extra_fields({"info": "bad"}, _logger())
    assert extra["preview_start"] == 0.0
    assert extra["tags"] == []


def test_build_unlock_video_single_file(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "Spas_Unlock.mp4").write_bytes(b"V")
    cache = {}
    result = phira._build_unlock_video("Spasmodic.x", "AT", str(videos_dir), cache, _logger())
    assert result == ("Spasmodic.x_unlock.mp4", b"V")
    # 同曲目其它难度命中缓存
    assert phira._build_unlock_video("Spasmodic.x", "EZ", str(videos_dir), cache, _logger()) == result
    # 无映射曲目返回 None
    assert phira._build_unlock_video("Unknown.x", "EZ", str(videos_dir), cache, _logger()) is None


def test_build_unlock_video_missing_file(tmp_path):
    cache = {}
    assert phira._build_unlock_video("Spasmodic.x", "AT", str(tmp_path), cache, _logger()) is None
    assert cache  # 失败结果也缓存,避免重复告警


def test_concat_videos_dispatches_by_resolution(monkeypatch):
    calls = []
    monkeypatch.setattr(phira, "_video_size",
                        lambda path: {"a": (1440, 1080), "b": (1920, 1080)}[path])
    monkeypatch.setattr(phira, "_concat_videos_copy", lambda paths, logger: calls.append("copy") or b"COPY")
    monkeypatch.setattr(phira, "_concat_videos_reencode",
                        lambda paths, sizes, logger: calls.append("reencode") or b"RE")
    assert phira._concat_videos(["a", "b"], _logger()) == b"RE"
    assert calls == ["reencode"]


def test_concat_videos_uniform_uses_copy(monkeypatch):
    monkeypatch.setattr(phira, "_video_size", lambda path: (1920, 1080))
    monkeypatch.setattr(phira, "_concat_videos_copy", lambda paths, logger: b"COPY")
    monkeypatch.setattr(phira, "_concat_videos_reencode",
                        lambda paths, sizes, logger: (_ for _ in ()).throw(AssertionError("不应重编码")))
    assert phira._concat_videos(["a", "b"], _logger()) == b"COPY"
