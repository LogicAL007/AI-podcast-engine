import pytest

from podcast_engine.api.http_range import RangeNotSatisfiableError, parse_range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("bytes=0-99", (0, 99)),
        ("bytes=10-", (10, 99)),
        ("bytes=-10", (90, 99)),
        ("bytes=-500", (0, 99)),
        ("bytes=50-5000", (50, 99)),
        ("bytes=0-1,5-6", None),  # several ranges: send the whole file
        ("items=0-1", None),
        ("bytes=-", None),
    ],
)
def test_parse_range(header: str | None, expected: tuple[int, int] | None) -> None:
    assert parse_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=50-10", "bytes=-0"])
def test_unsatisfiable(header: str) -> None:
    with pytest.raises(RangeNotSatisfiableError):
        parse_range(header, 100)
