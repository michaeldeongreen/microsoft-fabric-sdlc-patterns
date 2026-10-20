"""Unit tests for scripts/verify_translations.py."""

import sys
from pathlib import Path

import pytest

import verify_translations as vt


# ── Anchor slug derivation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Simple Heading", "simple-heading"),
        # GitHub replaces each space individually; it does not collapse runs,
        # so a stripped "&" leaves two hyphens behind.
        ("Prerequisites & Setup", "prerequisites--setup"),
        ("Qué es `workspace_swap.py`", "qué-es-workspace_swappy"),
        ("**Bold** and *italic*", "bold-and-italic"),
        ("Trailing punctuation!", "trailing-punctuation"),
    ],
)
def test_slug_matches_github_derivation(heading: str, expected: str) -> None:
    assert vt.slug(heading) == expected


# ── ASCII-art exemption ────────────────────────────────────────────────────


def test_ascii_art_detected_by_box_drawing() -> None:
    assert vt.is_ascii_art("┌────┐\n│ dev │\n└────┘")


def test_real_code_is_not_ascii_art() -> None:
    assert not vt.is_ascii_art("python scripts/workspace_swap.py --check-ready")


# ── Prose extraction ───────────────────────────────────────────────────────


def test_strip_code_removes_fenced_and_inline_code() -> None:
    text = "Antes\n```bash\npuedes ejecutar esto\n```\nDespués con `tu_variable` aquí."
    stripped = vt.strip_code(text)
    assert "puedes" not in stripped
    assert "tu_variable" not in stripped
    assert "Antes" in stripped
    assert "Después" in stripped


# ── Fixtures for the filesystem-walking checks ─────────────────────────────


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A minimal repository with one English document and its translation."""
    (tmp_path / "translations" / "es").mkdir(parents=True)
    (tmp_path / "assets" / "es").mkdir(parents=True)
    (tmp_path / "guide.md").write_text(
        "# Guide\n\n```bash\nfabric-cicd --workspace dev\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n```bash\nfabric-cicd --workspace dev\n```\n",
        encoding="utf-8",
    )
    return tmp_path


def test_clean_translation_passes_every_check(repo: Path) -> None:
    es = repo / "translations" / "es"
    assert vt.check_links(repo)[1] == []
    assert vt.check_code_parity(vt.build_pairs(repo, es)) == []
    assert vt.check_terminology(repo, es, repo / "assets" / "es") == []
    assert vt.check_register(repo, es)[0] == []
    assert vt.check_gender(repo, es) == []


def test_broken_relative_link_is_reported(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nVéase [el otro](./no-existe.md).\n", encoding="utf-8"
    )
    _count, problems = vt.check_links(repo)
    assert any("no-existe.md" in p for p in problems)


def test_same_file_anchor_is_checked(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n## Sección válida\n\nVéase [esto](#seccion-inexistente).\n", encoding="utf-8"
    )
    _count, problems = vt.check_anchors(repo, repo / "translations" / "es")
    assert any("seccion-inexistente" in p for p in problems)


def test_english_anchor_into_translated_sibling_is_reported(repo: Path) -> None:
    """The defect that survived two human reviews: an anchor copied from English.

    A relative link from a Spanish document resolves to its Spanish sibling,
    whose headings are translated, so the English anchor points at nothing.
    """
    es = repo / "translations" / "es"
    (es / "other.md").write_text("# Otro\n\n## Requisitos previos\n", encoding="utf-8")
    (es / "guide.md").write_text(
        "# Guía\n\nVéase [los requisitos](other.md#prerequisites).\n", encoding="utf-8"
    )
    _count, problems = vt.check_anchors(repo, es)
    assert any("other.md#prerequisites" in p for p in problems)


def test_correct_cross_file_anchor_passes(repo: Path) -> None:
    es = repo / "translations" / "es"
    (es / "other.md").write_text("# Otro\n\n## Requisitos previos\n", encoding="utf-8")
    (es / "guide.md").write_text(
        "# Guía\n\nVéase [los requisitos](other.md#requisitos-previos).\n", encoding="utf-8"
    )
    count, problems = vt.check_anchors(repo, es)
    assert problems == []
    assert count == 1


def test_explicit_html_anchor_is_a_valid_target(repo: Path) -> None:
    """English keeps ``<a id>`` anchors for compatibility; links to them must resolve."""
    es = repo / "translations" / "es"
    (es / "other.md").write_text(
        '# Otro\n\n## Tabla\n\n<a id="custom-anchor"></a>\n\nTexto.\n', encoding="utf-8"
    )
    (es / "guide.md").write_text(
        "# Guía\n\nVéase [esto](other.md#custom-anchor) y [lo otro](other.md#no-existe).\n",
        encoding="utf-8",
    )
    count, problems = vt.check_anchors(repo, es)
    assert count == 2
    assert problems == [f"{Path('translations') / 'es' / 'guide.md'} -> other.md#no-existe"]


def test_cross_file_anchor_to_missing_file_is_left_to_the_link_check(repo: Path) -> None:
    """Avoid reporting the same defect twice under two different names."""
    es = repo / "translations" / "es"
    (es / "guide.md").write_text(
        "# Guía\n\nVéase [esto](no-existe.md#algo).\n", encoding="utf-8"
    )
    count, problems = vt.check_anchors(repo, es)
    assert problems == []
    assert count == 0
    assert vt.check_links(repo)[1] != []


def test_altered_code_block_is_reported(repo: Path) -> None:
    """Translating inside a code fence is the defect that produced a wrong GUID."""
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n```bash\nfabric-cicd --area-de-trabajo dev\n```\n", encoding="utf-8"
    )
    problems = vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es"))
    assert any("block 1 differs" in p for p in problems)


def test_ascii_art_block_may_differ(repo: Path) -> None:
    (repo / "guide.md").write_text(
        "# Guide\n\n```text\n┌─────┐\n│ dev │\n└─────┘\n```\n", encoding="utf-8"
    )
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n```text\n┌─────┐\n│ des │\n└─────┘\n```\n", encoding="utf-8"
    )
    assert vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es")) == []


@pytest.mark.parametrize("language", ["", "text"])
def test_ascii_arrow_diagram_labels_may_differ(repo: Path, language: str) -> None:
    (repo / "guide.md").write_text(
        f"# Guide\n\n```{language}\nPipeline\n  -> native refresh\n```\n", encoding="utf-8"
    )
    (repo / "translations" / "es" / "guide.md").write_text(
        f"# Guía\n\n```{language}\nPipeline\n  -> actualización nativa\n```\n", encoding="utf-8"
    )
    assert vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es")) == []


@pytest.mark.parametrize(
    ("language", "english", "spanish", "allowed"),
    [
        (
            "yaml",
            '# Existing rules\nfind: "dev-id"  # Dev baseline',
            '# Reglas existentes\nfind: "dev-id"  # Referencia de Dev',
            True,
        ),
        ("yml", "value: 'it''s # literal' # Note", "value: 'it''s # literal' # Nota", True),
        (
            "yaml",
            'value: "escaped \\" # literal" # Note',
            'value: "escaped \\" # literal" # Nota',
            True,
        ),
        (
            "yaml",
            "url: https://example.invalid/#anchor # Note",
            "url: https://example.invalid/#anchor # Nota",
            True,
        ),
        ("yaml", 'find: "dev-id" # Note', 'find: "other-id" # Nota', False),
        ("yaml", 'value: "error # literal"', 'value: "error # traducido"', False),
        ("yaml", "value: 'error # literal'", "value: 'error # traducido'", False),
        ("yaml", "value: plain#literal", "value: plain#traducido", False),
        ("yaml", "value: |\n  # literal", "value: |\n  # traducido", False),
        ("yaml", "value: >-\n  # literal", "value: >-\n  # traducido", False),
        ("yaml", "value: |2-\n  # literal", "value: |2-\n  # traducido", False),
        (
            "yaml",
            'value: "first\n# literal\nlast"',
            'value: "first\n# traducido\nlast"',
            False,
        ),
        (
            "yaml",
            "name: don't\nvalue: 'hello # original'",
            "name: don't\nvalue: 'hello # changed'",
            False,
        ),
        ("yaml", "value: &body |\n  # original", "value: &body |\n  # changed", False),
        ("yaml", "value: !!str >-\n  # original", "value: !!str >-\n  # changed", False),
        (
            "yaml",
            "value: &body | # Note\n  # literal",
            "value: &body | # Nota\n  # literal",
            True,
        ),
        (
            "yaml",
            "value: first\n  # Note\n  second",
            "value: first\n  # Nota\n  second",
            True,
        ),
        ("yaml", 'value: "a → original"', 'value: "a → changed"', False),
        ("python", 'message = "a → original"', 'message = "a → changed"', False),
        ("text", "# Literal tool output", "# Salida traducida", False),
        ("console", "  -> Literal tool output", "  -> Salida traducida", False),
        ("console", "done → original", "done → changed", False),
        (
            "python",
            'message = """\n  -> Literal output\n"""',
            'message = """\n  -> Salida traducida\n"""',
            False,
        ),
    ],
)
def test_code_parity_preserves_data_while_allowing_yaml_comments(
    repo: Path, language: str, english: str, spanish: str, allowed: bool,
) -> None:
    (repo / "guide.md").write_text(
        f"# Guide\n\n```{language}\n{english}\n```\n", encoding="utf-8"
    )
    (repo / "translations" / "es" / "guide.md").write_text(
        f"# Guía\n\n```{language}\n{spanish}\n```\n", encoding="utf-8"
    )
    problems = vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es"))
    assert (problems == []) is allowed


def test_changed_fence_language_is_reported(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n```text\nfabric-cicd --workspace dev\n```\n", encoding="utf-8"
    )
    assert vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es"))


def test_invalid_yaml_comment_comparison_is_reported(repo: Path) -> None:
    (repo / "guide.md").write_text(
        '# Guide\n\n```yaml\nvalue: "unterminated # Note\n```\n', encoding="utf-8"
    )
    (repo / "translations" / "es" / "guide.md").write_text(
        '# Guía\n\n```yaml\nvalue: "unterminated # Nota\n```\n', encoding="utf-8"
    )
    problems = vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es"))
    assert any("invalid YAML" in problem for problem in problems)


def test_missing_yaml_parser_is_reported(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "guide.md").write_text(
        "# Guide\n\n```yaml\nvalue: same # Note\n```\n", encoding="utf-8"
    )
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\n```yaml\nvalue: same # Nota\n```\n", encoding="utf-8"
    )
    monkeypatch.setitem(sys.modules, "yaml", None)
    problems = vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es"))
    assert any("Install requirements-dev.txt" in problem for problem in problems)


def test_unchanged_yaml_needs_no_comment_parser(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = '```yaml\nvalue: "intentionally incomplete\n```\n'
    (repo / "guide.md").write_text(f"# Guide\n\n{text}", encoding="utf-8")
    (repo / "translations" / "es" / "guide.md").write_text(f"# Guía\n\n{text}", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert vt.check_code_parity(vt.build_pairs(repo, repo / "translations" / "es")) == []


def test_rejected_term_in_prose_is_reported(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nAbra el área de trabajo de desarrollo.\n", encoding="utf-8"
    )
    problems = vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es")
    assert any("área de trabajo" in p for p in problems)


def test_rejected_term_in_diagram_is_reported(repo: Path) -> None:
    (repo / "assets" / "es" / "flow.svg").write_text(
        "<svg><text>Canalización de despliegue</text></svg>", encoding="utf-8"
    )
    problems = vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es")
    assert any("flow.svg" in p for p in problems)


def test_glossary_may_quote_rejected_terms(repo: Path) -> None:
    """Reference files explain why terms are wrong, so they must be exempt."""
    (repo / "translations" / "es" / "GLOSARIO.md").write_text(
        "# Glosario\n\nNo se usa «área de trabajo»; se usa *workspace*.\n", encoding="utf-8"
    )
    assert vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es") == []


def test_tu_form_is_reported(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nPuedes abrir el workspace cuando quieras.\n", encoding="utf-8"
    )
    definite, _ambiguous = vt.check_register(repo, repo / "translations" / "es")
    assert len(definite) >= 1


def test_ambiguous_verb_is_not_a_failure(repo: Path) -> None:
    """'consulta' is third-person indicative here, not a tú imperative."""
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nEl script consulta el estado del trabajo.\n", encoding="utf-8"
    )
    definite, ambiguous = vt.check_register(repo, repo / "translations" / "es")
    assert definite == []
    assert len(ambiguous) == 1


def test_stranded_feminine_determiner_is_reported(repo: Path) -> None:
    """Replacing 'área de trabajo' with 'workspace' strands the feminine article."""
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nSe abre la workspace de desarrollo.\n", encoding="utf-8"
    )
    problems = vt.check_gender(repo, repo / "translations" / "es")
    assert any("la workspace" in p.lower() for p in problems)


@pytest.mark.parametrize(
    "phrase",
    [
        "la Workspace Identity",
        "una Workspace Identity",
        "las Workspace Identities",
        "estas Workspace Identities",
        "la\nWorkspace Identity",
    ],
)
def test_feminine_workspace_identity_is_allowed(repo: Path, phrase: str) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        f"# Guía\n\nSe verifica {phrase}.\n", encoding="utf-8"
    )
    assert vt.check_gender(repo, repo / "translations" / "es") == []


@pytest.mark.parametrize(
    "phrase",
    ["la workspace de desarrollo", "las workspaces de desarrollo", "la workspace IdentityProvider"],
)
def test_workspace_identity_exception_does_not_hide_gender_errors(repo: Path, phrase: str) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        f"# Guía\n\nSe verifica {phrase}.\n", encoding="utf-8"
    )
    assert vt.check_gender(repo, repo / "translations" / "es")


def test_verb_desencadenado_is_allowed_but_noun_is_not(repo: Path) -> None:
    es = repo / "translations" / "es"
    doc = es / "guide.md"
    doc.write_text("# Guía\n\nEl flujo se ejecuta desencadenado por un push.\n", encoding="utf-8")
    assert vt.check_terminology(repo, es, repo / "assets" / "es") == []

    doc.write_text("# Guía\n\nSe configura un desencadenador de rama.\n", encoding="utf-8")
    assert vt.check_terminology(repo, es, repo / "assets" / "es") != []


def test_hardcoded_sense_only_flagged_near_an_id(repo: Path) -> None:
    es = repo / "translations" / "es"
    doc = es / "guide.md"
    doc.write_text("# Guía\n\nEl valor va codificado en base64.\n", encoding="utf-8")
    assert vt.check_terminology(repo, es, repo / "assets" / "es") == []

    doc.write_text("# Guía\n\nEl GUID queda codificado en el archivo.\n", encoding="utf-8")
    assert vt.check_terminology(repo, es, repo / "assets" / "es") != []


@pytest.mark.parametrize(
    "phrase",
    [
        "personas desarrolladoras",
        "persona usuaria",
        "personas aprobadoras",
        "persona operadora",
        "personas revisoras",
        "persona administradora",
    ],
)
def test_inclusive_variant_is_reported(repo: Path, phrase: str) -> None:
    """The corpus settled on masculine generics; mixing the two forms is the defect."""
    (repo / "translations" / "es" / "guide.md").write_text(
        f"# Guía\n\nPara la mayoría de las {phrase}.\n", encoding="utf-8"
    )
    problems = vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es")
    assert any(phrase in p for p in problems)


def test_invariable_person_phrases_are_accepted(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nLa persona designada y la persona responsable de la rotación.\n",
        encoding="utf-8",
    )
    assert vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es") == []


def test_standard_form_is_accepted(repo: Path) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nPara la mayoría de los desarrolladores.\n", encoding="utf-8"
    )
    assert vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es") == []


# ── Entry point ────────────────────────────────────────────────────────────


def test_main_exits_non_zero_on_failure(repo: Path, capsys: pytest.CaptureFixture) -> None:
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nAbra el área de trabajo.\n", encoding="utf-8"
    )
    assert vt.main(["--root", str(repo)]) == 1
    assert "ISSUES FOUND" in capsys.readouterr().out


def test_main_exits_zero_when_clean(repo: Path, capsys: pytest.CaptureFixture) -> None:
    assert vt.main(["--root", str(repo)]) == 0
    assert "ALL CHECKS PASSED" in capsys.readouterr().out


def test_main_errors_when_language_missing(repo: Path) -> None:
    with pytest.raises(SystemExit):
        vt.main(["--root", str(repo), "--lang", "pt"])
