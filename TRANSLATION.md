# Translation Guide

How translations work in this repository. **This file stays in English** — it is the shared contract between contributors who don't necessarily read each other's languages.

> Para leer este repositorio en español, véase [`translations/es/README.md`](translations/es/README.md).

---

## Core principle: English is canonical

The English files at the repository root are the **single source of truth**. Every translation is derived from them.

This has a practical consequence. If you find a technical error in a translated document, **fix the English original first**, then mirror the fix into the translation. Fixing only the translation creates a silent divergence that nobody can detect later.

If a translation and the English source disagree, **the English source is correct by definition**.

---

## Structure

```
README.md                          English, canonical
fabric-*.md                        English, canonical
assets/*.svg                       English diagrams
assets/es/*.svg                    Spanish diagrams (same filenames)

translations/
  es/
    README.md                      mirrors the root filename exactly
    fabric-*.md
    GLOSARIO.md                    terminology decisions
    GUIA-DE-ESTILO.md              variant, register, anglicisms
```

Translated files **mirror the English filename exactly**. `fabric-hybrid-cicd-guide.md` at the root becomes `translations/es/fabric-hybrid-cicd-guide.md` — never a renamed or `-es`-suffixed variant.

Adding a language means adding one directory (`translations/pt-BR/`). Nothing else moves.

### Language codes

| Language | Code | Why |
|---|---|---|
| Spanish | `es` | Microsoft Learn serves a single Spanish locale — `es-mx` URLs canonicalize to `es-es`. One neutral Spanish, no country variants. |
| Portuguese *(future)* | `pt-BR` | Microsoft maintains `pt-br` and `pt-pt` as genuinely distinct locales and publishes **no** neutral-Portuguese style guide. A Portuguese translation must pick one and say so. |

---

## What gets translated

### Translate

- Prose, headings, table headers, table cell prose, list items, blockquotes
- Link **text** (but not link targets — see below)
- Prose labels inside ASCII-art diagrams in code fences
- `<text>` content in SVG diagrams
- Code **comments**, where a code sample contains them

### Never translate

| Category | Examples |
|---|---|
| Shell and CLI commands | `pip install -r requirements-dev.txt`, `python scripts/workspace_swap.py --swap-to-dev` |
| Python identifiers, YAML keys, JSON keys | `publish_all_items()`, `on:`, `jobs:`, `find_replace` |
| File and directory paths | `data/fabric/`, `scripts/workspace_swap.py` |
| Workflow and config filenames | `deploy-test.yml`, `parameter.yml` |
| Branch names | `dev`, `test`, `main`, `feature/*` |
| Environment variables, secrets, repository variables | `FABRIC_WORKSPACE_ID`, `AZURE_CLIENT_ID`, `DEPLOY_METHOD` and its values (`fabric-cicd`, `bulk`) |
| Fabric item types as used by the APIs | `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`, `Lakehouse` |
| Product and tool names | Microsoft Fabric, GitHub Actions, fabric-cicd, Direct Lake |
| Verbatim tool output and error messages | Anything a reader will actually see in English on their own screen |

For tool output, translate a **gloss outside the code fence** rather than the output itself. The reader needs to match what the docs show against what their terminal prints.

### Never translated, entire directories

- `scripts/` — executable code
- `tests/` — executable code
- `data/` — written by Fabric Git integration; Fabric owns those bytes
- `.github/` — **all of it**, including workflows, `copilot-instructions.md`, `instructions/*.instructions.md`, and `prompts/*.prompt.md`

The `.github/` exclusion is not stylistic. Those files are **model input** consumed by GitHub Copilot through path matching, not documentation for humans. Translating them degrades agent behavior. Microsoft's own translation tooling (`Azure/co-op-translator`) hard-codes `.github` into its excluded directories for the same reason.

### Product UI strings and technical terms

**Default to English.** Readers of this documentation work with Fabric, Git, and GitHub daily, almost always with an English-language interface. A literally translated technical term is usually *less* recognizable than the original — the canonical example being *pipeline*, whose literal Spanish translation ("tubería") nobody would ever use to discuss CI/CD.

So **Fabric item types and portal feature names stay in English**, including in running prose: *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*, *Branch Out*, *Update from Git*, *Deployment Pipelines*.

Translate only where the target-language equivalent is firmly established and transparent to any practitioner — *branch* → "rama", *repository* → "repositorio", *workspace* → "área de trabajo".

Where a term stays in English and a localized portal string exists, gloss it in parentheses on first use:

```markdown
Las ***Deployment Pipelines*** (canalizaciones de implementación en el portal en español) permiten...
```

Terminology for the terms that *are* translated starts from **Microsoft Terminology**, not from `learn.microsoft.com/es-es` prose. The Spanish Fabric documentation is machine-translated (`ms.translationtype: MT`) and is internally inconsistent — the Git integration page uses both "espacio de trabajo" and "área de trabajo" in a single paragraph. Link to it for the reader's convenience; never mine it for terminology.

**But Microsoft Terminology is the starting point, not the final authority.** It records the *official* term, which is not always the one practitioners use. Where a native reviewer says the official term isn't what people actually say, the reviewer wins. Spanish examples, all overriding the official form: *workspace* (not "área de trabajo"), *Service principal* (not "entidad de servicio"), *pipeline* (never "canalización" — the official term, and reportedly not understood in context).

### Register

Professional technical documentation is **impersonal**. Where direct address is unavoidable, use the formal form — in Spanish, *usted*. Never the familiar *tú*.

This matches Microsoft's own Spanish documentation, which combines impersonal constructions ("La estructura del área de trabajo **se conserva** en el repositorio") with formal imperatives ("**Consulte** la lista de elementos admitidos").

Each language records its own register decision in its style guide.

---

## Links

### Between documents

Inside `translations/es/`, link to sibling documents with a **bare relative filename**:

```markdown
Véase la [Guía de implementación híbrida](fabric-hybrid-cicd-guide.md).
```

GitHub resolves relative links against the current file, so this automatically lands on the **Spanish** sibling. This is what keeps a reader inside their language without any tooling.

### To shared files

Reach up two levels — never use a root-anchored `/path`, which works on github.com but breaks in local clones and editors:

```markdown
[workspace_swap.py](../../scripts/workspace_swap.py)
![Flujo recomendado](../../assets/es/hybrid-recommendation-flow.svg)
```

### To documents not yet translated

Link to the English original and label it:

```markdown
[Guía de CI/CD masivo](../../fabric-bulk-cicd-guide.md) (solo en inglés)
```

### Anchors

GitHub derives heading anchors from heading **text**, and its Markdown renderer does not support custom anchor IDs. Translating a heading therefore changes its anchor.

So within a translated document, **every cross-reference and table of contents must be regenerated against the translated headings**. Do not copy anchors from the English source.

### External documentation links

Microsoft Learn links may be localized by swapping the locale segment: `learn.microsoft.com/en-us/...` becomes `learn.microsoft.com/es-es/...`. Those pages are machine-translated; that is acceptable for reader convenience and is disclaimed in each translated file's footer.

---

## The language switcher

GitHub has **no** built-in language switcher and no content negotiation, so the switcher is written into the Markdown by hand.

**Every document in both languages carries one**, not just the README. Readers arrive via deep links, not only via the landing page.

First line of the file, above the `#` heading. The current language is bold text, not a link.

English document at the root:

```markdown
**English** | [Español](translations/es/fabric-development-process.md)
```

Its Spanish counterpart:

```markdown
[English](../../fabric-development-process.md) | **Español**
```

Rules:

1. **Label each language in its own language** — `Español`, not `Spanish`; `English`, not `Inglés`. A reader stranded on a page they cannot read must be able to recognize the way out.
2. **No flags.** Languages are not countries. Spanish is official in 21 nations and this project uses neutral Spanish specifically to avoid privileging any one of them.
3. **Add the English-side switcher only when its translation merges.** A switcher pointing at a file that doesn't exist yet is a broken link and will fail the link-check workflow.

---

## Staying in sync

Every translated file opens with a **source stamp** recording the English commit it was translated from:

```markdown
<!-- source: README.md @ 9aa6823 | translated: 2026-09-22 -->
```

When the English source changes, its translations become stale. That is expected and acceptable — what is *not* acceptable is stale translations being invisible.

**English documentation is never blocked on translation.** Edit English freely; translations catch up as separate work. A stale translation is a tracked task, not a merge blocker.

---

## Contributing a translation

1. **One language per pull request.** Reviewing a PR that changes several languages at once is impractical, and reviewers usually only read one of them.
2. **One document per pull request**, including that document's diagrams and its English-side switcher line. Very long documents may be split by section.
3. **Read that language's glossary and style guide first** — for Spanish, [`translations/es/GLOSARIO.md`](translations/es/GLOSARIO.md) and [`translations/es/GUIA-DE-ESTILO.md`](translations/es/GUIA-DE-ESTILO.md). Start with the glossary's "false friends and recurring traps" table: those are mistakes already caught once, and they recur. Consistency with existing translations matters more than individual preference.
4. **Machine translation is a starting point, never the final result.** Every translation is reviewed by a fluent speaker before merge. Reviewers should follow [`translations/es/REVISION.md`](translations/es/REVISION.md).
5. **Update the source stamp** to the commit your translation is based on.
6. If you improve terminology, **update the glossary in the same PR** so the next translator inherits the decision. A correction that isn't written down will be made again.

## Starting a new language

Each language keeps its own glossary and style guide, but the following was learned from the Spanish pilot and applies to any language. Establish each of these *before* translating the second document, not after.

1. **Default technical terms to English**, then justify each exception. Readers work in an English-language product interface; a literally translated technical term is usually less recognizable than the original. Spanish rejected the official translations of *workspace*, *service principal*, and *pipeline* on exactly these grounds.
2. **Decide the register once and write it down.** Professional documentation is impersonal, using the formal form where direct address is unavoidable. The real risk is not picking wrong — it is mixing forms within a document.
3. **Name a reviewer before starting.** A translation nobody maintains is worse than no translation, because readers assume an official-looking page is current.
4. **Record a false-friends table from the first review.** These recur in every document, and are the highest-value thing a reviewer produces. Watch especially for a target-language word that is correct in isolation but collides with another use in the same sentence — Spanish "equipo" meant both *team* and *laptop* two clauses apart.
5. **Watch for one English word covering two senses.** English uses *implementation* and *deployment* almost interchangeably; Spanish needs "implementación" and "despliegue" kept apart or the meaning blurs. Check for this pair, and for any other near-synonym the source language treats loosely.
6. **Vendor terminology is a starting point, not an authority** — see the note under "Product UI strings and technical terms" above.

### Translated file skeleton

```markdown
[English](../../README.md) | **Español**

<!-- source: README.md @ 9aa6823 | translated: 2026-09-22 -->

> 📄 La versión en inglés de este documento es la autoritativa.
> Si encuentra una discrepancia, [el original en inglés](../../README.md) tiene precedencia.

# Título del documento

...contenido...

---

*Este documento es una traducción de [README.md](../../README.md). Las traducciones
pueden quedar desactualizadas respecto al original en inglés, que es la fuente
autorizada. Los errores pueden comunicarse abriendo una incidencia e indicando el idioma.*
```

---

## Diagrams

SVG diagrams are translated into `assets/es/` using **identical filenames**. Spanish documents reference `../../assets/es/<name>.svg`.

- The SVGs are hand-authored XML — translate the `<text>` node contents directly.
- Keep script names, git commands, workflow filenames, and branch names untranslated inside diagrams.
- Fonts are `Segoe UI, Arial, sans-serif` and the files already contain non-ASCII characters, so accented Spanish renders without any encoding changes.
- **Do not convert text to curves.** It would make the diagrams non-editable and unmaintainable.
- Spanish runs roughly 15–25% longer than English. Labels sit in fixed-width boxes, so widen the box or shorten the label rather than letting text overflow.

---

## Validation

A link-check workflow runs on every pull request and catches the most common translation defect: a copied file whose `../` depth is now wrong.

Run it locally before pushing, if you have [lychee](https://github.com/lycheeverse/lychee) installed:

```bash
lychee --offline './**/*.md'
```

---

## What is never translated, and why

| File | Reason |
|---|---|
| `LICENSE` *(if added)* | License translations have no legal validity and an error in one could be genuinely harmful. The Free Software Foundation declines to approve license translations for exactly this reason. |
| `SECURITY.md` *(if added)* | A reporting protocol read by security teams and automated tooling. |
| `.github/**` | Model input for Copilot and CI configuration, not human documentation. |
| `CODE_OF_CONDUCT.md` *(if added)* | Link to the canonical upstream translation rather than forking a copy that can drift. |

---

## References

- [Microsoft Spanish (Neutral) Style Guide](https://aka.ms/spanish-neutral-styleguide)
- [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology)
- [Microsoft — Writing for a global audience](https://learn.microsoft.com/en-us/style-guide/global-communications/)
- [Google — Write for translation](https://developers.google.com/style/translation)
- [Kubernetes — Localizing documentation](https://kubernetes.io/docs/contribute/localization/)
- [W3C — Linking to translated pages](https://www.w3.org/International/questions/qa-site-conneg)
