"""Windows version of typing_check.py: checks that live-draft keystrokes and the final paste arrive intact.
Replays a heavy draft-churn sequence into a new Notepad window with retype(), pastes the final text with
paste() (delayed rendering + clipboard restore), then reads Notepad back and checks the clipboard came back.
Hands off the keyboard for ~15 s; stops if Notepad loses the focus.

    python tests/typing_check_win.py [pause_seconds]
"""
import ctypes, os, random, subprocess, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import output_win as O  # noqa: E402
import win32 as W  # noqa: E402

TEXT = 'Proviamo a registrare qualcosa. Alcune proteine rivestono precise funzioni biologiche nel plasma: nutritiva, tampone, coagulazione e fibrinolisi, difesa, trasporto, mantenimento della pressione colloidosmotica. Proteine con prevalente funzione di reazione dello stato infiammatorio. Domani devo ripassare il capitolo sulle lipoproteine e preparare le slide per il seminario di giovedì. Poi devo scrivere a Marco per chiedergli gli appunti della lezione di martedì, perché non sono riuscito a seguirla tutta, e controllare le date degli esami sul sito del dipartimento.'
FINAL = TEXT + " Fine. ✓"           # the paste: the draft's tail replaced, plus non-ASCII text
pause = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
SendMessageW = W._decl(W.user32, "SendMessageW", W.LRESULT, W.w.HWND, W.w.UINT, W.w.WPARAM, W.w.LPVOID)
ENUM = ctypes.WINFUNCTYPE(W.w.BOOL, W.w.HWND, W.w.LPARAM)
EnumChildWindows = W._decl(W.user32, "EnumChildWindows", W.w.BOOL, W.w.HWND, ENUM, W.w.LPARAM)


def editor(hwnd):
    """Notepad's text control, at any depth: RichEditD2DPT (Windows 11) or Edit (classic Notepad)."""
    found = []
    EnumChildWindows(hwnd, ENUM(lambda h, _: not (W.class_name(h) in ("RichEditD2DPT", "Edit") and found.append(h))), 0)
    return found[0] if found else None


def text_of(ctrl) -> str:
    n = SendMessageW(ctrl, WM_GETTEXTLENGTH, 0, None)
    buf = ctypes.create_unicode_buffer(n + 1)
    SendMessageW(ctrl, WM_GETTEXT, n + 1, buf)
    return buf.value.replace("\r\n", "\n").replace("\r", "\n")


def check(hwnd) -> None:
    try:
        target = None
        proc = subprocess.Popen(["notepad.exe"])
        for _ in range(50):                                    # its window, in front
            time.sleep(0.2)
            fg = W.GetForegroundWindow()
            if fg and W.class_name(fg) == "Notepad":
                target = O.focus()
                break
        if not target:
            sys.exit("aborted: Notepad didn't come to the front")
        time.sleep(1)
        target = O.focus()
        O._write([(W.CF_UNICODETEXT, O._utf16("clipboard before the check"))], history=False)
        random.seed(1)
        shown = ""
        for k in range(10, len(TEXT), len(TEXT) // 40):
            tail = random.randint(0, 90)
            draft = TEXT[:max(0, k - tail)] + "".join(random.choice("abcdeèàù ,.") for _ in range(tail))
            if not O.can_post(target, wait=1):
                sys.exit(f"aborted: the focus moved to {W.class_name(W.GetForegroundWindow())}")
            O.retype(shown, draft)
            shown = draft
            time.sleep(pause)
        pasted = O.paste(FINAL, shown, target)
        time.sleep(1.5)
        got = text_of(editor(W.GetForegroundWindow()))
        clip = O.clipboard_items()
        restored = any(f == W.CF_UNICODETEXT and d.decode("utf-16-le").rstrip("\0") == "clipboard before the check"
                       for f, d in clip)
        print("paste read by Notepad:", pasted)
        print("text:", "MATCH" if got == FINAL else f"MISMATCH\nexpected: {FINAL!r}\ngot:      {got!r}")
        print("clipboard restored:", restored)
    finally:
        W.PostMessageW(hwnd, W.WM_CLOSE, 0, 0)


if __name__ == "__main__":
    # the window that owns the clipboard and renders the pasted text, as the tray's does in the app
    def proc(h, m, wp, lp):
        if m == W.WM_RENDERFORMAT:
            O.render(wp)
            return 0
        return W.DefWindowProcW(h, m, wp, lp)
    wndproc = W.WNDPROC(proc)
    hinst = W.GetModuleHandleW(None)
    wc = W.WNDCLASSEXW(cbSize=ctypes.sizeof(W.WNDCLASSEXW), lpfnWndProc=wndproc, hInstance=hinst,
                       lpszClassName="STT-Clean typing check")
    W.RegisterClassExW(ctypes.byref(wc))
    O.OWNER = W.CreateWindowExW(0, "STT-Clean typing check", "", 0, 0, 0, 0, 0, None, None, hinst, None)
    threading.Thread(target=check, args=(O.OWNER,), daemon=True).start()
    msg = W.w.MSG()
    while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0 and msg.message != W.WM_CLOSE:
        W.TranslateMessage(ctypes.byref(msg))
        W.DispatchMessageW(ctypes.byref(msg))
