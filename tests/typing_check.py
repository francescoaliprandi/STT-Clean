"""Check that live-draft keystrokes arrive intact: replays a heavy draft-churn sequence into a new
TextEdit document with retype(), then reads the document back. Hands off the keyboard for ~15 s.
Run it from the terminal that runs stt-clean (it needs that app's Accessibility permission):

    python tests/typing_check.py [pause_seconds]
"""
import os, random, subprocess, sys, time
from AppKit import NSWorkspace
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from output import retype

def front():
    return NSWorkspace.sharedWorkspace().frontmostApplication().bundleIdentifier()

def osa(s):
    return subprocess.run(["osascript", "-e", s], capture_output=True, text=True).stdout.rstrip("\n")

TEXT = 'Proviamo a registrare qualcosa. Alcune proteine rivestono precise funzioni biologiche nel plasma: nutritiva, tampone, coagulazione e fibrinolisi, difesa, trasporto, mantenimento della pressione colloidosmotica. Proteine con prevalente funzione di reazione dello stato infiammatorio. Domani devo ripassare il capitolo sulle lipoproteine e preparare le slide per il seminario di giovedì. Poi devo scrivere a Marco per chiedergli gli appunti della lezione di martedì, perché non sono riuscito a seguirla tutta, e controllare le date degli esami sul sito del dipartimento.'
pause = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
osa('tell application "TextEdit" to activate')
osa('tell application "TextEdit" to make new document')
time.sleep(1.5)
random.seed(1)
shown = ""
for k in range(10, len(TEXT), len(TEXT) // 40):
    tail = random.randint(0, 90)
    draft = TEXT[:max(0, k - tail)] + "".join(random.choice("abcdeèàù ,.") for _ in range(tail))
    if front() != "com.apple.TextEdit":
        sys.exit(f"aborted: front app is {front()}")
    retype(shown, draft); shown = draft
    time.sleep(pause)
retype(shown, TEXT); shown = TEXT
time.sleep(1.5)
got = osa('tell application "TextEdit" to get text of front document')
print("MATCH" if got == TEXT else f"MISMATCH\nexpected: {TEXT!r}\ngot:      {got!r}")
