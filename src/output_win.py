"""output_win.py - putting text into the focused app on Windows: keystrokes, the focus check, clipboard and Ctrl+V.

The counterpart of output.py, same functions. Windows asks for no permission, with one silent exception:
keys sent by a normal program never reach an app running as administrator (blocked() tells).
"""
import ctypes
import threading
import time
import winreg

import win32 as W
from live import diff

OWNER = None              # the tray's hidden window: it owns the clipboard and renders our text (set by tray_win)
MODIFIERS = (W.VK_SHIFT, W.VK_CONTROL, W.VK_MENU, W.VK_LWIN, W.VK_RWIN)
CAN_HISTORY = W.RegisterClipboardFormatW("CanIncludeInClipboardHistory")   # 0: kept out of Win+V's history
CAN_CLOUD = W.RegisterClipboardFormatW("CanUploadToCloudClipboard")         # 0: not synced to other PCs
# handles that aren't memory blocks (GDI objects, owner-drawn): not copied by clipboard_items(); an image
# still comes back, as the CF_DIB Windows keeps next to CF_BITMAP
NOT_MEMORY = {W.CF_BITMAP, W.CF_METAFILEPICT, W.CF_PALETTE, W.CF_ENHMETAFILE, W.CF_OWNERDISPLAY, W.CF_DSPBITMAP,
              W.CF_DSPMETAFILEPICT, W.CF_DSPENHMETAFILE, *range(W.CF_GDIOBJFIRST, W.CF_GDIOBJLAST + 1)}


# ---------------------------------------------------------------- keystrokes
def _key(vk: int = 0, unit: int = 0, up: bool = False) -> W.INPUT:
    flags = (W.KEYEVENTF_UNICODE if unit else 0) | (W.KEYEVENTF_KEYUP if up else 0)
    return W.INPUT(type=W.INPUT_KEYBOARD, u=W._INPUTUNION(ki=W.KEYBDINPUT(wVk=vk, wScan=unit, dwFlags=flags)))


def keystrokes(text: str = "", backspaces: int = 0) -> list:
    """Key down + up events: `backspaces` x Backspace, then `text` as Unicode characters (one event pair
    per UTF-16 unit, so emoji and accents need no keyboard layout); a new line is the Enter key."""
    events = [_key(W.VK_BACK, up=up) for _ in range(backspaces) for up in (False, True)]
    for ch in text:
        if ch == "\n":
            events += [_key(W.VK_RETURN), _key(W.VK_RETURN, up=True)]
            continue
        units = ch.encode("utf-16-le")
        for i in range(0, len(units), 2):
            unit = int.from_bytes(units[i:i + 2], "little")
            events += [_key(unit=unit), _key(unit=unit, up=True)]
    return events


def send(events: list) -> None:
    """One SendInput call: the user's own typing can't land in the middle of ours."""
    if events:
        W.SendInput(len(events), (W.INPUT * len(events))(*events), ctypes.sizeof(W.INPUT))


def retype(old: str, new: str) -> None:
    """The app shows `old` (typed by us): erase its changed tail and type the rest of `new`."""
    erase, add = diff(old, new)
    send(keystrokes(add, erase))


# ---------------------------------------------------------------- where the keystrokes land
def focus() -> tuple:
    """Where our keystrokes land: (foreground app pid, its window, its focused control).
    A part Windows doesn't report is None."""
    hwnd = W.GetForegroundWindow()
    pid = W.w.DWORD()
    thread = W.GetWindowThreadProcessId(hwnd, W.byref(pid)) if hwnd else 0
    info = W.GUITHREADINFO(cbSize=ctypes.sizeof(W.GUITHREADINFO))
    # shortcut: like on macOS, Chrome and Electron apps (VS Code) report one control for the whole
    # window, so a tab switch inside one of their windows isn't seen
    field = info.hwndFocus if thread and W.GetGUIThreadInfo(thread, W.byref(info)) else None
    return pid.value, hwnd or None, field or None


def held() -> bool:
    """A modifier is down: Windows would add it to our keys (a typed letter becomes Ctrl+A)."""
    return any(W.GetAsyncKeyState(vk) & 0x8000 for vk in MODIFIERS)


def can_post(target: tuple, wait: float = 0) -> bool:
    """True if the focus is still `target` (same app, window and control) and no modifier is held,
    waiting up to `wait` s for the user to let go."""
    end = time.monotonic() + wait
    while held() and time.monotonic() < end:
        time.sleep(0.05)
    return not held() and focus() == target


def blocked(target: tuple) -> bool:
    """`target` runs as administrator and we don't: Windows drops our keys there without an error."""
    return bool(target[0]) and W.elevated(target[0]) is True and W.elevated(0) is False


# ---------------------------------------------------------------- clipboard and paste
class _Offer:
    """Clipboard text handed out on demand (Windows' delayed rendering): Windows asks our window for it
    (WM_RENDERFORMAT, on the tray's thread) when a program reads it. Only the processes in `readers` get
    it, and their read sets `read`: programs that read every clipboard change (WSL's and Remote Desktop's
    clipboard sync, clipboard managers) read before the app's Ctrl+V and would pass for the paste. Refused,
    they get no text and it stays on offer for the app."""
    def __init__(self, text: str, readers: set):
        self.data, self.readers, self.read = _utf16(text), readers, threading.Event()


PENDING = None            # the _Offer on the clipboard now, if any


def _utf16(text: str) -> bytes:
    return (text + "\0").encode("utf-16-le")


def _memory(data: bytes):
    h = W.GlobalAlloc(W.GMEM_MOVEABLE, max(len(data), 1))
    ctypes.memmove(W.GlobalLock(h), data, len(data))
    W.GlobalUnlock(h)
    return h


def _open() -> bool:
    """Another program may hold the clipboard for a moment (a clipboard manager, Win+V): retry for 1 s."""
    for _ in range(40):
        if W.OpenClipboard(OWNER):
            return True
        time.sleep(0.025)
    return False


def pid_of(hwnd) -> int:
    pid = W.w.DWORD()
    if hwnd:
        W.GetWindowThreadProcessId(hwnd, W.byref(pid))
    return pid.value


def render(fmt: int) -> None:
    """WM_RENDERFORMAT: a program reads the clipboard text we offered. The clipboard is open (by the reader)."""
    offer = PENDING
    if not offer or fmt != W.CF_UNICODETEXT:
        return
    reader = W.GetOpenClipboardWindow()
    # shortcut: a reader that opened the clipboard without a window can't be told apart: it counts as the paste
    if reader and pid_of(reader) not in offer.readers:
        return                             # not the app we type into: no text for it, still on offer
    W.SetClipboardData(W.CF_UNICODETEXT, _memory(offer.data))
    offer.read.set()


def render_all() -> None:
    """WM_RENDERALLFORMATS: we're quitting with an offer pending; leave the text for real."""
    if PENDING and _open():
        W.SetClipboardData(W.CF_UNICODETEXT, _memory(PENDING.data))
        W.CloseClipboard()


def _write(items: list, offer: _Offer | None = None, history: bool = True) -> bool:
    """Replace the clipboard with `items` [(format, bytes)], or with `offer` (text rendered on demand).
    history=False keeps it out of Win+V's history and the cloud clipboard."""
    global PENDING
    if not _open():
        return False
    try:
        W.EmptyClipboard()                 # makes OWNER the clipboard owner (it gets WM_RENDERFORMAT)
        PENDING = offer
        if offer:
            W.SetClipboardData(W.CF_UNICODETEXT, None)
        for fmt, data in items:
            W.SetClipboardData(fmt, _memory(data))
        if not history:
            for fmt in (CAN_HISTORY, CAN_CLOUD):
                W.SetClipboardData(fmt, _memory((0).to_bytes(4, "little")))
        return True
    finally:
        W.CloseClipboard()


def copy(text: str) -> None:
    _write([(W.CF_UNICODETEXT, _utf16(text))])


def clipboard_items() -> list:
    """A copy of everything on the clipboard that is a memory block: text, rich text, HTML, files, images."""
    items = []
    if not _open():
        return items
    try:
        fmt = W.EnumClipboardFormats(0)
        while fmt:
            if fmt not in NOT_MEMORY and (h := W.GetClipboardData(fmt)) and (size := W.GlobalSize(h)):
                if p := W.GlobalLock(h):
                    items.append((fmt, ctypes.string_at(p, size)))
                    W.GlobalUnlock(h)
            fmt = W.EnumClipboardFormats(fmt)
    finally:
        W.CloseClipboard()
    return items


def history_on() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Clipboard") as k:
            return bool(winreg.QueryValueEx(k, "EnableClipboardHistory")[0])
    except OSError:
        return False


def paste(text: str, typed: str, target: tuple) -> bool:
    """Replace the live draft `typed` with `text` (erase the changed tail, paste the rest with Ctrl+V) in
    `target` (focus()), then restore the old clipboard once that app has read it, as output.paste() does
    on macOS. False if it never read it: the text is then left on the clipboard for a manual Ctrl+V."""
    global PENDING
    erase, text = diff(typed, text)
    send(keystrokes(backspaces=erase))
    if not text:
        return True
    old = clipboard_items()
    if history_on():
        # the dictated text joins Win+V's history like anything you copy: put it there first, as plain
        # text; the offer for the paste below is kept out of the history (else a second entry)
        _write([(W.CF_UNICODETEXT, _utf16(text))])
        time.sleep(0.3)                    # the history service takes its copy on the clipboard change
    # the app's process, and the focused control's (a different one for Store apps hosted in a frame)
    offer = _Offer(text, {target[0], pid_of(target[2])} - {0})
    _write([], offer, history=False)
    send([_key(W.VK_CONTROL), _key(W.VK_V), _key(W.VK_V, up=True), _key(W.VK_CONTROL, up=True)])
    if not offer.read.wait(10 + erase / 50):
        PENDING = None
        _write([(W.CF_UNICODETEXT, _utf16(text))], history=False)   # as plain data, for a manual Ctrl+V
        return False
    time.sleep(0.2)                        # let the data reach the app before the clipboard changes again
    PENDING = None
    _write(old, history=False)             # back as it was, without a second history entry
    return True
