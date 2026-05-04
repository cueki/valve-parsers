"""Shared binary I/O helpers for format parsers.

Variants are kept separate (rather than collapsed into one helper) because
each caller depends on slightly different semantics; stream vs random
access, raw bytes vs decoded str, simple vs chunked reads.
"""
from typing import BinaryIO, Union


def read_cstring_stream(file: BinaryIO, *, chunked: bool = False) -> bytes:
    """Read a null-terminated string from a binary file.

    Returns the bytes between the cursor and the next null (excluding the
    null itself). Caller is responsible for decoding and any filtering.

    Args:
        file: Open binary file positioned at the string start.
        chunked: If True, read in 256-byte chunks and seek back past the
        null. Faster for long strings; equivalent to char-by-char for
        short ones. Defaults to False.
    """
    if chunked:
        chunks = []
        while True:
            chunk = file.read(256)
            if not chunk:
                break
            null_pos = chunk.find(b"\x00")
            if null_pos != -1:
                chunks.append(chunk[:null_pos])
                file.seek(-(len(chunk) - null_pos - 1), 1)
                break
            chunks.append(chunk)
        return b"".join(chunks)

    chars = bytearray()
    while True:
        char = file.read(1)
        if not char or char == b"\x00":
            break
        chars.extend(char)
    return bytes(chars)


def write_cstring(
    file: BinaryIO, string: Union[str, bytes], *, errors: str = "replace"
) -> None:
    """Write a null-terminated string to a binary file.

    Args:
        file: Open binary file.
        string: str (ASCII-encoded with the given errors policy) or bytes
            (written as-is).
        errors: Encode error policy when `string` is a str. Defaults to
            "replace" to match the library's forgiving stance on corrupt
            or non-ASCII inputs.
    """
    if isinstance(string, str):
        string = string.encode("ascii", errors=errors)
    file.write(string + b"\x00")


def read_cstring_at(
    buf: bytes,
    offset: int,
    *,
    encoding: str = "ascii",
    errors: str = "replace",
) -> str:
    """Read a null-terminated string from a bytes buffer at a fixed offset.

    Searches forward for the null and decodes everything up to it.

    Args:
        buf: Source buffer.
        offset: Byte offset to start reading from.
        encoding: Text encoding. Defaults to ASCII.
        errors: Decode error policy. Defaults to "replace".
    """
    end = buf.find(b"\x00", offset)
    if end < 0:
        end = len(buf)
    return buf[offset:end].decode(encoding, errors=errors)


def read_fixed_string(
    buf: bytes,
    offset: int,
    length: int,
    *,
    encoding: str = "ascii",
    errors: str = "replace",
) -> str:
    """Read a fixed-width null-padded string from a bytes buffer.

    Reads exactly `length` bytes from `offset`, truncates at the first null,
    and decodes. Used for fixed-width name fields in binary headers.

    Args:
        buf: Source buffer.
        offset: Byte offset to start reading from.
        length: Field width in bytes.
        encoding: Text encoding. Defaults to ASCII.
        errors: Decode error policy. Defaults to "replace".
    """
    chunk = buf[offset:offset + length]
    end = chunk.find(b"\x00")
    if end >= 0:
        chunk = chunk[:end]
    return chunk.decode(encoding, errors=errors)
