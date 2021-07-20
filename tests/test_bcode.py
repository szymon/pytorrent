import pytest

from pytorrent.bcode import bencode, bdecode


@pytest.mark.parametrize("test_input,expected", [(0, b"i0e"), (1, b"i1e"), (-1, b"i-1e")])
def test_encode_int(test_input, expected):
    assert bencode(test_input) == expected


@pytest.mark.parametrize("test_input,expected", [("spam", b"4:spam"), (b"spam", b"4:spam")])
def test_encode_string(test_input, expected):
    assert bencode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected", [(["bar", b"foo", "spam", 42], b"l3:bar3:foo4:spami42ee")]
)
def test_encode_list(test_input, expected):
    assert bencode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected", [({"bar": "spam", "foo": 42}, b"d3:bar4:spam3:fooi42ee")]
)
def test_encode_dict(test_input, expected):
    assert bencode(test_input) == expected


@pytest.mark.parametrize("test_input,expected", [(b"i42e", 42), (b"i0e", 0)])
def test_decode_int(test_input, expected):
    assert bdecode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (b"4:spam", b"spam"),
        (
            b"43:The quick brown fox jumps over the lazy dog",
            b"The quick brown fox jumps over the lazy dog",
        ),
    ],
)
def test_decode_string(test_input, expected):
    assert bdecode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected", [(b"l3:bar3:foo4:spami42ee", [b"bar", b"foo", b"spam", 42])]
)
def test_decode_list(test_input, expected):
    assert bdecode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected", [(b"d3:bar4:spam3:fooi42ee", {b"bar": b"spam", b"foo": 42})]
)
def test_decode_dict(test_input, expected):
    assert bdecode(test_input) == expected


def test_decode_complex():
    expected = {
        b"int": 42,
        b"string": b"this is some string",
        b"list": [
            b"this",
            b"is",
            b"some",
            [b"list", b"with", b"numbers", {b"42": 42, b"0": 0}],
        ],
        b"dict": {b"a": 1, b"b": 2, b"c": b"c"},
    }

    test_input = (
        b"d"
        b"3:inti42e"
        b"6:string19:this is some string"
        b"4:listl4:this2:is4:somel4:list4:with7:numbersd2:42i42e1:0i0eeee"
        b"4:dictd1:ai1e1:bi2e1:c1:ce"
        b"e"
    )

    assert bdecode(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            b"d14:failure reason63:Requested download is not authorized for use with this tracker.e",
            {b"failure reason": b"Requested download is not authorized for use with this tracker."},
        ),
    ],
)
def test_decode_complex_p(test_input, expected):
    assert bdecode(test_input) == expected
