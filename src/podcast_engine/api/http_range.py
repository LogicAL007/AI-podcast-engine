"""HTTP byte ranges (RFC 9110, section 14) for serving audio that players can seek in."""

import re

_SINGLE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiableError(ValueError):
    """The range lies outside the file: answer 416 with ``Content-Range: bytes */size``."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The inclusive (first, last) byte to send, or None to send the whole file.

    Handles ``bytes=0-499``, ``bytes=500-`` and ``bytes=-500`` (the last 500 bytes). A missing,
    malformed or multi-range header gets the whole file, which RFC 9110 allows a server to do.
    """
    if not header:
        return None
    match = _SINGLE.match(header.strip().replace(" ", ""))
    if match is None:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:  # a suffix: the final N bytes
        length = int(last)
        if length == 0:
            raise RangeNotSatisfiableError(header)
        return (max(size - length, 0), size - 1)
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or (last and int(last) < start):
        raise RangeNotSatisfiableError(header)
    return (start, end)
