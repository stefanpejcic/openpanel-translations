#!/usr/bin/env python3
"""Sync this repo's gettext catalogs with the strings OpenPanel's Go app
actually translates.

What it does:
  1. Scans the openpanel Go source tree for every string routed through the
     i18n system: `.T.Get("...")` / `.T.Get "..."` and `.T.GetN(...)` calls
     in .go files and .html templates, plus a handful of known indirect
     cases where the literal lives in a Go struct field (Label, Title,
     TechDetails, ...) that a template later translates via `.T.Get .Field`.
  2. Rebuilds en-us/messages.pot and en-us/messages.po from that extraction
     (en-us is the source locale: msgstr is always empty, gotext falls back
     to msgid).
  3. Merges every other locale's messages.po against the new template:
     keeps existing translations for strings that still exist, drops
     entries for strings no longer used, and adds empty entries for
     strings that are new.

This script does NOT translate anything - newly-added strings land with an
empty msgstr and need a human (or a follow-up AI translation pass) to fill
them in. Its job is only to keep the catalogs' *shape* in sync with the
code.

Usage:
    python3 sync_locales.py --source /path/to/openpanel/checkout

Run from anywhere inside (or pass --repo-dir to) the openpanel-translations
checkout; defaults to this script's parent directory.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone, timedelta

try:
    import polib
except ImportError:
    sys.exit("This script requires 'polib' (pip install polib)")

# --- extraction -------------------------------------------------------

TMPL_GET = re.compile(r'\.T\.Get\s+"((?:[^"\\]|\\.)*)"')
TMPL_GETN = re.compile(r'\.T\.GetN\s+"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"')
GO_GET = re.compile(r'(?:^|[^\w.])(?:t|T|layout\.T|[A-Za-z_][A-Za-z0-9_]*\.T)\.Get\(\s*"((?:[^"\\]|\\.)*)"')
GO_GETN = re.compile(r'(?:^|[^\w.])(?:t|T|layout\.T|[A-Za-z_][A-Za-z0-9_]*\.T)\.GetN\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"')
FIELD_RE = re.compile(r'\b(?:Label|Title|PageTitle|TechDetails|RequirementsLabel|RequirementsTooltip):\s*"((?:[^"\\]|\\.)*)"')

# Positional-literal struct definitions that indirectly feed .T.Get in a
# template. These are hand-picked because Go struct literals with
# unlabeled positional fields can't be found by a generic pattern - update
# this list if those files' shapes change.
SECTIONS_GO = "internal/modules/dashboard/sections.go"
SECTIONS_ITEM_RE = re.compile(r'\{"[^"]*",\s*"[^"]*",\s*"[^"]*",\s*"((?:[^"\\]|\\.)*)",\s*"[^"]*"\}')

WEBSITES_RENDER_DISPATCH_GO = "internal/modules/websites/render_dispatch.go"
SECURITY_TOGGLE_RE = re.compile(r'\{"([^"]*)",\s*"((?:[^"\\]|\\.)*)",\s*\n\s*"((?:[^"\\]|\\.)*)"\}')

WEBAUTHN_GO = "internal/modules/account/webauthn.go"
RETURN_STR_RE = re.compile(r'return\s+"((?:[^"\\]|\\.)*)"')


def unescape(s):
    return s.encode().decode("unicode_escape") if "\\" in s else s


def add(results, msgid, plural, relpath, lineno):
    msgid = unescape(msgid)
    entry = results.setdefault(msgid, {"plural": None, "locations": []})
    if plural:
        entry["plural"] = unescape(plural)
    entry["locations"].append((relpath, lineno))


def extract(source_root):
    results = {}

    for dirpath, dirnames, filenames in os.walk(source_root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, source_root)
            if fn.endswith(".html"):
                with open(full, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    for m in TMPL_GETN.finditer(line):
                        add(results, m.group(1), m.group(2), rel, i)
                    for m in TMPL_GET.finditer(line):
                        add(results, m.group(1), None, rel, i)
            elif fn.endswith(".go") and not fn.endswith("_test.go"):
                with open(full, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    for m in GO_GETN.finditer(line):
                        add(results, m.group(1), m.group(2), rel, i)
                    for m in GO_GET.finditer(line):
                        add(results, m.group(1), None, rel, i)
                    for m in FIELD_RE.finditer(line):
                        add(results, m.group(1), None, rel, i)

    # Positional SectionItem literals in sections.go: {"key","href","icon","Label","target"}
    sections_path = os.path.join(source_root, SECTIONS_GO)
    if os.path.isfile(sections_path):
        with open(sections_path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for m in SECTIONS_ITEM_RE.finditer(line):
                    add(results, m.group(1), None, SECTIONS_GO, i)

    # Positional SecurityToggle literals: {"id", "Label", "TechDetails"}
    toggles_path = os.path.join(source_root, WEBSITES_RENDER_DISPATCH_GO)
    if os.path.isfile(toggles_path):
        with open(toggles_path, encoding="utf-8") as f:
            content = f.read()
        for m in SECURITY_TOGGLE_RE.finditer(content):
            line = content[: m.start()].count("\n") + 1
            add(results, m.group(2), None, WEBSITES_RENDER_DISPATCH_GO, line)
            add(results, m.group(3), None, WEBSITES_RENDER_DISPATCH_GO, line)

    # webauthn.go literal `return "..."` reasons
    webauthn_path = os.path.join(source_root, WEBAUTHN_GO)
    if os.path.isfile(webauthn_path):
        with open(webauthn_path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for m in RETURN_STR_RE.finditer(line):
                    if m.group(1):
                        add(results, m.group(1), None, WEBAUTHN_GO, i)

    return results


# --- pot/po generation --------------------------------------------------

def sort_key(item):
    msgid, data = item
    locs = sorted(data["locations"])
    return locs[0] if locs else ("", 0)


def build_en_us(repo_dir, extracted, project_version):
    pot_path = os.path.join(repo_dir, "en-us", "messages.pot")
    po_path = os.path.join(repo_dir, "en-us", "messages.po")

    items = sorted(extracted.items(), key=sort_key)

    old_pot = polib.pofile(pot_path)
    now = datetime.now(timezone(timedelta(hours=2)))
    creation_date = now.strftime("%Y-%m-%d %H:%M%z")

    def make_catalog(old):
        meta = dict(old.metadata)
        meta["Project-Id-Version"] = project_version
        meta["POT-Creation-Date"] = creation_date
        cat = polib.POFile()
        cat.metadata = meta
        cat.header = old.header
        for msgid, data in items:
            entry = polib.POEntry(
                msgid=msgid,
                msgstr="",
                occurrences=[(loc[0], str(loc[1])) for loc in sorted(set(tuple(l) for l in data["locations"]))],
            )
            if data["plural"]:
                entry.msgid_plural = data["plural"]
                entry.msgstr_plural = {0: "", 1: ""}
            cat.append(entry)
        return cat

    new_pot = make_catalog(old_pot)
    new_pot.save(pot_path)

    old_po = polib.pofile(po_path)
    new_po = make_catalog(old_po)
    new_po.save(po_path)

    return new_pot


def sync_locale(repo_dir, locale, pot):
    po_path = os.path.join(repo_dir, locale, "messages.po")
    if not os.path.isfile(po_path):
        return None

    old_po = polib.pofile(po_path)
    old_map = {e.msgid: e for e in old_po}

    new_po = polib.POFile()
    meta = dict(old_po.metadata)
    meta["POT-Creation-Date"] = pot.metadata["POT-Creation-Date"]
    meta["Project-Id-Version"] = pot.metadata["Project-Id-Version"]
    new_po.metadata = meta
    new_po.header = old_po.header

    carried = 0
    for pot_entry in pot:
        old = old_map.get(pot_entry.msgid)
        entry = polib.POEntry(
            msgid=pot_entry.msgid,
            msgstr=old.msgstr if old and not old.fuzzy else "",
            occurrences=list(pot_entry.occurrences),
        )
        if pot_entry.msgid_plural:
            entry.msgid_plural = pot_entry.msgid_plural
            entry.msgstr_plural = dict(old.msgstr_plural) if old and old.msgstr_plural else {0: "", 1: ""}
        if old and old.msgstr and not old.fuzzy:
            carried += 1
        new_po.append(entry)

    new_po.save(po_path)
    return {
        "total": len(new_po),
        "carried_over": carried,
        "untranslated": len(new_po.untranslated_entries()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="path to an openpanel repo checkout (the Go app)")
    parser.add_argument("--repo-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         help="path to this openpanel-translations checkout (default: parent of this script's dir)")
    parser.add_argument("--project-version", default=None,
                         help="Project-Id-Version string, e.g. 'OpenPanel 2.0.3' (default: read from <source>/version)")
    args = parser.parse_args()

    source_root = os.path.abspath(args.source)
    repo_dir = os.path.abspath(args.repo_dir)

    if not os.path.isdir(source_root):
        sys.exit(f"--source path does not exist: {source_root}")

    project_version = args.project_version
    if not project_version:
        version_file = os.path.join(source_root, "version")
        if os.path.isfile(version_file):
            with open(version_file) as f:
                project_version = f"OpenPanel {f.read().strip()}"
        else:
            project_version = "OpenPanel"

    print(f"Extracting strings from {source_root} ...")
    extracted = extract(source_root)
    print(f"Found {len(extracted)} unique translatable strings.")

    pot = build_en_us(repo_dir, extracted, project_version)
    print(f"Wrote en-us/messages.pot and en-us/messages.po ({len(pot)} entries).")

    locales = sorted(
        d for d in os.listdir(repo_dir)
        if os.path.isdir(os.path.join(repo_dir, d)) and d != "en-us" and not d.startswith(".")
    )

    print()
    print(f"{'locale':8s} {'total':>6s} {'carried':>8s} {'untranslated':>13s}")
    any_locale = False
    for loc in locales:
        stats = sync_locale(repo_dir, loc, pot)
        if stats is None:
            continue
        any_locale = True
        print(f"{loc:8s} {stats['total']:6d} {stats['carried_over']:8d} {stats['untranslated']:13d}")

    if not any_locale:
        print("(no locale messages.po files found to sync)")


if __name__ == "__main__":
    main()
