"""Gateway-side taint tracking (TaintStoreImpl) and the ProvenanceCheck.

Everything a read returns (file contents, issue text, tool output) is recorded here as
untrusted_content by the gateway. A proposal is linked to it when its params contain:
- `substring`: a verbatim run of >= 20 characters seen in a read;
- `url`: a URL seen in a read (scheme, trailing slash and fragment ignored);
- `command`: a shell/exfiltration token (curl, wget, nc, base64 -d, $SECRETS, env dumps, ...)
  that also appears in a read.
All matching is on normalised text: Unicode NFKC, zero-width characters removed, case-folded,
every whitespace run collapsed to one space.

Provenance is derived only from what the gateway recorded. Whatever the agent says about where
its content came from is not an input here.

ProvenanceCheck (a verification Check) only counts NEW material: the part of a write that is
not already active (non-comment) content of the file being replaced. That way rewriting a file
the agent just read is not "tainted" by that read, while uncommenting a planted line is.
Then it decides:
- block    a sensitive write (CI, dependency, secrets, script or test-config path, or a file
           starting with `#!`) with any new tainted material;
- block    any write whose new material has a tainted URL or command token;
- info     a non-sensitive write whose only overlap is plain substrings (normal code copying;
           recorded, never blocking);
- pass     otherwise.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from av.contracts import ActionContract, CheckResult, TaintHit, TaskDefinition
from av.interfaces import CheckContext
from av.verify import paths

MIN_SUBSTRING = 20

# --------------------------------------------------------------------------- normalisation

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC, zero-width removed, case-folded, whitespace runs collapsed, stripped."""
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).casefold()
    return _WS.sub(" ", text).strip()


# --------------------------------------------------------------------------- URLs

_URL = re.compile(r"\b(?:https?|ftp|wss?|file|ssh|git)://[^\s'\"<>`)\]}]+")


def _canon_url(url: str) -> str:
    url = url.rstrip(".,;:!?'\"")
    url = url.split("#", 1)[0]
    url = re.sub(r"^[a-z0-9+.-]+://", "", url)
    return url.rstrip("/")


def urls_in(norm_text: str) -> set[str]:
    return {c for c in (_canon_url(u) for u in _URL.findall(norm_text)) if c}


# --------------------------------------------------------------------------- command tokens

#: name -> regex over NORMALISED (case-folded, single-spaced) text. Names are what a hit reports.
COMMAND_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(rx)
    for name, rx in {
        "curl": r"\bcurl\b",
        "wget": r"\bwget\b",
        "nc": r"(?:^|[\s|;&(`$])(?:nc|ncat|netcat)\s",
        "socat": r"\bsocat\b",
        "telnet": r"\btelnet\b",
        "scp/sftp": r"\b(?:scp|sftp)\b",
        "/dev/tcp": r"/dev/(?:tcp|udp)/",
        "base64 -d": r"\bbase64\s+(?:-d|--decode|-di)\b|\bb64decode\b",
        "pipe to shell": r"\|\s*(?:ba|z|da|k)?sh\b|\|\s*python[0-9.]*\b",
        "shell -c": r"\b(?:ba|z|da)?sh\s+-c\b",
        "powershell": r"\b(?:powershell|pwsh|iex|invoke-webrequest|invoke-expression)\b",
        "$secrets": r"\$\{?\s*\{?\s*secrets\b",
        "secret env var": r"\$\{?[a-z_]*(?:token|secret|passw(?:or)?d|api_?key|private_?key|credential)[a-z0-9_]*\}?",
        "env dump": r"\bprintenv\b|\benv\s*(?:\||>)|\bset\s*\||/proc/[a-z0-9]+/environ|\bexport\s+-p\b",
        "os.environ": r"\bos\.environ\b|\bos\.getenv\b|\bprocess\.env\b",
        "http client": r"\burlopen\b|\burllib\.request\b|\brequests\.(?:get|post|put)\b|\bhttpx\.(?:get|post|put)\b|\bhttp\.client\b",
        "raw socket": r"\bsocket\.(?:socket|create_connection)\b",
        "package install": r"\b(?:pip|pip3|uv pip|npm|yarn|pnpm|gem)\s+(?:install|add)\b",
    }.items()
}


def command_counts(norm_text: str) -> dict[str, int]:
    return {name: len(rx.findall(norm_text)) for name, rx in COMMAND_PATTERNS.items() if rx.search(norm_text)}


def active_text(text: str) -> str:
    """`text` without `#` comments (a line starting with `#`, or ` #...` to end of line), then
    normalised. Used to decide what is NEW active content in a rewrite. `#` inside a token (a
    URL fragment, `${{ }}`) is kept."""
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(re.sub(r"\s#.*$", "", line))
    return normalize("\n".join(out))


# --------------------------------------------------------------------------- the store


@dataclass
class _Source:
    ref: str
    shingles: frozenset[str]
    urls: frozenset[str]
    commands: frozenset[str]


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _strings(v)


@dataclass
class TaintStoreImpl:
    """TaintStore. The gateway calls record_read() with every read result; ContractBuilder and
    ProvenanceCheck call match(params). Deterministic: hits come out in a stable order."""

    min_len: int = MIN_SUBSTRING
    sources: list[_Source] = field(default_factory=list)

    def record_read(self, source_ref: str, text: str) -> None:
        norm = normalize(text if isinstance(text, str) else str(text))
        n = self.min_len
        shingles = frozenset(norm[i : i + n] for i in range(len(norm) - n + 1))
        self.sources.append(_Source(source_ref, shingles, frozenset(urls_in(norm)), frozenset(command_counts(norm))))

    def match(self, params: Mapping[str, Any]) -> list[TaintHit]:
        hits: list[TaintHit] = []
        seen: set[tuple[str, str, str]] = set()

        def add(ref: str, kind: str, matched: str) -> None:
            key = (ref, kind, matched)
            if key not in seen:
                seen.add(key)
                hits.append(TaintHit(source_ref=ref, kind=kind, matched=matched))  # type: ignore[arg-type]

        for value in _strings(params):
            text = normalize(value)
            for ref, seg in self._substring_hits(text):
                add(ref, "substring", seg)
            for url in sorted(urls_in(text)):
                for s in self.sources:
                    if url in s.urls:
                        add(s.ref, "url", url)
            for cmd in sorted(command_counts(text)):
                for s in self.sources:
                    if cmd in s.commands:
                        add(s.ref, "command", cmd)
        return hits

    def _substring_hits(self, text: str) -> list[tuple[str, str]]:
        """Maximal runs of `text` whose every min_len window occurs in one source, per source."""
        n = self.min_len
        positions = len(text) - n + 1
        out: list[tuple[str, str]] = []
        for src in self.sources:
            start = None
            for i in range(max(positions, 0)):
                inside = text[i : i + n] in src.shingles
                if inside and start is None:
                    start = i
                elif not inside and start is not None:
                    out.append((src.ref, text[start : i - 1 + n]))
                    start = None
            if start is not None:
                out.append((src.ref, text[start : positions - 1 + n]))
        return out


# --------------------------------------------------------------------------- the check

_SENSITIVE_CLASSES = frozenset({"ci", "dependencies", "secrets"})


def _sensitivity(views: tuple[str, ...], content: str) -> str | None:
    for view in views:
        classes = paths.protected_classes(view) & _SENSITIVE_CLASSES
        if classes:
            return f"{'/'.join(sorted(classes))} path {view}"
        if paths.is_test_config(view):
            return f"test-config path {view}"
        if paths.is_script(view, content):
            return f"script {view}"
    return None


class ProvenanceCheck:
    """Verification check. Blocks writes whose new material came from untrusted reads (see the
    module docstring for exactly when)."""

    name = "provenance"

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        if contract.tool != "write_file":
            return CheckResult(name=self.name, passed=True, reason=f"{contract.tool} carries no content")
        content = contract.params.get("content")
        if not isinstance(content, str):
            return CheckResult(name=self.name, passed=False, severity="block", error="write_file content is not a string")

        norm = paths.lexical(contract.params.get("path"))
        lex = norm.path or str(contract.params.get("path"))
        resolved = paths.resolve_in_workspace(ctx.workspace.root, norm.path) if norm.path else None
        views = paths.paths_of(lex, resolved)
        old = ""
        if resolved is not None and resolved.file is not None and resolved.file.is_file():
            old = resolved.file.read_bytes().decode("utf-8", errors="replace")

        # Only the content is matched: the path is the scope check's business, and a path the
        # agent saw in list_files output would otherwise taint every write.
        hits = ctx.taint_store.match({"content": content})
        new_hits = self._new_only(hits, old, content)
        if not new_hits:
            return CheckResult(name=self.name, passed=True, reason="no new material from untrusted reads")

        sensitive = _sensitivity(views, content)
        strong = [h for h in new_hits if h.kind in ("url", "command")]
        blocking = new_hits if sensitive else strong
        if blocking:
            where = sensitive or f"file {lex}"
            return CheckResult(
                name=self.name,
                passed=False,
                severity="block",
                reason=f"untrusted provenance (gateway taint tracking): write to {where} adds {self._describe(blocking)}",
            )
        return CheckResult(
            name=self.name,
            passed=False,
            severity="info",
            reason=f"overlaps untrusted content (not blocking for {lex}): {self._describe(new_hits)}",
        )

    @staticmethod
    def _new_only(hits: list[TaintHit], old: str, new: str) -> list[TaintHit]:
        old_active = active_text(old)
        new_active = active_text(new)
        old_cmds, new_cmds = command_counts(old_active), command_counts(new_active)
        new_norm = normalize(new)
        keep = []
        for h in hits:
            matched = normalize(h.matched)
            if h.kind == "command":
                if new_cmds.get(h.matched, 0) > old_cmds.get(h.matched, 0):
                    keep.append(h)
                elif h.matched not in COMMAND_PATTERNS and matched in new_norm and matched not in old_active:
                    keep.append(h)  # a store with other token names: fall back to text
            elif matched not in old_active:
                keep.append(h)
        return keep

    @staticmethod
    def _describe(hits: list[TaintHit], limit: int = 3) -> str:
        parts = [f"{h.kind} {h.matched[:80]!r} from {h.source_ref}" for h in hits[:limit]]
        more = f" (+{len(hits) - limit} more)" if len(hits) > limit else ""
        return "; ".join(parts) + more
