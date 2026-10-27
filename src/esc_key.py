"""esc_key.py - Esc as a global hot key while recording (cancels the dictation)."""
import ctypes

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class _HotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventType(ctypes.Structure):
    _fields_ = [("cls", ctypes.c_uint32), ("kind", ctypes.c_uint32)]


_carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
_carbon.InstallEventHandler.argtypes = [ctypes.c_void_p, _HANDLER, ctypes.c_ulong, ctypes.POINTER(_EventType),
                                        ctypes.c_void_p, ctypes.c_void_p]
_carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, _HotKeyID, ctypes.c_void_p,
                                        ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
_carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
ESC_KEYCODE = 53


class EscKey:
    """Esc as a global hot key (Carbon RegisterEventHotKey): reaches us in any app, is swallowed there and needs
    no permission (a keyboard event tap would need Input Monitoring). Main thread only; on() only while recording."""

    def __init__(self, pressed):
        self.target = _carbon.GetApplicationEventTarget()
        self.handler = _HANDLER(lambda *_: pressed() or 0)   # kept referenced: Carbon only holds the pointer
        kind = _EventType(int.from_bytes(b"keyb", "big"), 5)  # kEventClassKeyboard, kEventHotKeyPressed
        _carbon.InstallEventHandler(self.target, self.handler, 1, ctypes.byref(kind), None, None)
        self.ref = None

    def on(self) -> bool:
        ref = ctypes.c_void_p()
        err = _carbon.RegisterEventHotKey(ESC_KEYCODE, 0, _HotKeyID(int.from_bytes(b"sttc", "big"), 1),
                                          self.target, 0, ctypes.byref(ref))
        self.ref = ref if err == 0 else None
        return err == 0                    # fails if another app already holds plain Esc

    def off(self) -> None:
        if self.ref:
            _carbon.UnregisterEventHotKey(self.ref)
            self.ref = None
