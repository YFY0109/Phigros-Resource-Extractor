"""读取 APK 元数据(基于 apkutils):包名、versionName、versionCode。"""
import xml.etree.ElementTree as ET

from apkutils import APK

_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class ManifestParseError(Exception):
    """APK 元数据读取失败。"""


def _extract_version_code(manifest_xml):
    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError:
        return None
    return root.get(_ANDROID_NS + "versionCode")


def read_manifest(apk_path):
    """读取 APK 的 AndroidManifest 信息,返回 {"package", "version_name", "version_code"}。"""
    try:
        apk = APK.from_file(apk_path)
    except Exception as e:
        raise ManifestParseError("打开 APK 失败: %s" % e)
    try:
        # 先 get_manifest() 触发 AXML 解析;之后 package_name/version_name 属性才可用
        manifest_xml = apk.get_manifest()
        package = apk.package_name
        version_name = apk.version_name
    except Exception as e:
        raise ManifestParseError("解析 AndroidManifest 失败: %s" % e)
    finally:
        try:
            apk.close()
        except Exception:
            pass
    if not package and not version_name:
        raise ManifestParseError("未能从 APK 读取包信息")
    return {
        "package": package,
        "version_name": version_name,
        "version_code": _extract_version_code(manifest_xml),
    }
