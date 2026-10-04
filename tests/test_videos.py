"""videos.py 的单元测试:视频容器识别。"""
import videos


def test_video_extension_webm():
    assert videos._video_extension(b"\x1a\x45\xdf\xa3\x01\x02\x03\x04") == ".webm"


def test_video_extension_mp4():
    assert videos._video_extension(b"\x00\x00\x00\x18ftypmp42") == ".mp4"


def test_video_extension_unknown():
    assert videos._video_extension(b"not-a-video") == ".bin"
