"""cleanup.py - STT-Clean: LLM clean-up of dictated text + user glossary.

Two local servers, picked in the menu's LLM list: "ollama" (its own API: thinking off, model kept
loaded) and "lmstudio" (LM Studio's OpenAI-compatible API). Both are unloaded on exit.
The LLM pass handles what speech-to-text can't: self-corrections ("no cancella", "anzi",
"scratch that"), spoken formatting ("virgola", "a capo"), glossary spellings, and
instructions at the end of a dictation ("scrivilo in inglese").
Any failure (server down, timeout, implausible output) returns None so the caller
pastes the raw text instead. Only the standard library is used.
"""
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_LLM = "gemma4:12b-mlx"
SERVERS = {"ollama": ("Ollama", "http://127.0.0.1:11434"), "lmstudio": ("LM Studio", "http://127.0.0.1:1234/v1")}
NUM_CTX = 4096   # keep identical in every request, otherwise Ollama reloads the model

SYSTEM_PROMPT = """You clean up raw speech-to-text transcripts. The user dictated the text; you output the final text to paste.
Rules:
1. Output ONLY the final text. No quotes, no comments, no preamble.
2. Keep the user's words, language and style. Do NOT rephrase, summarize, answer, or add content. Keep a first word used as a heading or label ("Prompt", "Titolo", "Note").
3. Self-corrections: when the speaker retracts something ("no cancella", "cancella", "anzi", "no aspetta", "delete that", "scratch that", "actually no"), remove the retracted part and the correction phrase, keep only the corrected version.
4. Spoken formatting: replace the spoken command with the symbol and drop the command words (they never appear in the output): "punto" -> ".", "virgola" -> ",", "punto interrogativo" -> "?", "due punti" -> ":", "a capo" -> new line, "nuovo paragrafo" -> blank line. Same in English ("period", "comma", "new line", "new paragraph"). Only when clearly used as a command.
5. Fix spellings using the glossary below, including a common word that sounds like a glossary term when the context clearly means that name (e.g. "API di Cloud" -> "API di Claude"; but "senza cloud" stays).
6. Instructions addressed to you (e.g. "scrivilo in inglese", "write it in English", "traduci in inglese", "ora traducimi tutto questo in inglese") must be applied to the rest of the text (or only to the part they name, e.g. "solo la prossima frase traducimela" = only the next sentence), and the instruction removed together with the words addressing you just before it ("ok", "perfetto", a name you are called, like "Gemma" or "Gemini", also when corrected with "anzi"): "... come c'è scritto. Perfetto Gemini. Anzi Gemma, ora traducimi tutto questo in inglese." -> "... as it says." (all in English, nothing after it). Translating means the whole text in that language, not just the instruction.
7. If the text is a question or a request, do NOT answer it: it is text to be pasted, return it cleaned."""


# ---------------------------------------------------------------- glossary
class Glossary:
    """Terms from a text file, one per line:   Correct: heard as 1, heard as 2

    Lines starting with # are comments. "heard as" variants are replaced in code
    (case-insensitive, whole words) before the LLM sees the text; all terms are
    also listed in the LLM prompt. The file is re-read when it changes.
    """

    def __init__(self, path: str | None):
        self.path = path
        self.terms: list[tuple[str, list[str]]] = []
        self._mtime = None
        self._pattern = None
        self._lookup: dict[str, str] = {}
        self.maybe_reload()

    def maybe_reload(self) -> bool:
        if not self.path or not os.path.exists(self.path):
            changed, self.terms, self._mtime = bool(self.terms), [], None
        else:
            mtime = os.path.getmtime(self.path)
            if mtime == self._mtime:
                return False
            with open(self.path, encoding="utf-8") as f:
                self.terms, self._mtime, changed = parse_glossary(f.read()), mtime, True
        if changed:
            self._compile()
        return changed

    def _compile(self) -> None:
        self._lookup = {v.lower(): term for term, variants in self.terms for v in variants}
        if not self._lookup:
            self._pattern = None
            return
        alts = sorted(self._lookup, key=len, reverse=True)   # longest variant wins
        self._pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, alts)) + r")(?!\w)", re.IGNORECASE)

    def apply(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(lambda m: self._lookup[m.group(1).lower()], text)

    def prompt_block(self) -> str:
        lines = [f"{t} (heard as: {', '.join(v)})" if v else t for t, v in self.terms]
        return "\n".join(lines) if lines else "(empty)"


def parse_glossary(content: str) -> list[tuple[str, list[str]]]:
    terms = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, _, heard = line.partition(":")
        variants = [v.strip() for v in heard.split(",") if v.strip()]
        if term.strip():
            terms.append((term.strip(), variants))
    return terms


# ---------------------------------------------------------------- LLM
def plausible(raw: str, out: str) -> bool:
    """Reject outputs that look like the model answered or rambled instead of cleaning."""
    return bool(out) and len(out) <= 2 * len(raw) + 80


def strip_wrapping(raw: str, out: str) -> str:
    out = re.sub(r"^\s*<think>.*?</think>", "", out, flags=re.S).strip()   # reasoning models (Qwen3, ...)
    if out.startswith("```") and out.endswith("```"):
        out = out.strip("`").strip()
    for q in ('"', "“", "«"):
        closing = {"“": "”", "«": "»"}.get(q, q)
        if out.startswith(q) and out.endswith(closing) and not raw.lstrip().startswith(q):
            out = out[1:-1].strip()
    return out


class Cleaner:
    def __init__(self, model: str, url: str, glossary: Glossary, timeout: float = 3.0, provider: str = "ollama"):
        if provider not in SERVERS:
            raise ValueError(f'unknown LLM provider "{provider}": use {" or ".join(SERVERS)}')
        self.model, self.glossary, self.timeout, self.provider = model, glossary, timeout, provider
        self.label, default_url = SERVERS[provider]
        self.url = (url or default_url).rstrip("/")
        self.last_error = ""
        # thinking off (it would spend the output budget): reasoning_effort (OpenAI style) and
        # chat_template_kwargs (Qwen3 & co.). Dropped if the server rejects them.
        self.no_think = {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}

    def _post(self, path: str, body: dict | None, timeout: float, base: str = "") -> dict:
        """POST `body` as JSON (GET if None) to `base` (default: the server URL) + `path`, return the JSON reply."""
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request((base or self.url) + path, data, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def system_prompt(self) -> str:
        return f"{SYSTEM_PROMPT}\nGlossary:\n{self.glossary.prompt_block()}"

    def models(self, timeout: float) -> list[str]:
        """Names of the chat models on the server (raises if it doesn't answer)."""
        if self.provider == "ollama":
            names = [m["name"] for m in self._post("/api/tags", None, timeout).get("models", [])]
        else:
            names = [m["id"] for m in self._post("/models", None, timeout).get("data", [])]
        return sorted((n for n in names if "embed" not in n.lower()), key=str.lower)   # embedding models can't chat

    def check(self) -> str | None:
        """Return a warning if the server is unreachable or doesn't have the model."""
        try:
            names = set(self.models(timeout=5))
        except Exception as e:
            return f"{self.label} isn't running ({e}). Start it, or turn Smart clean-up off in the menu."
        if self.model not in names and f"{self.model}:latest" not in names:
            return f"'{self.model}' isn't in {self.label}: pick a model in the menu's LLM list."
        return None

    def clean(self, raw: str, timeout: float | None = None) -> str | None:
        """Cleaned text, or None on any failure (caller falls back to raw)."""
        self.glossary.maybe_reload()
        messages = [{"role": "system", "content": self.system_prompt()}, {"role": "user", "content": raw}]
        budget = len(raw) // 2 + 64                     # output tokens: enough for the text, not for an essay
        try:
            if self.provider == "ollama":
                d = self._post("/api/chat", {
                    "model": self.model, "stream": False, "think": False, "keep_alive": -1, "messages": messages,
                    "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": budget},
                }, timeout=timeout or self.timeout + len(raw) / 40)
                reply, end = d["message"]["content"], d.get("done_reason")
            else:
                body = {"model": self.model, "temperature": 0, "max_tokens": budget, "messages": messages}
                try:
                    d = self._post("/chat/completions", {**body, **self.no_think}, timeout or self.timeout + len(raw) / 40)
                except urllib.error.HTTPError as e:
                    if e.code != 400 or not self.no_think:
                        raise
                    d = self._post("/chat/completions", body, timeout or self.timeout + len(raw) / 40)
                    self.no_think = {}                  # the plain request worked: a strict server, plain from now on
                reply, end = d["choices"][0]["message"]["content"], d["choices"][0].get("finish_reason")
            if end == "length":                         # hit the budget: the end of the text is missing
                raise ValueError("output cut off")
            out = strip_wrapping(raw, reply)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None
        if not plausible(raw, out):
            self.last_error = f"implausible output ignored: {out[:80]!r}"
            return None
        return out

    def warm_up(self) -> bool:
        """Load the model (cold load can take ~10 s) and prime its prompt cache; True if it worked."""
        return self.clean("Prova.", timeout=60) is not None

    def unload(self) -> None:
        """Free the model's RAM: Ollama's keep_alive 0, or LM Studio's own REST API."""
        try:
            if self.provider == "ollama":
                self._post("/api/generate", {"model": self.model, "keep_alive": 0}, timeout=3)
                return
            # shortcut: assumes LM Studio's JIT loading (its default) to load the model again when used
            root = self.url.removesuffix("/v1")
            for m in self._post("/api/v1/models", None, 3, root).get("models", []):
                if m.get("key") == self.model:
                    for instance in m.get("loaded_instances", []):
                        self._post("/api/v1/models/unload", {"instance_id": instance["id"]}, 10, root)
        except Exception:                               # server gone: nothing to free
            pass



def available() -> list[tuple[str, str, list[str]]]:
    """(label, provider, models) for each local LLM server that answers now (Ollama, LM Studio).
    Their models are a click away in the menu's LLM list."""
    found = []
    for provider, (label, url) in SERVERS.items():
        try:
            names = Cleaner("", url, Glossary(None), provider=provider).models(timeout=1)
        except Exception:                          # not running: nothing to offer
            continue
        if names:
            found.append((label, provider, names))
    return found
