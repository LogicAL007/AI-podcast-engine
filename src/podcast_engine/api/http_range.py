import re

_SINGLE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiableError(ValueError):
    """The requested range lies outside the file.

    The response is 416 with ``Content-Range: bytes */size``.
    """


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Work out which bytes of a file an HTTP ``Range`` header asks for.

    Follows RFC 9110, section 14, so players can seek in served audio. Handles ``bytes=0-499``,
    ``bytes=500-`` and ``bytes=-500`` (a suffix: the last 500 bytes). A missing, malformed or
    multi-range header gets the whole file, which RFC 9110 allows a server to do.

    Args:
        header: The request's ``Range`` header, or None when it has none.
        size: The file's size in bytes.

    Returns:
        The inclusive (first, last) byte to send, or None to send the whole file.

    Raises:
        RangeNotSatisfiableError: The range starts past the end of the file, ends before it starts,
            or is an empty suffix.
    """
    if not header:
        return None
    match = _SINGLE.match(header.strip().replace(" ", ""))
    if match is None:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:
        length = int(last)
        if length == 0:
            raise RangeNotSatisfiableError(header)
        return (max(size - length, 0), size - 1)
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or (last and int(last) < start):
        raise RangeNotSatisfiableError(header)
    return (start, end)
