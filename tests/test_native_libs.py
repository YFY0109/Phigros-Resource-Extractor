"""native_libs.py 的单元测试:跨平台本地库查找与可用性检查。"""
import pytest

import native_libs


def test_candidate_patterns_linux(monkeypatch):
    monkeypatch.setattr(native_libs.sys, "platform", "linux")
    assert native_libs._candidate_patterns("vorbis") == ["libvorbis.so", "libvorbis.so.*"]


def test_candidate_patterns_windows(monkeypatch):
    monkeypatch.setattr(native_libs.sys, "platform", "win32")
    assert native_libs._candidate_patterns("vorbis") == ["libvorbis.dll", "vorbis.dll"]


def test_find_library_prefers_system(monkeypatch):
    monkeypatch.setattr(native_libs, "_ORIGINAL_FIND_LIBRARY", lambda name: "system-%s" % name)
    assert native_libs.find_library("vorbis") == "system-vorbis"


def test_find_library_falls_back_to_local_so(tmp_path, monkeypatch):
    monkeypatch.setattr(native_libs, "_ORIGINAL_FIND_LIBRARY", lambda name: None)
    monkeypatch.setattr(native_libs.sys, "platform", "linux")
    monkeypatch.chdir(tmp_path)
    lib = tmp_path / "libvorbis.so.0"
    lib.write_bytes(b"")
    assert native_libs.find_library("vorbis") == str(lib)


def test_find_library_ignores_unknown_names(tmp_path, monkeypatch):
    monkeypatch.setattr(native_libs, "_ORIGINAL_FIND_LIBRARY", lambda name: None)
    monkeypatch.setattr(native_libs.sys, "platform", "linux")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "libfoo.so").write_bytes(b"")
    assert native_libs.find_library("foo") is None


def test_check_available_ok(monkeypatch):
    monkeypatch.setattr(native_libs, "missing_libraries", lambda: [])
    assert native_libs.check_available() is None


def test_check_available_raises_with_hint(monkeypatch):
    monkeypatch.setattr(native_libs, "missing_libraries", lambda: ["vorbis", "ogg"])
    monkeypatch.setattr(native_libs.sys, "platform", "linux")
    with pytest.raises(RuntimeError) as exc:
        native_libs.check_available()
    assert "vorbis" in str(exc.value)
    assert "libogg" in str(exc.value)


def test_ensure_patched_is_idempotent(monkeypatch):
    monkeypatch.setattr(native_libs, "_PATCHED", False)
    original = native_libs.ctypes.util.find_library
    try:
        native_libs.ensure_patched()
        assert native_libs.ctypes.util.find_library is native_libs.find_library
        native_libs.ensure_patched()
        assert native_libs._PATCHED is True
    finally:
        monkeypatch.setattr(native_libs.ctypes.util, "find_library", original)


def test_missing_libraries_vorbisenc_can_fall_back_to_vorbis(monkeypatch):
    """单独缺 vorbisenc 时不算缺失:vorbis 带编码符号即可(Windows 官方 DLL)。"""
    paths = {"vorbis": "/lib/libvorbis.dll", "ogg": "/lib/libogg.dll"}
    monkeypatch.setattr(native_libs, "find_library", lambda name: paths.get(name))
    monkeypatch.setattr(native_libs, "_has_encode_symbol", lambda path: True)
    assert native_libs.missing_libraries() == []


def test_missing_libraries_reports_vorbisenc_without_symbols(monkeypatch):
    """vorbis 也不带编码符号时,vorbisenc 仍算缺失(Linux 解码版 libvorbis)。"""
    paths = {"vorbis": "/lib/libvorbis.so.0", "ogg": "/lib/libogg.so.0"}
    monkeypatch.setattr(native_libs, "find_library", lambda name: paths.get(name))
    monkeypatch.setattr(native_libs, "_has_encode_symbol", lambda path: False)
    assert native_libs.missing_libraries() == ["vorbisenc"]


def test_missing_libraries_reports_all_when_nothing_found(monkeypatch):
    monkeypatch.setattr(native_libs, "find_library", lambda name: None)
    assert native_libs.missing_libraries() == ["vorbis", "vorbisenc", "ogg"]
