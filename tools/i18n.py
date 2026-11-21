#!/usr/bin/env python3
"""
Translation helper for LinSticky (standard library only).

    python3 tools/i18n.py check            # report problems, exit code 1 if any
    python3 tools/i18n.py update [--prune] # add new strings from the code to .pot and all .po
    python3 tools/i18n.py compile          # build every .mo from its .po
    python3 tools/i18n.py new <lang>       # start a new language from the .pot

Strings are collected from ``_("...")`` (also ``builtins._``) and ``N_("...")``
calls in ``linsticky/**/*.py``. ``N_`` marks strings that are translated later
(e.g. table entries). Like ``msgfmt``, ``compile`` skips fuzzy and empty
entries, so they fall back to English.
"""
import ast
import gettext
import json
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "linsticky"
LOCALE = SRC / "locale"
DOMAIN = "io.linsticky.app"
POT = LOCALE / f"{DOMAIN}.pot"
KEYWORDS = {"_", "N_"}
PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


# --------------------------------------------------------------------------- source
def extract() -> dict:
    """Returns {msgid: [ "path:line", ... ]} in order of first appearance."""
    found = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            arg = node.args[0]
            if name in KEYWORDS and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.setdefault(arg.value, []).append(f"{rel}:{node.lineno}")
    return found


# --------------------------------------------------------------------------- PO files
def _unquote(line: str) -> str:
    return json.loads(line) if line.startswith('"') else ""


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


class Entry:
    def __init__(self, lines):
        self.lines = lines
        self.msgid = None
        self.msgstr = ""
        self.fuzzy = False
        self.obsolete = any(l.startswith("#~ msgid") for l in lines)
        field = None
        for line in lines:
            s = line.strip()
            if s.startswith("#,") and "fuzzy" in s:
                self.fuzzy = True
            elif s.startswith(("msgctxt", "msgid_plural", "msgstr[")):
                raise SystemExit(f"Unsupported PO construct (plural/context): {s}")
            elif s.startswith("msgid "):
                field, self.msgid = "msgid", _unquote(s[6:])
            elif s.startswith("msgstr "):
                field, self.msgstr = "msgstr", _unquote(s[7:])
            elif s.startswith('"') and field:
                setattr(self, field, getattr(self, field) + _unquote(s))


def read_po(path: Path):
    """Splits a PO file into entries (blocks separated by blank lines)."""
    blocks, cur = [], []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return [Entry(b) for b in blocks]


def write_po(path: Path, entries):
    path.write_text("\n\n".join("\n".join(e.lines) for e in entries) + "\n",
                    encoding="utf-8", newline="\n")


def new_entry(msgid: str, refs, msgstr: str = "") -> Entry:
    lines = [f"# {r}" for r in refs[:3]]
    if PLACEHOLDER_RE.search(msgid):
        lines.append("#, python-brace-format")
    lines += [f"msgid {_quote(msgid)}", f"msgstr {_quote(msgstr)}"]
    return Entry(lines)


def catalog(path: Path) -> dict:
    """Translations that msgfmt would compile (no fuzzy, no empty)."""
    result = {}
    for e in read_po(path):
        if e.msgid is None or e.obsolete:
            continue
        if e.msgid and (e.fuzzy or not e.msgstr):
            continue
        result[e.msgid] = e.msgstr
    return result


def po_files():
    return sorted(LOCALE.glob(f"*/LC_MESSAGES/{DOMAIN}.po"))


def lang_of(po: Path) -> str:
    return po.parent.parent.name


# --------------------------------------------------------------------------- MO
def write_mo(cat: dict, path: Path):
    keys = sorted(cat)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(cat[k].encode() + b"\0" for k in keys)
    n = len(keys)
    key_start = 7 * 4 + 16 * n
    value_start = key_start + len(ids)
    koffsets, voffsets, ko, vo = [], [], 0, 0
    for k in keys:
        kb, vb = k.encode(), cat[k].encode()
        koffsets += [len(kb), key_start + ko]
        voffsets += [len(vb), value_start + vo]
        ko += len(kb) + 1
        vo += len(vb) + 1
    data = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
    data += struct.pack(f"{2 * n}i", *koffsets) + struct.pack(f"{2 * n}i", *voffsets)
    path.write_bytes(data + ids + strs)


def mo_is_current(po: Path) -> bool:
    mo = po.with_suffix(".mo")
    if not mo.exists():
        return False
    with mo.open("rb") as f:
        compiled = gettext.GNUTranslations(f)
    cat = catalog(po)
    return all(compiled.gettext(k) == v for k, v in cat.items() if k) and \
        len(compiled._catalog) == len(cat)  # noqa: SLF001 - no public API for the size


# --------------------------------------------------------------------------- commands
def cmd_check() -> int:
    code = extract()
    problems = 0

    def report(msg):
        nonlocal problems
        problems += 1
        print("  " + msg)

    pot_ids = {e.msgid for e in read_po(POT) if e.msgid and not e.obsolete}
    print(f"{POT.relative_to(ROOT)}: {len(code)} strings in code, {len(pot_ids)} in template")
    for m in sorted(set(code) - pot_ids):
        report(f"missing in .pot (run update): {m!r}")
    for m in sorted(pot_ids - set(code)):
        print(f"  note: not used in code any more (update --prune removes): {m!r}")

    for po in po_files():
        entries = [e for e in read_po(po) if e.msgid and not e.obsolete]
        ids = {e.msgid for e in entries}
        print(f"{lang_of(po)}:")
        for m in sorted(pot_ids - ids):
            report(f"missing: {m!r}")
        for e in entries:
            if e.fuzzy:
                report(f"fuzzy (not used until reviewed): {e.msgid!r}")
            elif not e.msgstr:
                report(f"untranslated: {e.msgid!r}")
            elif sorted(PLACEHOLDER_RE.findall(e.msgid)) != sorted(PLACEHOLDER_RE.findall(e.msgstr)):
                report(f"placeholders differ: {e.msgid!r} -> {e.msgstr!r}")
        if not mo_is_current(po):
            report(".mo is out of date (run compile)")
    print("OK" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


def cmd_update(prune: bool) -> int:
    code = extract()
    for path in [POT] + po_files():
        entries = read_po(path)
        known = {e.msgid for e in entries if e.msgid is not None}
        added = [new_entry(m, refs) for m, refs in code.items() if m not in known]
        removed = 0
        if prune:
            keep = [e for e in entries if e.msgid == "" or e.msgid is None or e.msgid in code]
            removed = len(entries) - len(keep)
            entries = keep
        if path == POT:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M+0000")
            header = entries[0]
            header.lines = [f'"POT-Creation-Date: {stamp}\\n"' if l.startswith('"POT-Creation-Date:') else l
                            for l in header.lines]
        write_po(path, entries + added)
        name = "template" if path == POT else lang_of(path)
        print(f"{name}: +{len(added)} new" + (f", -{removed} obsolete" if prune else ""))
    print("Translate the new (empty) entries in the .po files, then run: compile")
    return 0


def cmd_compile() -> int:
    for po in po_files():
        cat = catalog(po)
        write_mo(cat, po.with_suffix(".mo"))
        print(f"{lang_of(po)}: {len(cat) - ('' in cat)} messages")
    return 0


def cmd_new(lang: str) -> int:
    target = LOCALE / lang / "LC_MESSAGES" / f"{DOMAIN}.po"
    if target.exists():
        raise SystemExit(f"{target} already exists")
    entries = read_po(POT)
    header = entries[0]
    header.lines = [l for l in header.lines if l.strip() != "#, fuzzy"]
    header.lines = [l.replace('"Language: \\n"', f'"Language: {lang}\\n"') for l in header.lines]
    target.parent.mkdir(parents=True)
    write_po(target, entries)
    print(f"Created {target.relative_to(ROOT)}. Translate it, run compile, and add the "
          f"language to LANGUAGE_NAMES and LOCALE_MAP in linsticky/config/config.py.")
    return 0


def main(argv) -> int:
    if not argv or argv[0] not in ("check", "update", "compile", "new"):
        print(__doc__)
        return 2
    if argv[0] == "check":
        return cmd_check()
    if argv[0] == "update":
        return cmd_update(prune="--prune" in argv)
    if argv[0] == "compile":
        return cmd_compile()
    if len(argv) != 2:
        raise SystemExit("usage: i18n.py new <lang>")
    return cmd_new(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
