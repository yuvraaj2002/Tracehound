"""Collapse repeated log messages so adapters return unique lines with an occurrence count."""

import hashlib

from tracehound.schemas.logs import LogLine


def dedupe_by_message(lines: list[LogLine]) -> list[LogLine]:
    """Keep the first line for each exact ``message``, bumping ``occurrence`` on repeats.

    Input should already be oldest-first. Order of first appearances is preserved.
    """
    order: list[str] = []
    kept: dict[str, LogLine] = {}
    for line in lines:
        key = hashlib.sha256(line.message.encode()).hexdigest()
        if key not in kept:
            order.append(key)
            kept[key] = line
            continue
        prior = kept[key]
        kept[key] = prior.model_copy(update={"occurrence": prior.occurrence + 1})
    return [kept[key] for key in order]
