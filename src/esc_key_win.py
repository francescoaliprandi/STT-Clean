"""esc_key_win.py - Esc as a global hot key while recording (cancels the dictation), on Windows.

The counterpart of esc_key.py: RegisterHotKey reaches us in any app, swallows the key there and needs no
permission, like Carbon's RegisterEventHotKey. Windows delivers it as WM_HOTKEY to the tray's window,
which calls pressed(). Tray thread only; on() only while recording."""
import win32 as W

HOTKEY_ID = 1


class EscKey:
    def __init__(self, hwnd, pressed):
        self.hwnd, self.pressed, self.registered = hwnd, pressed, False

    def on(self) -> bool:
        self.registered = bool(W.RegisterHotKey(self.hwnd, HOTKEY_ID, 0, W.VK_ESCAPE))
        return self.registered             # fails if another app already holds plain Esc

    def off(self) -> None:
        if self.registered:
            W.UnregisterHotKey(self.hwnd, HOTKEY_ID)
            self.registered = False
