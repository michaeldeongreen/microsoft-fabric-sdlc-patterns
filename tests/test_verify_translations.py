"""Unit tests for scripts/verify_translations.py."""

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


def test_inclusive_variant_is_reported(repo: Path) -> None:
    """The corpus settled on 'desarrollador(es)'; mixing the two forms is the defect."""
    (repo / "translations" / "es" / "guide.md").write_text(
        "# Guía\n\nPara la mayoría de las personas desarrolladoras.\n", encoding="utf-8"
    )
    problems = vt.check_terminology(repo, repo / "translations" / "es", repo / "assets" / "es")
    assert any("personas desarrolladoras" in p for p in problems)


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
