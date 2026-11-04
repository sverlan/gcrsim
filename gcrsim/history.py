"""A set of strings that stores 128-bit digests instead of the strings (the optional ``hash_history`` setting).

The history of seen strings is the largest part of the memory of a long run. Keeping a 16-byte digest instead of each string
cuts that to a fraction. The price is that the duplicate test is no longer exact: two different strings with the same digest
would be taken for one. With a 128-bit cryptographic hash the probability of that is below 2**-60 even for 10**9 strings, but it
is not zero, so a run with ``hash_history`` is outside the exactness guarantee of docs/checking.md.
"""

from __future__ import annotations

import hashlib
from typing import Iterable


def digest(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=16).digest()


class DigestSet:
    """The part of the ``set`` interface the engine uses (``in``, ``add``, ``len``), over digests."""

    __slots__ = ("_digests",)

    def __init__(self, items: Iterable[str] = ()):
        self._digests = {digest(s) for s in items}

    def add(self, text: str) -> None:
        self._digests.add(digest(text))

    def __contains__(self, text: object) -> bool:
        return digest(text) in self._digests  # type: ignore[arg-type]

    def __len__(self) -> int:
        return len(self._digests)
