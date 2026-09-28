---
applyTo: "translations/**, assets/es/**"
---

When creating or editing translated documentation in this repository:

## Read these first

1. **`translations/<lang>/GLOSARIO.md`** — terminology. Start with the **"Falsos amigos y trampas recurrentes"** table: those are mistakes already caught in review, and they recur in every document.
2. **`translations/<lang>/GUIA-DE-ESTILO.md`** — register, anglicisms, punctuation, headings.
3. **`TRANSLATION.md`** (repo root) — the full contract.

Entries marked **👤 Revisión** in the glossary are decisions by named native reviewers. **Apply them; do not re-litigate them**, and do not "correct" them back toward the vendor's official terminology.

## Terminology

- **Default to English, then justify exceptions.** A literally translated technical term is usually *less* recognizable than the original to someone running the product interface in English. Confirmed independently by two native reviewers for this repository.
- **Never translated, even in prose:** Fabric item types (*Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*), portal objects (*workspace*, *Fabric Capacity*, *Branch Out*), CI/CD vocabulary (*pipeline*, *commit*, *pull request*, *feature branch*, *Trigger*, *Service principal*).
- **Translate only firmly established equivalents:** *branch* → rama, *repository* → repositorio, *environment* → entorno, *deployment* → despliegue.
- **Native review outranks Microsoft Terminology.** The official term is the starting point, not the final answer.
- **Never mine `learn.microsoft.com/<locale>/` prose for terminology.** Those pages are machine-translated and internally inconsistent.

## Register

Impersonal by default; the formal form (*usted* in Spanish) where direct address is unavoidable. **Never the familiar form** (*tú*). Consistency within a document matters more than either choice.

## Mechanics

- **Source stamp:** every translated file opens with `<!-- source: <file> @ <short-sha> | translated: <date> -->`. Update it to the English commit the translation is based on; a stale stamp makes the staleness check fire a false positive.
- **Path mirroring:** translations mirror the English **path**, subdirectories included. `presentations/fabric-sdlc-cd.md` becomes `translations/es/presentations/fabric-sdlc-cd.md`, never a flattened or `-es`-suffixed name.
- **Link depth follows nesting.** From `translations/es/` shared assets are `../../`; from `translations/es/presentations/` they are `../../../`. A wrong depth renders as a broken link that looks fine in the diff — run `python scripts/verify_translations.py` to catch it.
- **Anchors:** GitHub derives anchors from heading text, so translating a heading changes its anchor. Regenerate every table of contents and cross-reference against the *translated* headings. Never copy anchors from the English source.
- **Links between translated documents:** bare relative filenames (`fabric-hybrid-cicd-guide.md`), which resolve to the translated sibling automatically.
- **Links to shared files:** reach the repo root with the depth matching the file's own nesting — `../../` from `translations/es/`, `../../../` from `translations/es/presentations/`. Never root-anchored `/path`.
- **Links to untranslated documents:** point at the English original and label it, e.g. `*(solo en inglés)*`.
- **External documentation links stay English** (`/en-us/`), never the localized locale.
- **Diagrams:** translate `<text>` content only, into `assets/<lang>/` with identical filenames. Keep script names, git commands, workflow filenames and branch names untranslated. Never convert text to curves. Leave geometry untouched. Measure rather than estimate — render and compare text width against box width.
- **Marp decks in `presentations/`:** never translate YAML frontmatter or the `style:` CSS block; do translate `header:` and the slide content. Copy the frontmatter from the source rather than retyping it. Slides have hard space limits, so render and check for overflow. The compiled HTML is a gitignored build artifact — rebuild it locally to check, but do not commit it. Decks get **no language switcher**: anything in the body renders onto a slide.

## Find-and-replace hazards

Bulk replacement has caused real defects in this repository. After any terminology sweep:

- **Check gender and number agreement.** Replacing a feminine noun with a masculine one (*área de trabajo* → *workspace*) leaves articles, pronouns and adjectives stranded, and find-and-replace will not catch them.
- **Never rewrite inside a verbatim quotation**, even if it uses terminology this repository has rejected.
- **Re-read the surrounding sentence**, not just the replaced token.

## Before finishing

- Run `python scripts/verify_translations.py` from the repository root. It checks links, anchors, code-fence parity, rejected terminology, register and gender agreement, and exits non-zero on failure. It is not wired into CI, so it has to be run deliberately.
- If a diagram changed, render it and check for overflow — the script does not measure geometry.
- If a Marp deck changed, rebuild its HTML and check for slide overflow. Wait for fonts to load before measuring; a measurement taken too early reports a few pixels of phantom overflow.
- If terminology changed, update `GLOSARIO.md` in the same change so the next translator inherits the decision, and add the rejected term to `REJECTED` in the script.
