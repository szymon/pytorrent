from typing import Dict, Iterable, Union
import string


_digits_as_bytes = tuple(ord(x) for x in string.digits)

BCodeType = Union[
    int, bytes, str, Dict[Union[str, bytes], "BCodeType"], Iterable["BCodeType"]
]


def _decode_int(data: bytes) -> BCodeType:
    data_end = data.index(b"e")
    return int(data[1:data_end].decode()), data[1 + data_end :]


def _decode_string(data: bytes) -> BCodeType:
    length_data = []
    i = 0

    while True:
        c = data[i]
        i += 1

        if c == ord(b":"):
            break

        length_data.append(chr(c))

    length = int("".join(length_data))

    return data[i : i + length], data[i + length :]


def _decode_list(data: bytes) -> BCodeType:
    results = []

    data = data[1:]

    while True:

        value, data = _bdecode_impl(data)

        results.append(value)

        if data[0] == ord(b"e"):
            break

    data = data[1:]

    return (results, data)


def _decode_dict(data: bytes) -> BCodeType:
    results_data = []
    data = data[1:]

    while True:

        key, data = _bdecode_impl(data)
        value, data = _bdecode_impl(data)

        results_data.append((key, value))

        if data[0] == ord(b"e"):
            break

    data = data[1:]

    return dict(results_data), data


def _bdecode_impl(data: bytes) -> BCodeType:
    if data.startswith(b"i"):
        return _decode_int(data)
    elif data[0] in _digits_as_bytes:
        return _decode_string(data)
    elif data.startswith(b"l"):
        return _decode_list(data)
    elif data.startswith(b"d"):
        return _decode_dict(data)
    else:
        raise NotImplementedError


def bdecode(data: bytes) -> BCodeType:
    return _bdecode_impl(data)[0]


def bencode(data: BCodeType) -> bytes:
    if isinstance(data, int):
        return f"i{data}e".encode()
    elif isinstance(data, (bytes, str)):
        if isinstance(data, bytes):
            return str(len(data)).encode() + b":" + data
        return f"{len(data)}:{data}".encode()
    elif isinstance(data, (list, tuple)):
        encoded = b""
        for value in data:
            encoded += bencode(value)

        return b"l" + encoded + b"e"
    elif isinstance(data, dict):
        encoded = b""
        for key, value in data.items():
            encoded += bencode(key) + bencode(value)

        return b"d" + encoded + b"e"
    else:
        raise ValueError
