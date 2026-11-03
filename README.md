# QBL Solution Analyzer

A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that turns a Quickbase QBL export into something you can ask questions about — and, from the same run, an Excel workbook and CSVs.

It runs entirely on files you supply. There is no Quickbase API client, no credential handling, and no network access.

## Two things it gives you

**A queryable model of the application.** Ask what a pipeline does, what breaks if you delete a field, which tables an integration writes to, who can see what, or where the technical debt is. A digest gives complete orientation; a query command answers the specifics without loading the whole inventory.

**A spreadsheet.** One sheet per populated collection, plus CSVs and normalized JSON.

## What it parses

Point it at a QBL export and it parses the whole solution into a structured inventory:

- Applications, application settings, variables, and parameter definitions
- Tables, fields, and relationships
- Roles, role permissions, and the field-to-role permission matrix
- Forms, form rules, and field-to-form usage
- Reports, charts, report groups, report field usage, report permissions, and duplicate-report detection
- Dashboards, pages, home page widgets, and application guides
- Pipelines, pipeline steps, and pipeline table/field usage
- Connected tables and external resources
- Custom emails and document templates, with their field and template references

On top of the inventory it surfaces quality signals — potentially unused fields and duplicate reports — and runs five validation layers over the document: schema shape, reference resolution, value domains, container-level structure, and field references inside formula bodies. Every finding carries a code, the layer that produced it, a severity, and the fix. Errors are what Quickbase rejects; warnings are pre-existing debt such as a `!BadRef` the platform itself wrote into the export.

Supports QBL schema versions 0.7, 0.9, 0.11, 0.12, 0.14, and 0.15.

## Inputs

**Required:** one QBL export in YAML format (`.yaml`, `.yml`, or `.txt`).

**Optional:** one Quickbase table schema JSON file. Each table in a QBL export declares an `AliasHint`; that alias joins to the table schema payload to add runtime table IDs, table names, and storage metadata. Everything else — including the field and role IDs the export declares — comes from the QBL file itself, so the inventory is complete without it.

See [`references/input-guide.md`](references/input-guide.md) for file shapes and examples.

## Usage

### As a Claude Skill

Install the directory as a Skill, upload a QBL export, and ask questions about the application. Claude parses once, reads the digest, and queries for specifics.

### From the command line

Parse once:

```bash
python3 scripts/qbl_analyzer.py summary path/to/solution-qbl.yaml --table-schema path/to/table-schema.json --output-dir ./output --label "Project Tracker"
```

Then explore. What collections and columns exist:

```bash
python3 scripts/qbl_analyzer.py collections ./output
```

Which outbound endpoints do our pipelines call:

```bash
python3 scripts/qbl_analyzer.py query ./output pipeline_steps --where "HTTP URL!=" --columns "Pipeline Name,HTTP Method,HTTP URL" --distinct
```

What references this field:

```bash
python3 scripts/qbl_analyzer.py query ./output field_pipeline_matrix --where "Field Logical ID=\$Field_Budget" --columns "Pipeline Name,Step Name,Reference Context"
```

Filters support `=`, `!=`, `=~` (contains), `!~`, and numeric `>` `<` `>=` `<=`. A bare `col=` matches blank cells, `col!=` matches non-blank. Repeat `--where` to AND conditions. Unknown collection and column names return the valid list.

## Outputs

| File | Contents |
|---|---|
| `solution-digest.md` | Size-capped orientation doc. **Read this first.** |
| `parsed-qbl.json` | Complete inventory. Query it rather than reading it whole. |
| `solution-overview.xlsx` | Overview sheet plus one sheet per populated collection |
| `solution-summary.md` | Short counts-and-signals summary |
| `csv/*.csv` | One CSV per populated collection |
| `manifest.json` | Run metadata, artifact paths, ready-to-run next-step commands |
| `qbl-solution-overview.zip` | Everything above, bundled |

## Scale

The inventory expands to 7–12x the source QBL, so it is not something to read directly. The digest and the query command exist to keep analysis cheap regardless of solution size. Measured on a synthetic 240-table, 9,600-field, 40-pipeline solution:

| | Size | Approx tokens |
|---|---|---|
| Input QBL | 1.6 MB | 416k |
| `parsed-qbl.json` | 20.4 MB | 5.1M |
| `solution-digest.md` | 368 KB | 92k |

Parsing took 3.3 seconds; individual queries against the 20 MB inventory returned in under 200 ms.

Nothing in the digest is sampled — all 240 tables, all 40 pipelines, all 200 outbound endpoints, and every flagged field. Truncating any of them would present an incomplete picture as if it were complete, and Quickbase places no limit on how many a solution may have. Digest size therefore grows with the solution; the `query` subcommand is there for when a targeted answer is cheaper than reading the whole thing.

The digest figure above reflects a synthetic worst case in which almost every field is unreferenced. A real application, where most fields are used, produces a substantially smaller digest.

See [`references/analysis-guide.md`](references/analysis-guide.md) for question-to-query patterns and [`references/output-guide.md`](references/output-guide.md) for artifact details.

## Tests

```bash
python3 -m unittest discover -s tests
```

Standard library only, no runner or install required. The tests drive the CLI against the fixtures in `tests/fixtures/` and cover artifact generation, table-schema enrichment (including cross-app lookup and summary targets), behavior with no table schema, every query operator and output format, error handling and exit codes, and a check that fields read only by pipelines are not flagged as unused.

`tests/test_privacy.py` is an ordinary test like the rest. It scans every file in the Skill, bundled dependencies included, and fails on an email address outside the documentation domains, a Quickbase hostname that is neither public nor a placeholder, a URL carrying a dbid, or a module that imports a networking library.

## Requirements

Python 3.9 or later. No install step and no network access.

Inputs are capped at 32 MB. Parsing expands a QBL export by roughly 150–200x in peak memory — it builds the entity inventory, cross-reference matrices, and usage analysis in RAM, so a 1.6 MB synthetic export peaks at about 255 MB. Raise `MAX_INPUT_BYTES` in `scripts/qbl_analyzer.py` if you have the headroom.

The QBL parser is in `scripts/qblparser/`. PyYAML and XlsxWriter are bundled as pure-Python trees under `scripts/vendor/`, trimmed to the modules the Skill imports, so there is nothing to install. See [`NOTICE`](NOTICE) for their licenses.

## Repository layout

```
SKILL.md                     Skill definition and runtime behavior
LICENSE, NOTICE, VERSION     MIT licence, third-party notices, version
tests/test_analyzer.py       Test suite (stdlib only)
tests/test_privacy.py        Fixture-hygiene and no-network tests
tests/fixtures/              Committed QBL fixtures
scripts/qbl_analyzer.py      CLI entrypoint: summary, collections, query
scripts/qbl_index.py         Table, field and role identifiers, indexed for the parser
scripts/query_engine.py      Filter and project collections
scripts/digest_writer.py     Size-bounded orientation digest
scripts/workbook_writer.py   Excel workbook generation
scripts/secret_scanner.py    Hardcoded credential detection
scripts/workflows/executive/ Inventory enrichment beyond the raw parse
scripts/qblparser/           QBL parser
scripts/vendor/{yaml,xlsxwriter}/  Bundled third-party dependencies
references/                  Analysis, input, output, and intake guides
```

## Hardcoded credential detection

A QBL export can carry secrets in plain text — an API key in a pipeline URL or request body, a token in an application variable, a key in a code page. Every run scans pipeline steps, application variables, parameter definitions, code pages, custom emails, field formulas, and external resources, and reports `possible_credential_count` in the manifest. Findings appear at the top of `solution-digest.md` with masked values and the exact location of each:

```
| Where                                    | Field                      | Kind         | Value                 |
| Leaky Integration / Call Vendor API / s0 | `pipeline_steps.HTTP URL`  | Stripe key   | `sk_l************00`  |
| $App_S / VendorApiKey                    | `application_variables.Value` | Stripe key | `sk_l************00` |
```

Detection covers common vendor token formats (AWS, GitHub, GitLab, Stripe, Slack, Google, SendGrid, Shopify, npm, DigitalOcean, JWTs, PEM private keys), basic auth embedded in URLs, and credential-named query or JSON keys carrying a plausible value.

Two deliberate limits:

- **Nothing is redacted outside that table.** The digest, `parsed-qbl.json`, and the CSVs keep the real values, because that is what makes remediation possible. Treat every generated artifact as sensitive until the credentials are rotated.
- **A zero count is not proof of cleanliness.** Detection is conservative to avoid false positives — stored-credential references like `{{ secrets.key }}` are correct practice and never flagged — so an unrecognized token format can slip through.

## Privacy

QBL exports describe real applications, and everything stays local: no input file is transmitted, and files that look like they carry credentials are refused. The included `.gitignore` excludes common QBL and table schema filenames so exports don't get committed by accident.

Interpreting formulas, pipeline configuration, page code, and integration endpoints is the point of the tool, so those are quoted freely when they answer a question. What the Skill avoids is bulk dumping — pasting an entire export or a whole collection into a conversation when a targeted answer will do.

## License

MIT. See [`LICENSE`](LICENSE).
