"""解析 Android APK 内的二进制 AndroidManifest.xml。

纯 Python 实现(无额外依赖),用于读取包名、versionName、versionCode。
"""
import struct
from zipfile import ZipFile

MANIFEST_PATH = "AndroidManifest.xml"

_STRING_POOL = 0x0001
_START_ELEMENT = 0x0102
_TYPE_STRING = 0x03


class ManifestParseError(Exception):
    """AndroidManifest.xml 解析失败。"""


def _decode_length(data, pos):
    """解码 Android 资源字符串长度的 7bit 变长编码(1-2 字节)。"""
    value = data[pos]
    if value & 0x80:
        return ((value & 0x7F) << 8) | data[pos + 1], pos + 2
    return value, pos + 1


def _read_string_pool(data, offset):
    """解析字符串池 chunk,返回字符串列表。"""
    chunk_type, header_size, _ = struct.unpack_from("<HHI", data, offset)
    if chunk_type != _STRING_POOL:
        raise ManifestParseError("未找到字符串池")
    string_count, _, flags, strings_start, _ = struct.unpack_from("<IIIII", data, offset + 8)
    utf8 = bool(flags & (1 << 8))
    offset_table = offset + header_size
    strings = []
    for i in range(string_count):
        str_offset = struct.unpack_from("<I", data, offset_table + i * 4)[0]
        pos = offset + strings_start + str_offset
        if utf8:
            _, pos = _decode_length(data, pos)      # 字符数(UTF-16 单元)
            byte_len, pos = _decode_length(data, pos)
            strings.append(data[pos:pos + byte_len].decode("utf-8", "replace"))
        else:
            char_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            strings.append(data[pos:pos + char_len * 2].decode("utf-16-le", "replace"))
    return strings


def _iter_chunks(data):
    """从 RES_XML 文件头之后依次遍历 chunk。"""
    pos = 8  # 跳过 RES_XML_TYPE chunk 头(type/headerSize/size)
    while pos + 8 <= len(data):
        chunk_type, header_size, chunk_size = struct.unpack_from("<HHI", data, pos)
        if chunk_size <= 0:
            break
        yield chunk_type, pos, header_size, chunk_size
        pos += chunk_size


def _parse_start_element(data, pos, strings):
    """解析一个 start element chunk,返回 (元素名, {属性名: 值})。"""
    _, name_index = struct.unpack_from("<II", data, pos + 16)
    attribute_start, attribute_size, attribute_count = struct.unpack_from("<HHH", data, pos + 24)
    attributes = {}
    for i in range(attribute_count):
        attr_pos = pos + 16 + attribute_start + i * attribute_size
        _, attr_name_index, raw_index = struct.unpack_from("<III", data, attr_pos)
        _, _, value_type = struct.unpack_from("<HBB", data, attr_pos + 12)
        value_data = struct.unpack_from("<I", data, attr_pos + 16)[0]

        if raw_index != 0xFFFFFFFF:
            value = strings[raw_index]
        elif value_type == _TYPE_STRING and value_data != 0xFFFFFFFF:
            value = strings[value_data]
        else:
            value = value_data
        name = strings[attr_name_index] if attr_name_index != 0xFFFFFFFF else ""
        attributes.setdefault(name, value)
    element_name = strings[name_index] if name_index != 0xFFFFFFFF else ""
    return element_name, attributes


def parse_manifest(data):
    """解析 AXML 字节,返回 {"package", "version_name", "version_code"}。"""
    strings = None
    root_attributes = {}
    for chunk_type, pos, _, _ in _iter_chunks(data):
        if chunk_type == _STRING_POOL and strings is None:
            strings = _read_string_pool(data, pos)
        elif chunk_type == _START_ELEMENT and strings is not None:
            element_name, attributes = _parse_start_element(data, pos, strings)
            if element_name == "manifest":
                root_attributes = attributes
                break
    if not root_attributes:
        raise ManifestParseError("未找到 manifest 元素")
    return {
        "package": root_attributes.get("package"),
        "version_name": root_attributes.get("versionName"),
        "version_code": root_attributes.get("versionCode"),
    }


def read_manifest(apk_path):
    """读取 APK 的 AndroidManifest.xml 并解析。"""
    with ZipFile(apk_path) as apk:
        if MANIFEST_PATH not in apk.NameToInfo:
            raise ManifestParseError("APK 内没有 AndroidManifest.xml")
        data = apk.read(MANIFEST_PATH)
    return parse_manifest(data)
