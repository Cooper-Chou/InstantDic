"""MDict (.mdx / .mdd) reader with random access.

Indexing reads only the key section at the start of the file; records are fetched
block-by-block on demand, so multi-GB .mdd files never need to be loaded.
Format reference: https://github.com/zhansliu/writemdict/blob/master/fileformat.md
"""
import re
import struct
import zlib
from collections import OrderedDict

from ._ripemd128 import ripemd128  # vendored from zhansliu/writemdict (MIT)


class MDictError(Exception):
    pass


def _decompress(block):
    kind = block[:4]
    data = block[8:]
    if kind == b"\x00\x00\x00\x00":
        return data
    if kind == b"\x02\x00\x00\x00":
        return zlib.decompress(data)
    if kind == b"\x01\x00\x00\x00":
        try:
            import lzo  # optional, only very old dictionaries use LZO
        except ImportError:
            raise MDictError("该词典使用 LZO 压缩，暂不支持")
        return lzo.decompress(data, initSize=0x100000, blockSize=0x100000)  # noqa
    raise MDictError(f"未知压缩类型 {kind!r}")


def _fast_decrypt(data, key):
    b = bytearray(data)
    prev = 0x36
    for i in range(len(b)):
        t = ((b[i] >> 4) | (b[i] << 4)) & 0xFF
        t = t ^ prev ^ (i & 0xFF) ^ key[i % len(key)]
        prev = b[i]
        b[i] = t
    return bytes(b)


class MDict:
    def __init__(self, path, is_mdd=False):
        self.path = str(path)
        self.is_mdd = is_mdd
        self._f = open(self.path, "rb")
        self._block_cache = OrderedDict()
        self._read_header()

    def close(self):
        self._f.close()

    # ---------- header ----------
    def _read_header(self):
        f = self._f
        (size,) = struct.unpack(">I", f.read(4))
        raw = f.read(size)
        f.read(4)  # adler32
        text = raw.decode("utf-16-le", errors="ignore").rstrip("\x00")
        self.header = dict(re.findall(r'(\w+)="(.*?)"', text, re.S))
        self.version = float(self.header.get("GeneratedByEngineVersion", "2.0") or 2.0)
        enc_flag = self.header.get("Encrypted", "0")
        self.encrypted = 1 if enc_flag == "Yes" else int(enc_flag) if enc_flag.isdigit() else 0
        enc = self.header.get("Encoding", "").upper()
        if self.is_mdd:
            enc = "UTF-16"
        self.encoding = {"": "utf-8", "UTF-8": "utf-8", "UTF-16": "utf-16-le", "GBK": "gb18030",
                         "GB2312": "gb18030", "BIG5": "big5"}.get(enc, enc.lower() or "utf-8")
        self.title = self.header.get("Title", "")
        self._num_width = 8 if self.version >= 2.0 else 4
        self._num_fmt = ">Q" if self.version >= 2.0 else ">I"
        self.key_section_start = f.tell()

    def _num(self, buf, pos):
        return struct.unpack_from(self._num_fmt, buf, pos)[0], pos + self._num_width

    # ---------- keys ----------
    def read_keys(self):
        """Return [(key, record_offset)] in file order, plus record-section layout."""
        if self.encrypted & 1:
            raise MDictError("该词典已加密（需要注册码），无法读取")
        f = self._f
        f.seek(self.key_section_start)
        n = 5 if self.version >= 2.0 else 4
        head = f.read(n * self._num_width)
        if self.version >= 2.0:
            f.read(4)  # adler32 of head
        vals = struct.unpack(">" + ("Q" if self.version >= 2.0 else "I") * n, head)
        if self.version >= 2.0:
            num_blocks, num_entries, _info_decomp, info_size, blocks_size = vals
        else:
            num_blocks, num_entries, info_size, blocks_size = vals
        info = f.read(info_size)
        blocks = f.read(blocks_size)
        self.record_section_start = f.tell()

        info = self._decode_key_info(info)
        sizes = self._parse_key_info(info, num_blocks)
        keys = []
        pos = 0
        for comp, _decomp in sizes:
            keys.extend(self._split_key_block(_decompress(blocks[pos:pos + comp])))
            pos += comp
        self._read_record_layout()
        return keys

    def _decode_key_info(self, info):
        if self.version < 2.0:
            return info
        if self.encrypted & 2:
            key = ripemd128(info[4:8] + struct.pack("<L", 0x3695))
            info = info[:8] + _fast_decrypt(info[8:], key)
        return zlib.decompress(info[8:])

    def _parse_key_info(self, info, num_blocks):
        utf16 = self.encoding == "utf-16-le"
        v2 = self.version >= 2.0
        term = 1 if v2 else 0
        sizes = []
        p = 0
        for _ in range(num_blocks):
            _, p = self._num(info, p)  # entries in block
            for _ in range(2):  # first key, last key
                if v2:
                    (ks,) = struct.unpack_from(">H", info, p)
                    p += 2
                else:
                    ks = info[p]
                    p += 1
                p += (ks + term) * 2 if utf16 else ks + term
            comp, p = self._num(info, p)
            decomp, p = self._num(info, p)
            sizes.append((comp, decomp))
        return sizes

    def _split_key_block(self, data):
        out = []
        utf16 = self.encoding == "utf-16-le"
        w = self._num_width
        p, n = 0, len(data)
        while p < n:
            offset = struct.unpack_from(self._num_fmt, data, p)[0]
            p += w
            if utf16:
                end = p
                while end + 1 < n and not (data[end] == 0 and data[end + 1] == 0):
                    end += 2
                key = data[p:end].decode("utf-16-le", errors="ignore")
                p = end + 2
            else:
                end = data.find(b"\x00", p)
                if end < 0:
                    end = n
                key = data[p:end].decode(self.encoding, errors="ignore")
                p = end + 1
            out.append((key, offset))
        return out

    # ---------- records ----------
    def _read_record_layout(self):
        f = self._f
        f.seek(self.record_section_start)
        n = 4
        vals = struct.unpack(self._num_fmt[0] + self._num_fmt[1] * n, f.read(n * self._num_width))
        num_blocks, _entries, info_size, _blocks_size = vals
        info = f.read(info_size)
        data_start = f.tell()
        layout = []  # (comp_offset_in_file, comp_size, decomp_offset, decomp_size)
        comp_off, decomp_off = data_start, 0
        p = 0
        for _ in range(num_blocks):
            comp, p = self._num(info, p)
            decomp, p = self._num(info, p)
            layout.append((comp_off, comp, decomp_off, decomp))
            comp_off += comp
            decomp_off += decomp
        self.record_layout = layout
        self.total_decomp = decomp_off

    def set_record_layout(self, layout):
        self.record_layout = layout
        self.total_decomp = layout[-1][2] + layout[-1][3] if layout else 0

    def _block(self, i):
        if i in self._block_cache:
            self._block_cache.move_to_end(i)
            return self._block_cache[i]
        comp_off, comp, _d_off, _d = self.record_layout[i]
        self._f.seek(comp_off)
        data = _decompress(self._f.read(comp))
        self._block_cache[i] = data
        if len(self._block_cache) > 24:
            self._block_cache.popitem(last=False)
        return data

    def read_record(self, start, end):
        """Bytes of the record spanning [start, end) in the decompressed record stream."""
        import bisect
        starts = self._starts if hasattr(self, "_starts") else None
        if starts is None or len(starts) != len(self.record_layout):
            self._starts = starts = [b[2] for b in self.record_layout]
        i = bisect.bisect_right(starts, start) - 1
        out = bytearray()
        pos = start
        while pos < end and i < len(self.record_layout):
            _, _, d_off, d_size = self.record_layout[i]
            block = self._block(i)
            out += block[pos - d_off:min(end, d_off + d_size) - d_off]
            pos = d_off + d_size
            i += 1
        return bytes(out)

    def decode_text(self, raw):
        return raw.decode(self.encoding, errors="replace").rstrip("\x00")
