"""Simple dice roller.

Parses dice strings like ``1d20``, ``1d20+3``, ``2d6``, ``2d6+1`` and
``1d8-1`` and returns structured results.
"""

from __future__ import annotations

import random
import re
from typing import Dict, List, Union

_DICE_RE = re.compile(
    r"^\s*(\d+)\s*[dD]\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*$"
)


def roll(formula: str) -> Dict[str, Union[str, int, List[int]]]:
    """Roll a dice formula and return structured data.

    Args:
        formula: A dice string such as ``"1d20+3"`` or ``"2d6"``.

    Returns:
        A dict with the original ``formula``, the individual ``rolls``,
        the applied ``modifier`` and the ``total``.

    Raises:
        ValueError: If the formula cannot be parsed or is out of range.

    Example:
        >>> roll("1d20+3")  # doctest: +SKIP
        {'formula': '1d20+3', 'rolls': [14], 'modifier': 3, 'total': 17}
    """
    match = _DICE_RE.match(formula)
    if not match:
        raise ValueError(f"Could not parse dice formula: {formula!r}")

    count = int(match.group(1))
    sides = int(match.group(2))
    sign = match.group(3)
    mod_value = match.group(4)

    if count < 1:
        raise ValueError("Dice count must be at least 1.")
    if sides < 1:
        raise ValueError("Dice must have at least 1 side.")

    modifier = 0
    if mod_value is not None:
        modifier = int(mod_value)
        if sign == "-":
            modifier = -modifier

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier

    return {
        "formula": formula.strip(),
        "rolls": rolls,
        "modifier": modifier,
        "total": total,
    }


if __name__ == "__main__":
    import sys

    expr = sys.argv[1] if len(sys.argv) > 1 else "1d20"
    print(roll(expr))
