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
