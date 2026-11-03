---
name: quickbase-qbl-analyzer
description: Parse a Quickbase QBL (Quickbase Language) export into a queryable inventory, then answer questions about the application - architecture, data model, pipelines and integrations, formulas, permissions, dependencies, and technical debt. Also produces an Excel workbook and CSVs. Use for QBL parsing, architecture review, impact analysis ("what breaks if I change this field"), pipeline and integration review, solution inventory, and application documentation. Accepts one QBL YAML file plus an optional Quickbase table schema JSON file. Supports QBL schema versions through v0.15.
license: MIT
---

# QBL Solution Analyzer

Turn a Quickbase QBL export into something you can ask questions about.

The primary use is interpretation: explaining what an application does, how its pipelines and integrations work, what depends on what, and where the risks are. A spreadsheet and CSVs come out of the same run for users who want them.

Use this Skill only with files supplied by the user. Never call Quickbase or any other external API. Never request or use a user token, service-account token, password, `.env` file, or credentials file of any kind.

## Inputs

Required:

- One QBL export in YAML format. The filename may end in `.yaml`, `.yml`, or `.txt`.

Optional:

- One Quickbase table schema JSON file, which adds runtime table IDs, table names, and storage metadata.

Everything else — including the field and role IDs the export declares — comes from the QBL file itself, so the analysis is complete without it.

## Workflow

### 1. Parse once

```bash
python3 <skill-dir>/scripts/qbl_analyzer.py summary \
  "<qbl-file>" \
  --output-dir "<output-dir>" \
  --label "<solution-label>"
```

Add `--table-schema "<file>"` when one was supplied.

This writes the queryable inventory and every artifact. Run it once per solution and reuse the output directory for the rest of the conversation. Do not re-parse to answer a follow-up question.

### 2. Read the digest

Read `solution-digest.md` in full. It covers the architecture, the integration surface, logic and automation counts, validation findings, and quality signals, and it is usually enough on its own to answer "what does this application do?"

Nothing in the digest is sampled — every table, relationship, role, pipeline, outbound endpoint, and flagged field is listed, because a truncated list is indistinguishable from a complete one. It therefore grows with the solution. On a large solution, read the architecture and integration sections and query for the long lists rather than loading the whole file.

### 3. Query for anything deeper

```bash
python3 <skill-dir>/scripts/qbl_analyzer.py collections "<output-dir>"
python3 <skill-dir>/scripts/qbl_analyzer.py query "<output-dir>" <collection> \
  --where "<column>=<value>" --columns "A,B,C"
```

Only matching rows are printed, so the cost scales with the answer rather than the solution. Queries run in well under a second even on a 20 MB inventory.

**Do not read `parsed-qbl.json` directly** unless the solution is small. It runs 7-12x the size of the source QBL — on a large realm that is tens of megabytes. Query it instead.

`references/analysis-guide.md` maps common questions to concrete commands. Consult it before improvising a query.

### 4. Report

When reporting validation findings, keep errors and warnings apart. The manifest gives both as `validation_error_count` and `validation_warning_count`, and `validation_by_layer` says which layer found what. Errors are what Quickbase rejects; warnings are pre-existing configuration debt, most often a `!BadRef` the platform itself wrote into the export. Reporting one combined total makes a healthy application look broken.

Give the fix each finding carries rather than improvising one — for several codes the obvious response is the wrong one. An unrecognised resource type, for instance, is skipped by Quickbase with a warning rather than rejected, so the object is simply missing and the fix is correcting the type name, not adding properties. `references/output-guide.md` lists the layers and what each one checks.

Answer the question, grounded in the queries you ran. Return `solution-overview.xlsx` and `qbl-solution-overview.zip` when the user wants the spreadsheet, or when a full inventory is the point of the request.

## Interaction model

Ask only the minimum needed to identify the QBL file. Do not make users repeat what is already clear from their message, filenames, or file contents.

### Fast path

With one QBL candidate present, state the assignment and run:

```text
I'll analyze `<filename>`.
```

Then answer whatever the user actually asked. If they asked a question, lead with the answer, not with a list of generated files.

### Missing input

```text
Please upload the QBL export for the solution. A `.yaml`, `.yml`, or `.txt` file is accepted.

Optional: a Quickbase table schema JSON file, which adds runtime table IDs and table metadata.
```

### Several QBL candidates

```text
Which QBL should I analyze?

1. <filename one>
2. <filename two>
```

### Intake principles

- Ask one compact question at a time when clarification is required.
- Detect file types by content, not filename alone.
- Never ask for the optional table schema file unless its absence materially limits what the user asked for.
- If the user asked a question rather than requesting a report, answer the question. Mention the workbook once; do not lead with it.

See `references/conversational-intake.md` for response templates.

## File identification

- QBL files normally contain top-level `Solution` and `Resources` YAML keys.
- Table schema files are JSON arrays or API response objects containing table IDs, names, and aliases.

Ignore `.env`, `config.yaml`, Git metadata, generated workbooks, and cached files. If an uploaded file appears to contain credentials, stop processing that file, do not reproduce its values, and tell the user to remove it and rotate any potentially exposed credential.

## Outputs

The `summary` command prints a JSON manifest to stdout. A successful run has `"success": true`, and `next_steps` carries ready-to-run commands.

| File | Purpose |
|---|---|
| `solution-digest.md` | Size-capped orientation doc. **Read this first.** |
| `parsed-qbl.json` | Complete inventory. Query it; do not read it whole. |
| `solution-overview.xlsx` | Workbook, one sheet per populated collection |
| `solution-summary.md` | Short counts-and-signals summary |
| `csv/*.csv` | One CSV per populated collection |
| `manifest.json` | Run metadata and artifact paths |
| `qbl-solution-overview.zip` | Everything above |

## Accuracy rules

- The uploaded QBL export is the only source of truth. Do not infer entities that are not present in the file.
- Ground answers in queries you actually ran, and name the collection and filter when it matters.
- Distinguish what the QBL states from what you inferred. Say which is which.
- Report caps and truncation. The query footer tells you when `--limit` cut the output; pass that on rather than presenting a partial list as complete.
- Matrix collections carry one row per reference, so the same pair can repeat. Use `--distinct` for unique pairs, and do not report raw row counts as entity counts.
- The `Potentially Unused` flag is a starting point, not an answer. It is computed from the references the export records, including those from pipelines, custom emails, and connected tables, so a field read only by a live integration is not flagged. What it still cannot see is anything outside the export: a code page, a URL formula, an external integration. Use the split in the digest's quality section, which separates fields with no reference anywhere from fields still referenced by a cross-reference collection, and never present the raw flag as a delete list.
- Without a table schema file, runtime table IDs, table names, and storage metadata are blank. Runtime application IDs are never available, because a QBL export does not carry them.
- Reject files larger than the script safety limit rather than attempting partial parsing.
- If parsing fails, return the sanitized error message and identify which file failed.
- Do not claim a run completed unless the script returned `"success": true` and the expected artifacts exist.

## Hardcoded credentials

A QBL export can carry secrets in plain text — an API key in a pipeline URL or request body, a token in an application variable, a key in a code page. Every run scans for these and reports the count as `possible_credential_count` in the manifest.

When the count is above zero:

1. Lead with it. It outranks whatever else the user asked about.
2. Read the `## Possible hardcoded credentials` table at the top of `solution-digest.md`. It masks values and names the exact location of each.
3. Recommend rotating each one and replacing the literal with a stored credential reference.
4. Tell the user the generated artifacts are sensitive until rotation is done. Values are **not** redacted anywhere outside that table — the digest, `parsed-qbl.json`, and the CSVs all carry them, which is what makes remediation possible.

Use the masked table when discussing findings in chat. Quote a full credential only if the user explicitly asks for the value.

Detection is conservative: stored-credential references such as `{{ secrets.key }}` are the correct pattern and are never flagged. It is not exhaustive — a custom or unrecognized token format can slip through, so a count of zero is not proof an export is clean.

## Privacy

QBL exports describe real applications. Explaining formulas, pipeline configuration, page code, and integration endpoints is the purpose of this Skill — quote them freely when they answer the question. What to avoid is bulk dumping: do not paste an entire export or a whole collection into chat when a targeted answer will do.

See `references/analysis-guide.md`, `references/input-guide.md`, and `references/output-guide.md` for detail.
