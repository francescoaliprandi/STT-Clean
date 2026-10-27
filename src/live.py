"""live.py - what the live draft shows while you speak: pure text logic, no macOS calls."""
import os
from difflib import SequenceMatcher


def diff(old: str, new: str) -> tuple[int, str]:
    """(chars to erase from the end of old, text to add after that) to turn old into new."""
    n = len(os.path.commonprefix([old, new]))
    return len(old) - n, new[n:]


def _words(ws: list) -> list:
    return [w.strip(".,;:!?…\"'«»()").lower() for w in ws]


def _blocks(x: list, y: list) -> list:
    return SequenceMatcher(None, x, y, autojunk=False).get_matching_blocks()


def advance(typed: str, prev: str, draft: str) -> str:
    """Live text after an update. Adds the words the last two drafts agree on (ignoring case and
    punctuation), continuing from where the typed text sits in the newest draft. Typed words stay
    frozen (the final pass fixes them) except the last one, which may still change, e.g. its comma;
    so the text in the app only grows instead of flickering."""
    a, b, t = prev.split(), draft.split(), typed.split()
    bn, tn = _words(b), _words(t)
    # agreed up to the end of the last run of ≥2 shared words (or a shared first word), so one
    # hard word that keeps changing doesn't hold back the stable words after it
    n = max((m.b + m.size for m in _blocks(_words(a), bn) if m.size >= 2 or (m.size and m.a == m.b == 0)),
            default=0)
    if not t:
        return " ".join(b[:n])
    # where the typed text sits in the newest draft: its last run of ≥2 matching words (e, j = end in
    # typed, end in draft). Typed words after that run changed and are erased: normally only the last
    # one (e.g. its comma), rarely more ("Dips Ic." -> "Dipsik."); without this it would stay stuck.
    e = j = 0
    for m in reversed(_blocks(tn, bn)):
        if m.size >= min(2, len(t)):
            e, j = m.a + m.size, m.b + m.size
            break
    if e == len(t):                       # all typed words matched: still refresh the last one
        e, j = e - 1, j - 1
    if j >= n:
        return typed                      # nothing agreed past it yet: wait for the next draft
    return " ".join(t[:e] + b[j:n])
