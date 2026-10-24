"""On-the-fly transcoding of Speex (.spx) pronunciations to WAV.

Chromium can't play Speex (used by LDOCE5 and other older MDX dictionaries), but Qt Multimedia's
bundled FFmpeg can decode it. Decoding is asynchronous; the callback gets WAV bytes or None.
"""
import array
import logging
import struct
from collections import OrderedDict

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

log = logging.getLogger(__name__)


def _wav(pcm16: bytes, rate: int, channels: int) -> bytes:
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm16)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16)
            + b"data" + struct.pack("<I", len(pcm16)) + pcm16)


def _to_int16(raw: bytes, fmt: QAudioFormat) -> bytes:
    sf = fmt.sampleFormat()
    if sf == QAudioFormat.Int16:
        return raw
    if sf == QAudioFormat.Float:
        f = array.array("f", raw)
        return array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in f)).tobytes()
    if sf == QAudioFormat.Int32:
        return array.array("h", (x >> 16 for x in array.array("i", raw))).tobytes()
    if sf == QAudioFormat.UInt8:
        return array.array("h", ((x - 128) << 8 for x in raw)).tobytes()
    raise ValueError(f"unsupported sample format {sf}")


class SpeexTranscoder(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = OrderedDict()
        self._jobs = set()  # keeps decoders alive while running

    def to_wav(self, key, data: bytes, callback):
        hit = self.cache.get(key)
        if hit is not None:
            callback(hit)
            return
        dec = QAudioDecoder(self)
        buf = QBuffer(dec)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.ReadOnly)
        dec.setSourceDevice(buf)
        chunks, fmt = [], [None]
        state = {"dec": dec, "buf": buf}
        self._jobs.add(id(state))

        def on_buffer():
            b = dec.read()
            fmt[0] = b.format()
            chunks.append(bytes(b.constData()[:b.byteCount()]) if hasattr(b, "constData") else bytes(b.data()))

        def finish(wav):
            if id(state) not in self._jobs:
                return
            self._jobs.discard(id(state))
            if wav:
                self.cache[key] = wav
                while len(self.cache) > 200:
                    self.cache.popitem(last=False)
            callback(wav)
            dec.deleteLater()

        def on_finished():
            try:
                f = fmt[0]
                pcm = _to_int16(b"".join(chunks), f)
                finish(_wav(pcm, f.sampleRate(), f.channelCount()))
            except Exception:
                log.exception("speex transcode failed for %s", key)
                finish(None)

        def on_error(*_):
            log.warning("speex decode error for %s: %s", key, dec.errorString())
            finish(None)

        dec.bufferReady.connect(on_buffer)
        dec.finished.connect(on_finished)
        dec.error.connect(on_error)
        dec.start()
