from typing import Any


class GenerateContentConfig:
    """Keeps whatever it is given, like the real config object."""

    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)
