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
- **Anchors:** GitHub derives anchors from heading text, so translating a heading changes its anchor. Regenerate every table of contents and cross-reference against the *translated* headings. Never copy anchors from the English source.
- **Links between translated documents:** bare relative filenames (`fabric-hybrid-cicd-guide.md`), which resolve to the translated sibling automatically.
- **Links to shared files:** `../../scripts/...`, `../../assets/es/...`. Never root-anchored `/path`.
- **Links to untranslated documents:** point at the English original and label it, e.g. `*(solo en inglés)*`.
- **External documentation links stay English** (`/en-us/`), never the localized locale.
- **Diagrams:** translate `<text>` content only, into `assets/<lang>/` with identical filenames. Keep script names, git commands, workflow filenames and branch names untranslated. Never convert text to curves. Verify no label overflows its box — translated text often runs longer than English.

## Find-and-replace hazards

Bulk replacement has caused real defects in this repository. After any terminology sweep:

- **Check gender and number agreement.** Replacing a feminine noun with a masculine one (*área de trabajo* → *workspace*) leaves articles, pronouns and adjectives stranded, and find-and-replace will not catch them.
- **Never rewrite inside a verbatim quotation**, even if it uses terminology this repository has rejected.
- **Re-read the surrounding sentence**, not just the replaced token.

## Before finishing

- Verify every relative link in changed files resolves.
- Verify anchors match translated headings.
- If a diagram changed, render it and check for overflow.
- If terminology changed, update `GLOSARIO.md` in the same change so the next translator inherits the decision.
