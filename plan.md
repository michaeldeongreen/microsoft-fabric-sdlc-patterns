> ⚠️ **TEMPORARY WORKING FILE — DELETE BEFORE PR.**
> Scratch planning artifact for the `feature/i18n-spanish` branch, committed only so the plan
> survives session loss. It is not a deliverable and must not reach `dev`.
> The permanent, contributor-facing policy lives in `TRANSLATION.md`.

# Plan: Multilingual (Spanish, later Portuguese) for microsoft-fabric-sdlc-patterns

## 1. What this repository is

A **reference implementation and solution accelerator** for the Microsoft Fabric developer workflow and CI/CD pipeline. It is not a library — it is an opinionated, end-to-end working example plus the written guidance that explains the choices.

It has two halves:

| Half | Contents | Audience |
|---|---|---|
| **Executable reference** | `scripts/` (5 stdlib-only Python CLIs), `tests/` (pytest), `.github/workflows/` (13 workflows), `data/fabric/` (9 real Fabric item definitions, git-synced from a live workspace), `data/fabric/parameter.yml` | Engineers who clone and run it |
| **Written guidance** | 7 root-level Markdown docs (~24,400 words), 6 hand-authored SVG diagrams | Engineers, architects, decision-makers |

**The written guidance is the product.** The docs are why someone finds this repo — the code exists to prove the docs are real. That is exactly what makes translation worth doing, and it also defines the scope: **translate the guidance, never the executable reference.**

### Document inventory (translation scope)

| Document | Words | Role |
|---|---|---|
| `README.md` | 1,247 | Landing page, architecture, quick start |
| `fabric-development-process.md` | 2,113 | Day-to-day Branch Out workflow |
| `fabric-cicd-governance-considerations.md` | 2,188 | Identity, RBAC, approvals |
| `fabric-hybrid-cicd-guide.md` | 2,589 | Recommended fabric-cicd implementation |
| `fabric-bulk-cicd-guide.md` | 4,336 | Alternative Bulk API (Preview) path |
| `fabric-cicd-release-options.md` | 5,925 | Strategy evaluation — the "start here" doc |
| `fabric-sdlc-cicd-presentation.md` | 6,041 | Customer-facing presentation |
| **Total** | **~24,440** | |

### Repo-specific constraints discovered

1. **All internal doc links are flat siblings** (`fabric-hybrid-cicd-guide.md`), plus `assets/*.svg`, `.github/workflows/*.yml`, and `data/fabric/*`. Moving English docs would break every one of them plus all external bookmarks.
2. **Cross-doc links use heading anchors** (e.g. `fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis`), and 4 docs have hand-written Tables of Contents. GitHub derives anchors from heading text, so translated headings change anchors — TOCs and deep links must be regenerated in Spanish.
3. **95 of 136 external links point to `learn.microsoft.com/en-us/`** — all locale-swappable.
4. **The 6 SVGs are hand-authored text-based SVG** with 174 `<text>` nodes — translatable by editing XML, no design tool needed.
5. **`data/fabric/` is written by Fabric Git integration.** Never touch it; Fabric owns those bytes.
6. **Strict promotion path**: `enforce-promotion-path.yml` forces `dev → test → main`. Translation PRs target `dev` like everything else. `check-pr-ready.yml` and `run-tests.yml` both run on PRs and will pass on doc-only changes.
7. **No `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, or `SECURITY.md` exist today.** Nothing to translate there; noted as out of scope.

---

## 2. Decisions (confirmed)

| Decision | Choice |
|---|---|
| Structure | `translations/es/` mirroring root filenames |
| Rollout | Pilot `README.md` → native-speaker review → then scale |
| Variant | **Español neutro / internacional** (not es-ES, not es-MX) |
| Register | **tú**, favoring impersonal constructions |
| Review | Native speaker reviews before merge |

---

## 3. Target structure

```
README.md                                   ← English, canonical. Language table at top.
fabric-*.md                     (6 more)    ← unchanged, stay at root
assets/*.svg                    (6)         ← English diagrams, unchanged
assets/es/*.svg                             ← Spanish diagrams (Phase 4)
scripts/ tests/ data/ .github/              ← NEVER translated
TRANSLATION.md                              ← English. The contract.
TRANSLATION_STATUS.md                       ← English. Staleness dashboard.
translations/
  es/
    README.md                               ← identical filenames = trivial pairing
    fabric-development-process.md
    fabric-cicd-release-options.md
    fabric-hybrid-cicd-guide.md
    fabric-bulk-cicd-guide.md
    fabric-cicd-governance-considerations.md
    fabric-sdlc-cicd-presentation.md
    GLOSARIO.md                             ← Spanish. Terminology table.
    GUIA-DE-ESTILO.md                       ← Spanish. Variant, register, anglicisms.
  pt-BR/                                    ← Phase 5. Costs one mkdir.
```

**Why:** Kubernetes (`content/es/`), MDN (`files/es/`), and ~17 Microsoft repos (`translations/es/`) all use a per-locale directory for multi-document repos. The `README.es.md` suffix pattern is only common for single-README repos. Critically, GitHub resolves relative links *relative to the current file*, so `[guía](fabric-hybrid-cicd-guide.md)` inside `translations/es/` lands on the **Spanish** sibling for free — language containment with zero tooling.

**Locale codes:** `es` (Microsoft Learn has exactly one Spanish — `es-mx` URLs canonicalize to `es-es`). Portuguese later must be **`pt-BR`**, because Microsoft maintains `pt-br` and `pt-pt` as genuinely distinct locales with separate style guides and publishes **no** neutral-Portuguese guide.

---

## 4. Translate / Do-not-translate policy

### Translate

- Prose, headings, table headers and cell prose, list items, blockquotes, admonitions
- Link **text** (not link targets, except Learn locale swaps)
- Prose labels inside ASCII-art diagrams in code fences (e.g. the README architecture block)
- SVG `<text>` content (Phase 4)
- `learn.microsoft.com/en-us/` → `/es-es/` (95 links) — with a caveat, see below

### Never translate

| Category | Examples in this repo |
|---|---|
| Shell / CLI commands | `pip install -r requirements-dev.txt`, `python scripts/workspace_swap.py --swap-to-dev` |
| Python identifiers, YAML keys, JSON keys | `publish_all_items()`, `on:`, `jobs:`, `find_replace` |
| File and directory paths | `data/fabric/`, `scripts/workspace_swap.py`, `.github/workflows/` |
| Filenames of workflows and docs | `deploy-test.yml`, `parameter.yml` |
| Branch names | `dev`, `test`, `main`, `feature/*` |
| Env vars, secrets, repo variables | `FABRIC_WORKSPACE_ID`, `AZURE_CLIENT_ID`, `DEPLOY_METHOD` and its values (`fabric-cicd`, `bulk`) |
| Fabric item type names as used by APIs | `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology` |
| Product and tool names | Microsoft Fabric, GitHub Actions, fabric-cicd, Direct Lake |
| Verbatim tool output / error messages | Script stdout quoted in the docs — readers see English on screen; translate as a gloss *outside* the fence |
| Anything under `data/` | Fabric Git integration owns it |

### Entire directories excluded

`scripts/`, `tests/`, `data/`, and **all of `.github/`** — workflows, `copilot-instructions.md`, `instructions/*.instructions.md`, `prompts/*.prompt.md`.

`.github/` exclusion is not a stylistic call. Those files are **model input** consumed by Copilot via path-matching, and Microsoft's own co-op-translator hard-codes `.github` into `EXCLUDED_DIRS`. Translating them would degrade agent behavior. Instead we *extend* `copilot-instructions.md` (in English) with the translation contract, turning Copilot into an enforcer.

### Product UI strings — special handling

Fabric portal terms get **Spanish term + English in parentheses on first use per document**: `**canalizaciones de implementación** (*deployment pipelines*)`. Most Fabric practitioners run an English-locale portal, so the English must stay visible.

⚠️ Terminology source is **Microsoft Terminology Search**, *not* `learn.microsoft.com/es-es` prose. The Spanish Fabric docs carry `ms.translationtype: MT` and are internally inconsistent — a single page uses both "pipelines de despliegue" and "Canalizaciones de despliegue". We link to `/es-es/` for reader convenience but never mine it for terminology, and `TRANSLATION.md` will say so.

### Anglicisms

Per RAE/ASALE *Diccionario panhispánico de dudas*: necessary, internationally-established foreign terms keep their original spelling but **must carry typographic emphasis (italics)**. Applied on first use per document, never inside code fences.

| English | Spanish | Note |
|---|---|---|
| branch | rama | Established equivalent |
| merge | fusionar | Established |
| commit (n.) | *commit* | No settled equivalent |
| commit (v.) | hacer *commit* / confirmar | Avoid "commitear" |
| pull request | *pull request* (PR) | GitHub UI term; gloss once |
| deployment | despliegue / implementación | Check Terminology for Fabric UI usage |
| pipeline | *pipeline* generic; canalización when naming Fabric UI | |
| workspace | área de trabajo | Confirm against Terminology |
| feature branch | *feature branch* | Established methodology name |

Final table lives in `translations/es/GLOSARIO.md` and is the reviewer's checklist.

---

## 5. Link integrity

Five mechanisms, layered:

1. **Sibling links stay relative and bare** — `fabric-hybrid-cicd-guide.md` inside `translations/es/` auto-resolves to Spanish. Language containment for free.
2. **Shared assets reach up two levels** — `../../assets/hybrid-recommendation-flow.svg`, `../../scripts/workspace_swap.py`. Never use root-anchored `/path` links: they work on github.com but break in clones and editors.
3. **Anchors translate in lockstep.** Translating `## Configuration Strategy` changes its GitHub anchor. Every cross-doc deep link and all 4 hand-written TOCs must be regenerated against the Spanish headings. GitHub's renderer does **not** support `{#custom-id}`, so the alternative — explicit `<a id="..."></a>` tags in both languages — is rejected as too invasive for the English docs.
4. **Untranslated targets link to English and say so**, e.g. `[Guía Bulk](../../fabric-bulk-cicd-guide.md) (solo en inglés)`. No silent fallback exists on raw GitHub.
5. **CI enforcement** — `lychee-action` over `./**/*.md` with `fail: true`. This catches the #1 translation bug class: a copied file whose `../` depth is now wrong.

### Discoverability (no switcher exists)

GitHub has **no** built-in language switcher. README precedence is `.github` → root → `docs`, with no locale dimension anywhere in GitHub's docs, and no localization mechanism for community health files. Every large project hand-builds a language table. So:

- English `README.md` gets a language table at the very top: `🌐 English | [Español](translations/es/README.md)`
- Each Spanish doc gets a header banner: link back to the English original + "English is the authoritative version"
- Each Spanish doc gets a footer disclaimer modeled on Microsoft's co-op-translator disclaimer

---

## 6. Staying in sync (the thing that kills translations)

Vue **stopped accepting new translations in 2025** — not for quality reasons, but because stale translations on an official domain "create more confusion than sending them to the English docs directly." MDN restricts to locales "that have active community maintenance teams." This risk is the single biggest threat to the effort and gets designed for on day one.

**Three controls:**

1. **Source-commit stamp** in every translated file:
   `<!-- source: README.md @ 8c15d84 | translated: 2026-09-22 -->`
2. **Staleness checker** — `scripts/check_translations.py`, stdlib-only, matching existing repo conventions (`encoding="utf-8"`, item-registry style, pytest coverage in `tests/`). Compares each stamp's SHA to `git log -1 --format=%H -- <source>`. Also emits `TRANSLATION_STATUS.md`.
3. **CI job** — runs on PRs, **labels `translation-stale` rather than blocking**. A blocking check would make every English doc edit hostage to a translator's availability, which is how translations get abandoned.

**Policy, stated in `TRANSLATION.md`:** English is canonical. Fix English upstream first, then mirror. One locale per PR (Kubernetes: "reviewing pull requests that change content in multiple localizations is problematic").

---

## 7. Phases and todos

### Phase 0 — Foundation (English only, no translation yet)
| ID | Task |
|---|---|
| `translation-contract` | Write `TRANSLATION.md`: canonical-source policy, do/do-not-translate lists, link rules, stamp format, PR workflow |
| `copilot-contract` | Extend `.github/copilot-instructions.md` with the translation contract so Copilot enforces it |
| `glossary-seed` | Seed `translations/es/GLOSARIO.md` and `GUIA-DE-ESTILO.md` (neutro + tú + RAE italics rule) |
| `terminology-lookup` | Resolve Fabric UI strings via Microsoft Terminology Search: *Deployment pipelines*, *Workspace*, *Variable library*, *Git integration*, *Semantic model*, *Lakehouse*, *Notebook* |
| `link-check-ci` | Add `lychee-action` workflow, SHA-pinned per `actions.instructions.md` |

### Phase 1 — Pilot
| ID | Task |
|---|---|
| `pilot-readme` | Translate `README.md` → `translations/es/README.md`. Includes banner, footer disclaimer, source stamp, `../../` asset links, translated ASCII architecture diagram labels, `/es-es/` Learn links |
| `language-table` | Add language table to English `README.md` |
| `pilot-review` | **Native-speaker review.** Reviewer validates glossary, register, and anglicism handling — then we amend `GLOSARIO.md` with what they corrected |

**Gate:** nothing in Phase 2 starts until the reviewer signs off. The glossary corrections from this review are the whole point of piloting.

### Phase 2 — Sync tooling
| ID | Task |
|---|---|
| `staleness-script` | `scripts/check_translations.py` + `tests/test_check_translations.py` |
| `staleness-ci` | CI job, non-blocking label |
| `codeowners` | `CODEOWNERS` routing `/translations/es/**` to the Spanish reviewer |

### Phase 3 — Scale, in priority order
Ordered by reader value, cheapest-first within that:
| ID | Doc | Words |
|---|---|---|
| `translate-devprocess` | `fabric-development-process.md` | 2,113 |
| `translate-release-options` | `fabric-cicd-release-options.md` — the "start here" doc | 5,925 |
| `translate-hybrid-guide` | `fabric-hybrid-cicd-guide.md` | 2,589 |
| `translate-governance` | `fabric-cicd-governance-considerations.md` | 2,188 |
| `translate-bulk-guide` | `fabric-bulk-cicd-guide.md` | 4,336 |
| `translate-presentation` | `fabric-sdlc-cicd-presentation.md` | 6,041 |

One doc = one PR into `dev`. Long docs may be split by section across PRs.

### Phase 4 — Diagrams
| ID | Task |
|---|---|
| `translate-svgs` | Translate 174 `<text>` nodes → `assets/es/`. Keep filenames identical; repoint Spanish docs. Keep `workspace_swap.py`, `git commit`, branch names untranslated inside diagrams |

### Phase 5 — Portuguese (deferred)
| ID | Task |
|---|---|
| `pt-br-pilot` | `translations/pt-BR/README.md`, same process. **`pt-BR` specifically — no neutral Portuguese exists.** Requires a Brazilian Portuguese reviewer before starting |

---

## 8. Method

**LLM-drafted, native-speaker-reviewed**, working in Git. Docusaurus' own assessment: Git-based translation is "easy to get started, free, low friction" for developer-run projects (React, Vue, MDN, TypeScript all use it); Crowdin/Weblate overhead exceeds the benefit at 7 documents.

Machine translation is used strictly **as a base, never as the final result** — Kubernetes: "machine-generated translation is insufficient on its own"; React's Spanish team: "siempre y cuando se utilice como base y no como resultado final."

`Azure/co-op-translator` is a considered alternative — it's Microsoft-native, MIT, and automates exactly this layout including link rewriting and source-hash staleness. **Deferred, not adopted**, because it requires Azure AI credentials and would auto-generate all 7 docs at once, which is precisely the big-bang approach we rejected. If Phase 3 volume becomes painful, revisit it there.

---

## 9. Open items / risks

- **Reviewer bandwidth is the binding constraint**, not translation throughput. 24,440 words is real review work. Phase 3 ordering exists so that value lands early if review capacity runs out.
- **Terminology Search is a Power BI–hosted app** — may need manual lookup rather than scripted extraction.
- **Learn `/es-es/` links are machine-translated.** We link to them but disclaim them. If a reviewer objects, the fallback is keeping `/en-us/` links throughout — decide during `pilot-review`.
- **The presentation doc may be better left in English** — it's customer-facing collateral where the presenter's own language may differ from the deck's. Worth a decision at Phase 3 rather than now.
- No `LICENSE` exists yet. If one is added: **never translate it** (FSF: unofficial license translations "can't do any legal harm" only as long as they're clearly unofficial; errors "could be disastrous").

---

## 10. Sources

- GitHub README precedence & relative links — docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
- GitHub community health file precedence — docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file
- Copilot repository custom instructions — docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions
- Microsoft Spanish (Neutral) Style Guide — aka.ms/spanish-neutral-styleguide
- Microsoft style guides index — learn.microsoft.com/en-us/globalization/reference/microsoft-style-guides
- Microsoft Terminology — learn.microsoft.com/en-us/globalization/reference/microsoft-terminology
- Microsoft "write for a global audience" — learn.microsoft.com/en-us/style-guide/global-communications/
- Google "Write for translation" — developers.google.com/style/translation
- RAE/ASALE, Tratamiento de los extranjerismos — rae.es/dpd/ayuda/tratamiento-de-los-extranjerismos
- Kubernetes localization guide (incl. SVG localization) — kubernetes.io/docs/contribute/localization/
- Kubernetes Spanish glossary — kubernetes.io/es/docs/contribute/localization_es/
- Azure/co-op-translator — github.com/Azure/co-op-translator
- Vue translation guidelines (why translations get shut down) — github.com/vuejs-translations/guidelines
- React universal translation style guide — github.com/reactjs/translations.react.dev
- MDN translated-content active-locale policy — github.com/mdn/translated-content
- Docusaurus i18n with Git (trade-offs) — docusaurus.io/docs/i18n/git
- lychee-action — github.com/lycheeverse/lychee-action
- FSF on license translations — gnu.org/licenses/translations.html
