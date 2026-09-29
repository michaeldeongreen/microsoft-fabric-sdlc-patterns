"""Mechanical verification sweep for the Spanish translations.

Checks the things a human reviewer reliably skims past, so that review
attention can go to naturalness and terminology instead:

  1. relative links resolve (the ``../`` depth changes with nesting)
  2. in-page anchors match the *translated* headings
  3. fenced code blocks are byte-identical to the English source
  4. no terminology the native review rejected
  5. no ``tú`` forms (the agreed register is impersonal / ``usted``)
  6. no gender disagreement left behind by a terminology substitution

Every rule here encodes a defect that actually occurred. Check 3 caught a
GUID that had been retyped from a truncated read; check 5 caught a ``tú``
form that had survived two rounds of human review.

The rules are Spanish-specific. A Portuguese translation would need its own
rejected-terminology and register lists, not a ``--lang`` flag on these.

Run from the repository root::

    python scripts/verify_translations.py

Exits non-zero if any check fails, so it can gate a commit.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

SKIP_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__", "node_modules", ".scratch"}

LINK = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)]+)\)")
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
FENCE_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)

# Box-drawing characters mark an ASCII-art diagram rather than code. Those
# blocks contain prose labels that *should* be translated, so they are exempt
# from the byte-identical requirement applied to real code.
BOX_DRAWING = frozenset("─│┌┐└┘├┤┬┴┼━┃▼▲►◄↓↑→←")

# Terms the native review rejected. The glossary and style guide legitimately
# quote them while explaining why they are wrong, so those files are exempt.
REJECTED = (
    "área de trabajo", "áreas de trabajo", "entidad de servicio", "entidades de servicio",
    "canalización", "canalizaciones", "la *pipeline*", "las *pipelines*",
    "PR fusionado", "Capacidad de Fabric",
    "librería", "identificador", "identificadores", "ambiente", "soporta", "soportan",
    # Inclusive-language variant that drifted in on two lines. The rest of the
    # corpus uses "desarrollador(es)", including the reviewed README; mixing the
    # two reads worse than either used consistently.
    "personas desarrolladoras", "persona desarrolladora",
)

# Rejected only in specific senses; the same stem is fine elsewhere.
CONTEXTUAL_REJECTED = (
    # The noun is rejected in favour of "Trigger", but the verb
    # "desencadenado por" is ordinary Spanish and must not be flagged.
    (r"\bdesencadenador(es)?\b", "use *Trigger* (the noun is rejected; the verb is fine)"),
    # "codificado" is only wrong for *hardcoded*, which in this repository always
    # concerns GUIDs or IDs. "codificado en base64" and "conocimiento codificado
    # en el contrato" are ordinary Spanish, so require an ID nearby. Python
    # lookbehind is fixed-width, hence two forward patterns rather than one.
    (r"\b(GUID|IDs?)\b[^.]{0,40}\bcodificad[oa]s?\b", "use 'definido directamente' for hardcoded"),
    (r"\bcodificad[oa]s?\b[^.]{0,40}\b(GUID|IDs?)\b", "use 'definido directamente' for hardcoded"),
    (r"\bconmuta\b", "use 'alterna'"),
)

REFERENCE_FILES = frozenset({"GLOSARIO.md", "GUIA-DE-ESTILO.md", "REVISION.md"})

# Unambiguous second-person forms. These can only be tú, so they are failures.
TU_DEFINITE = (
    r"\bpuedes\b", r"\btienes\b", r"\bdebes\b", r"\bencuentras\b", r"\bdetectas\b",
    r"\bnecesitas\b", r"\bquieres\b", r"\bharás\b", r"\bverás\b", r"\bsabes\b",
    r"\btu\s+\w", r"\btus\s+\w",
)

# Forms identical as a tú imperative and as third-person indicative:
# "consulta la guía" (you check) versus "el script consulta la guía" (it checks).
# Reported for a human to judge rather than failed automatically.
TU_AMBIGUOUS = (
    r"\bconsulta\b", r"\brevisa\b", r"\bcomprueba\b", r"\belige\b", r"\bañade\b",
    r"\bactualiza\b", r"\bcorrige\b", r"\butiliza\b", r"\bcopia\b", r"\babre\b",
    r"\bejecuta\b", r"\bpega\b", r"\bcrea\b",
)

# Replacing a feminine Spanish noun with a masculine English one strands the
# determiner. This is the single most recurrent defect in the batch.
GENDER_TRAPS = (
    (r"\b(la|una|las|esta|estas|otra|otras|dicha|misma|propia)\s+workspace", "workspace is masculine"),
    (r"\b(la|una|las|esta|estas)\s+\*?pipeline", "pipeline is masculine"),
    (r"workspace\s+a\s+otra\b", "should be 'a otro'"),
    (r"\b(la|una)\s+\*?Service principal", "Service principal is masculine"),
    (r"workspace[s]?\s+\w+(ada|adas)\b", "check participle agreement"),
)

AMBIGUOUS_SHOWN = 12
DETAIL_LIMIT = 25


def walk_markdown(base: Path) -> list[Path]:
    """Return every Markdown file under ``base``, skipping build directories."""
    if not base.exists():
        return []
    found = [
        path for path in sorted(base.rglob("*.md"))
        if not SKIP_DIRS.intersection(path.parts)
    ]
    return found


def is_ascii_art(block: str) -> bool:
    """True if a fenced block is a diagram whose labels should be translated."""
    return any(ch in BOX_DRAWING for ch in block)


def strip_code(text: str) -> str:
    """Remove fenced blocks and inline code so examples are not read as prose."""
    out: list[str] = []
    in_fence = False
    marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence, marker = True, stripped[:3]
            continue
        if in_fence:
            if stripped.startswith(marker):
                in_fence = False
            continue
        out.append(line)
    return re.sub(r"`[^`\n]*`", "", "\n".join(out))


def slug(heading: str) -> str:
    """Approximate GitHub's heading-to-anchor derivation.

    GitHub lowercases, strips punctuation, and replaces each remaining space
    with a hyphen -- individually, not collapsing runs. "Prerequisites & Setup"
    therefore yields "prerequisites--setup", with two hyphens. Underscores are
    punctuation to Unicode but GitHub keeps them, so they are allowed through.
    """
    text = re.sub(r"[`*~]", "", heading).strip().lower()
    text = "".join(
        c for c in text
        if unicodedata.category(c)[0] in "LN" or c in "-_ \u00a0"
    )
    return text.replace(" ", "-").strip("-")


def check_links(root: Path) -> tuple[int, list[str]]:
    """Resolve every relative Markdown link and image against the filesystem."""
    problems: list[str] = []
    count = 0
    for path in walk_markdown(root):
        content = strip_code(path.read_text(encoding="utf-8"))
        for pattern in (LINK, IMG):
            for _text, raw_target in pattern.findall(content):
                target = raw_target.strip()
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target = target.split("#")[0]
                if not target:
                    continue
                count += 1
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    problems.append(f"{path.relative_to(root)} -> {target}")
    return count, problems


def check_anchors(root: Path, translations: Path) -> tuple[int, list[str]]:
    """Verify anchors point at headings that exist *after* translation.

    Covers both same-file (``#anchor``) and cross-file (``guide.md#anchor``)
    targets. The cross-file case matters most: a relative link from a Spanish
    document resolves to its Spanish sibling, whose headings are translated, so
    an anchor copied from the English source silently points at nothing. Five
    such links survived two rounds of human review because only the same-file
    case was checked and the link check discards the fragment.
    """
    problems: list[str] = []
    count = 0
    heading_cache: dict[Path, set[str]] = {}

    def headings_of(path: Path) -> set[str]:
        if path not in heading_cache:
            heading_cache[path] = {
                slug(m) for m in
                re.findall(r"(?m)^#{1,6}\s+(.+)$", path.read_text(encoding="utf-8"))
            }
        return heading_cache[path]

    for path in walk_markdown(translations):
        content = strip_code(path.read_text(encoding="utf-8"))
        for _text, raw_target in LINK.findall(content):
            target = raw_target.strip()
            if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
                continue
            file_part, _, anchor = target.partition("#")
            if not file_part:
                dest = path
            else:
                if not file_part.endswith(".md"):
                    continue
                dest = (path.parent / file_part).resolve()
                if not dest.exists():
                    continue  # reported by the link check
            count += 1
            if anchor not in headings_of(dest):
                problems.append(f"{path.relative_to(root)} -> {target}")
    return count, problems


def check_code_parity(pairs: list[tuple[Path, Path]]) -> list[str]:
    """Fenced code must survive translation untouched, except ASCII-art labels."""
    problems: list[str] = []
    for en_path, es_path in pairs:
        if not (en_path.exists() and es_path.exists()):
            continue
        en = [b.strip() for b in FENCE_BLOCK.findall(en_path.read_text(encoding="utf-8"))]
        es = [b.strip() for b in FENCE_BLOCK.findall(es_path.read_text(encoding="utf-8"))]
        if len(en) != len(es):
            problems.append(f"{es_path.name}: {len(en)} English blocks vs {len(es)} Spanish")
            continue
        for i, (a, b) in enumerate(zip(en, es), 1):
            if is_ascii_art(a):
                continue
            if a != b:
                problems.append(f"{es_path.name} block {i} differs")
    return problems


def _scan(text: str, label: str) -> list[str]:
    """Apply the rejected-terminology rules to one file's contents.

    Matching is case-insensitive: these terms turn up capitalised at the start
    of a sentence and title-cased in diagram labels and table headers.
    """
    problems: list[str] = []
    for bad in REJECTED:
        n = len(re.findall(re.escape(bad), text, re.I))
        if n:
            problems.append(f"{label}: '{bad}' x{n}")
    for pattern, why in CONTEXTUAL_REJECTED:
        for m in re.finditer(pattern, text, re.I):
            problems.append(f"{label}: '{m.group(0)}' — {why}")
    return problems


def check_terminology(root: Path, translations: Path, diagrams: Path) -> list[str]:
    """Check prose and diagram labels against the rejected-terminology list."""
    problems: list[str] = []
    for path in walk_markdown(translations):
        if path.name in REFERENCE_FILES:
            continue
        problems += _scan(path.read_text(encoding="utf-8"), str(path.relative_to(root)))
    if diagrams.exists():
        for path in sorted(diagrams.rglob("*.svg")):
            problems += _scan(path.read_text(encoding="utf-8"), str(path.relative_to(root)))
    return problems


def check_register(root: Path, translations: Path) -> tuple[list[str], list[str]]:
    """Return (definite tú failures, ambiguous forms needing human judgement)."""
    definite: list[str] = []
    ambiguous: list[str] = []
    for path in walk_markdown(translations):
        if path.name in REFERENCE_FILES:
            continue
        content = strip_code(path.read_text(encoding="utf-8"))
        label = str(path.relative_to(root))
        for pattern in TU_DEFINITE:
            for m in re.finditer(pattern, content, re.I):
                snippet = content[max(0, m.start() - 45):m.end() + 35].replace("\n", " ")
                definite.append(f"{label}: …{snippet}…")
        for pattern in TU_AMBIGUOUS:
            for m in re.finditer(pattern, content, re.I):
                snippet = content[max(0, m.start() - 55):m.end() + 30].replace("\n", " ")
                ambiguous.append(f"{label}: …{snippet}…")
    return definite, ambiguous


def check_gender(root: Path, translations: Path) -> list[str]:
    """Catch determiners left feminine after a masculine English term replaced them."""
    problems: list[str] = []
    for path in walk_markdown(translations):
        if path.name in REFERENCE_FILES:
            continue
        content = path.read_text(encoding="utf-8")
        label = str(path.relative_to(root))
        for pattern, why in GENDER_TRAPS:
            for m in re.finditer(pattern, content, re.I):
                problems.append(f"{label}: '{m.group(0)}' ({why})")
    return problems


def report(title: str, problems: list[str], detail_limit: int = DETAIL_LIMIT) -> bool:
    """Print a check's result; return True when it passed."""
    if problems:
        print(f"\n{title}: {len(problems)} ISSUE(S)")
        for p in problems[:detail_limit]:
            print(f"    {p}")
        if len(problems) > detail_limit:
            print(f"    … and {len(problems) - detail_limit} more")
        return False
    print(f"{title}: clean")
    return True


def build_pairs(root: Path, translations: Path) -> list[tuple[Path, Path]]:
    """Pair each translated file with its English source by mirrored path."""
    pairs: list[tuple[Path, Path]] = []
    for path in walk_markdown(translations):
        if path.name in REFERENCE_FILES:
            continue
        pairs.append((root / path.relative_to(translations), path))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(),
        help="repository root (defaults to the current directory)",
    )
    parser.add_argument(
        "--lang", default="es",
        help="translation subdirectory under translations/ (default: es)",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    translations = root / "translations" / args.lang
    diagrams = root / "assets" / args.lang

    if not translations.is_dir():
        sys.exit(f"error: no translations found at {translations}")

    ok = True

    n, problems = check_links(root)
    print(f"relative links checked: {n}")
    ok &= report("  links", problems)

    n, problems = check_anchors(root, translations)
    print(f"anchors checked: {n}")
    ok &= report("  anchors", problems)

    ok &= report("code fence parity", check_code_parity(build_pairs(root, translations)))
    ok &= report("rejected terminology", check_terminology(root, translations, diagrams))

    definite, ambiguous = check_register(root, translations)
    ok &= report("tú-form register", definite)
    if ambiguous:
        print(f"\n  note: {len(ambiguous)} ambiguous verb form(s) — valid as third-person")
        print("        indicative, listed for human judgement, not counted as failures:")
        for a in ambiguous[:AMBIGUOUS_SHOWN]:
            print(f"    {a}")
        if len(ambiguous) > AMBIGUOUS_SHOWN:
            print(f"    … and {len(ambiguous) - AMBIGUOUS_SHOWN} more")

    ok &= report("gender agreement", check_gender(root, translations))

    print("\n" + ("ALL CHECKS PASSED" if ok else "ISSUES FOUND — see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
