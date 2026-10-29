"""win32.py - the Windows API calls the Windows modules use, declared once with ctypes (no pywin32).

Every function gets argtypes / restype: ctypes' default int would truncate 64-bit handles and pointers.
"""
import ctypes
from ctypes import POINTER, Structure, Union, WINFUNCTYPE, byref, sizeof  # noqa: F401 (re-exported)
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
WINEVENTPROC = WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)

# ---------------------------------------------------------------- constants
WM_DESTROY, WM_CLOSE, WM_TIMER, WM_COMMAND, WM_NULL = 0x0002, 0x0010, 0x0113, 0x0111, 0x0000
WM_HOTKEY, WM_LBUTTONUP, WM_RBUTTONUP, WM_APP = 0x0312, 0x0202, 0x0205, 0x8000
WM_RENDERFORMAT, WM_RENDERALLFORMATS, WM_DESTROYCLIPBOARD = 0x0305, 0x0306, 0x0307
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_SHOWTIP = 0x01, 0x02, 0x04, 0x80
MF_STRING, MF_POPUP, MF_SEPARATOR, MF_GRAYED, MF_CHECKED = 0x0, 0x10, 0x800, 0x1, 0x8
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x0002, 0x0100, 0x0080
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
SM_CXSMICON = 49
MB_OK, MB_ICONINFORMATION = 0x0, 0x40
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x0002, 0x0004
VK_BACK, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_ESCAPE, VK_V = (
    0x08, 0x0D, 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x1B, 0x56)
CF_UNICODETEXT, CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE = 13, 2, 3, 9, 14
CF_OWNERDISPLAY, CF_DSPBITMAP, CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE = 0x80, 0x82, 0x83, 0x8E
CF_GDIOBJFIRST, CF_GDIOBJLAST = 0x300, 0x3FF
GMEM_MOVEABLE = 0x0002
EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 0x0003, 0x0000
PROCESS_QUERY_LIMITED_INFORMATION, TOKEN_QUERY, TokenElevation = 0x1000, 0x0008, 20
ERROR_ALREADY_EXISTS = 183
HWND_MESSAGE = w.HWND(-3)


# ---------------------------------------------------------------- structures
class GUID(Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", w.BYTE * 8)]


class NOTIFYICONDATAW(Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", w.HICON)]


class WNDCLASSEXW(Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR),
                ("hIconSm", w.HICON)]


class MOUSEINPUT(Structure):     # only here so that INPUT has the size SendInput expects (40 bytes on x64)
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(Structure):
    _fields_ = [("cbSize", w.DWORD), ("flags", w.DWORD), ("hwndActive", w.HWND), ("hwndFocus", w.HWND),
                ("hwndCapture", w.HWND), ("hwndMenuOwner", w.HWND), ("hwndMoveSize", w.HWND),
                ("hwndCaret", w.HWND), ("rcCaret", w.RECT)]


# ---------------------------------------------------------------- functions
def _decl(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype, f.argtypes = restype, list(argtypes)
    return f


RegisterClassExW = _decl(user32, "RegisterClassExW", w.ATOM, POINTER(WNDCLASSEXW))
CreateWindowExW = _decl(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int,
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
DefWindowProcW = _decl(user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
DestroyWindow = _decl(user32, "DestroyWindow", w.BOOL, w.HWND)
GetMessageW = _decl(user32, "GetMessageW", w.BOOL, POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
TranslateMessage = _decl(user32, "TranslateMessage", w.BOOL, POINTER(w.MSG))
DispatchMessageW = _decl(user32, "DispatchMessageW", LRESULT, POINTER(w.MSG))
PostMessageW = _decl(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
PostQuitMessage = _decl(user32, "PostQuitMessage", None, ctypes.c_int)
RegisterWindowMessageW = _decl(user32, "RegisterWindowMessageW", w.UINT, w.LPCWSTR)
SetTimer = _decl(user32, "SetTimer", ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID)
KillTimer = _decl(user32, "KillTimer", w.BOOL, w.HWND, ctypes.c_size_t)
CreatePopupMenu = _decl(user32, "CreatePopupMenu", w.HMENU)
AppendMenuW = _decl(user32, "AppendMenuW", w.BOOL, w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR)
TrackPopupMenu = _decl(user32, "TrackPopupMenu", w.BOOL, w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       w.HWND, w.LPVOID)
DestroyMenu = _decl(user32, "DestroyMenu", w.BOOL, w.HMENU)
GetCursorPos = _decl(user32, "GetCursorPos", w.BOOL, POINTER(w.POINT))
LoadImageW = _decl(user32, "LoadImageW", w.HANDLE, w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT)
DestroyIcon = _decl(user32, "DestroyIcon", w.BOOL, w.HICON)
GetSystemMetrics = _decl(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
MessageBoxW = _decl(user32, "MessageBoxW", ctypes.c_int, w.HWND, w.LPCWSTR, w.LPCWSTR, w.UINT)
SetForegroundWindow = _decl(user32, "SetForegroundWindow", w.BOOL, w.HWND)
GetForegroundWindow = _decl(user32, "GetForegroundWindow", w.HWND)
GetWindowThreadProcessId = _decl(user32, "GetWindowThreadProcessId", w.DWORD, w.HWND, POINTER(w.DWORD))
GetGUIThreadInfo = _decl(user32, "GetGUIThreadInfo", w.BOOL, w.DWORD, POINTER(GUITHREADINFO))
GetClassNameW = _decl(user32, "GetClassNameW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
IsWindow = _decl(user32, "IsWindow", w.BOOL, w.HWND)
SetWinEventHook = _decl(user32, "SetWinEventHook", w.HANDLE, w.DWORD, w.DWORD, w.HMODULE, WINEVENTPROC, w.DWORD,
                        w.DWORD, w.DWORD)
UnhookWinEvent = _decl(user32, "UnhookWinEvent", w.BOOL, w.HANDLE)
RegisterHotKey = _decl(user32, "RegisterHotKey", w.BOOL, w.HWND, ctypes.c_int, w.UINT, w.UINT)
UnregisterHotKey = _decl(user32, "UnregisterHotKey", w.BOOL, w.HWND, ctypes.c_int)
SendInput = _decl(user32, "SendInput", w.UINT, w.UINT, POINTER(INPUT), ctypes.c_int)
GetAsyncKeyState = _decl(user32, "GetAsyncKeyState", w.SHORT, ctypes.c_int)
OpenClipboard = _decl(user32, "OpenClipboard", w.BOOL, w.HWND)
CloseClipboard = _decl(user32, "CloseClipboard", w.BOOL)
EmptyClipboard = _decl(user32, "EmptyClipboard", w.BOOL)
SetClipboardData = _decl(user32, "SetClipboardData", w.HANDLE, w.UINT, w.HANDLE)
GetClipboardData = _decl(user32, "GetClipboardData", w.HANDLE, w.UINT)
EnumClipboardFormats = _decl(user32, "EnumClipboardFormats", w.UINT, w.UINT)
RegisterClipboardFormatW = _decl(user32, "RegisterClipboardFormatW", w.UINT, w.LPCWSTR)
GetOpenClipboardWindow = _decl(user32, "GetOpenClipboardWindow", w.HWND)
SetProcessDpiAwarenessContext = _decl(user32, "SetProcessDpiAwarenessContext", w.BOOL, w.HANDLE)

GetModuleHandleW = _decl(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
GlobalAlloc = _decl(kernel32, "GlobalAlloc", w.HGLOBAL, w.UINT, ctypes.c_size_t)
GlobalLock = _decl(kernel32, "GlobalLock", w.LPVOID, w.HGLOBAL)
GlobalUnlock = _decl(kernel32, "GlobalUnlock", w.BOOL, w.HGLOBAL)
GlobalSize = _decl(kernel32, "GlobalSize", ctypes.c_size_t, w.HGLOBAL)
GlobalFree = _decl(kernel32, "GlobalFree", w.HGLOBAL, w.HGLOBAL)
CreateMutexW = _decl(kernel32, "CreateMutexW", w.HANDLE, w.LPVOID, w.BOOL, w.LPCWSTR)
OpenProcess = _decl(kernel32, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
GetCurrentProcess = _decl(kernel32, "GetCurrentProcess", w.HANDLE)
CloseHandle = _decl(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
OpenProcessToken = _decl(advapi32, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, POINTER(w.HANDLE))
GetTokenInformation = _decl(advapi32, "GetTokenInformation", w.BOOL, w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD,
                            POINTER(w.DWORD))
Shell_NotifyIconW = _decl(shell32, "Shell_NotifyIconW", w.BOOL, w.DWORD, POINTER(NOTIFYICONDATAW))


def class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def elevated(pid: int) -> bool | None:
    """True if process `pid` (0: this one) runs as administrator, None if it can't be asked."""
    proc = GetCurrentProcess() if pid == 0 else OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not proc:
        return None
    token, value, size = w.HANDLE(), w.DWORD(), w.DWORD()
    try:
        if not OpenProcessToken(proc, TOKEN_QUERY, byref(token)):
            return None
        ok = GetTokenInformation(token, TokenElevation, byref(value), sizeof(value), byref(size))
        CloseHandle(token)
        return bool(value.value) if ok else None
    finally:
        if pid:
            CloseHandle(proc)
