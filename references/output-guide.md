# Output Guide

One `summary` run writes every artifact into a single output directory and bundles them into one ZIP.

## solution-digest.md -- read this first

The orientation document, and the intended entry point for answering questions.

Structural inventories are listed in full rather than sampled. A truncated table or pipeline list reads exactly like a complete one, and Quickbase places no limit on how many a solution may contain, so sampling them would silently misrepresent the architecture.

| Solution | Digest size |
|---|---|
| 9 fields | ~3 KB |
| 9,600 fields, 240 tables, 40 pipelines | ~368 KB |

The larger figure is a synthetic worst case in which nearly every field is unreferenced, so the unused-field list dominates. A real application produces a much smaller digest. When it is large, query instead of reading it whole — the same rule that applies to `parsed-qbl.json`.

Sections:

- **Possible hardcoded credentials** — present only when something was found. Appears first, ahead of the architecture, because it is the one section that is urgent rather than descriptive. Values are masked in the table; they are not redacted elsewhere.

- **Architecture** — apps, tables with field counts and runtime IDs, relationships, roles
- **Integration surface** — pipelines with the tables and fields each touches, outbound HTTP calls, channels in use, connected tables, external resources
- **Logic and automation** — counts of formula fields, formula-query fields, lookups, summaries, form rules, custom emails, document templates, code pages, home page widgets, app guides
- **Validation findings** — every distinct finding, with the layer that produced it, its severity, and the fix
- **Quality signals** — duplicate report groups and fields flagged `Potentially Unused`, split into those with no reference in any collection and those some collection still references, which are not safe to treat as unused
- **Full inventory counts** — row count per populated collection

Nothing is capped or truncated. Digest size grows with the solution; that is a deliberate trade, because a truncated list is indistinguishable from a complete one.

## parsed-qbl.json -- query, do not read

The complete normalized inventory: every collection, entity counts, parser warnings, and validation issues.

It runs 7-12x the size of the source QBL, because the parser expands each entity with resolved IDs, cross-references, and usage flags. A 1.6 MB synthetic QBL produced a 20 MB inventory — far past what belongs in context.

Use the `query` subcommand instead. It loads the file inside the analyzer process and prints only matching rows, so a question costs what the answer costs. See `analysis-guide.md`.

## solution-overview.xlsx

Opens on an Overview sheet listing every parsed collection, its row count, and whether it was included or empty. Each populated collection then gets its own sheet with frozen headers and autofilters.

Depending on the export, sheets may include application settings and variables, parameter definitions, roles and the field-to-role matrix, tables, fields, relationships, connected tables, external resources, forms and form rules, field-to-form usage, dashboards, pages, reports, report dependencies, duplicate reports, pipelines and pipeline steps with table and field usage, custom emails and document templates, charts and report groups, parser warnings, and validation issues.

## Validation findings

The parser runs five validation layers over the document. Every finding carries
a code, the layer that produced it, a severity, and the fix.

| Prefix | Layer | Question it answers |
|---|---|---|
| `SCH` | Schema | Is this node's own shape right - required properties present, no unknown ones, type recognised? |
| `REF` | Reference | Does every `!Ref` resolve, and to a resource of the kind its key names? |
| `VAL` | Value | Is the value the right kind of thing - a reference where a reference belongs, a number where a number belongs? |
| `STR` | Structure | Container-level rules no single node can express, such as an application with no home page. |
| `FML` | Formula | Does a formula name a field that exists? No other layer can see inside a formula body. |

Severity is what separates a defect from debt:

- **error** - the platform rejects this. It blocks a deployment.
- **warning** - pre-existing configuration debt, most often a `!BadRef` that
  Quickbase itself wrote into the export because a reference could not be
  resolved at export time. It deploys fine and is worth reporting as technical
  debt, not as a blocker.

The digest and `solution-summary.md` both group findings by code, because a
large export is usually a dozen distinct problems repeated many times and the
fix is per code. Every occurrence, with its path and logical ID, is in the
`Validation Issues` sheet and in `parsed-qbl.json`.

Report errors and warnings as separate numbers. A single combined total makes a
healthy application look broken.

## solution-summary.md

A short counts-and-signals summary — under 1 KB regardless of solution size. Useful as a header for a written report. The digest supersedes it for analysis.

## csv/*.csv

One CSV per populated collection, for users who want to pivot the data themselves. These are also a reasonable fallback for ad-hoc inspection with standard shell tools, though `query` handles CSV quoting and column selection more reliably.

## manifest.json

Run metadata: input file, QBL version, entity counts, warning and issue counts (`validation_error_count`, `validation_warning_count`, and `validation_by_layer`), and the path of every artifact. A successful run has `"success": true`. The `next_steps` object carries ready-to-run `collections` and `query` commands for that output directory.

## qbl-solution-overview.zip

Everything above.

## Enrichment limits

Runtime table IDs, table names, and table storage metadata come from the optional table schema file and are blank without it.

Runtime application IDs are never available, because a QBL export does not carry them.
