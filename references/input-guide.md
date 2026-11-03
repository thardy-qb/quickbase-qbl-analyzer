# Input Guide

The Skill classifies uploaded files by content, so explicit filenames are recommended but not required.

## Required input

1. A QBL export in YAML format.

A QBL export normally contains top-level `Solution` and `Resources` keys:

```yaml
Solution:
  Version: 0.14
Resources:
  $App_Main:
    Type: QB::Application
    Properties:
      Name: Project Tracker
    Tables:
      $Table_Projects:
        Type: QB::Table
        Properties:
          Name: Projects
          AliasHint: _DBID_PROJECTS
```

A platform export also ends with a second YAML document — `---` followed by a
`Parameters:` block holding the values the deploying app substitutes for the
defaults in `ParameterDefinitions`. Upload the file exactly as exported; the
parser reads both documents and lets the `Parameters` overrides win when it
resolves `!Var` references, so the inventory describes the app the export is
going to rather than the one it came from. A file with the block stripped off
parses too, and then only the defaults apply.

QBL files may also be uploaded with a `.txt` extension when a chat interface rejects `.yaml` uploads.

## Optional input

2. A Quickbase table schema JSON file.

The table schema payload is an array of table objects. Only `id`, `alias`, and `name` are required for enrichment; other keys are used when present.

```json
[
  {
    "id": "bqx1aaaaa",
    "alias": "_DBID_PROJECTS",
    "name": "Projects",
    "updated": "2026-01-05T00:00:00Z",
    "keyFieldId": 3,
    "sizeLimit": "500 MB",
    "spaceUsed": "1 MB",
    "spaceRemaining": "499 MB"
  }
]
```

An API response object that wraps the array is also accepted.

### What the table schema adds

Each table in a QBL export declares an `AliasHint`. That alias is the join key to the table schema payload, which supplies:

- Runtime table IDs on tables, fields, reports, and permission rows
- Table names and key field IDs from the live application
- Table storage metadata: `sizeLimit`, `spaceUsed`, `spaceRemaining`

Without the table schema file, those columns are blank. The full inventory — tables, fields, relationships, roles, permissions, forms, rules, reports, dashboards, pages, pipelines, connected tables, custom emails, and document templates — still parses from the QBL export alone, including the field and role IDs the export declares.

## Recommended filenames

```text
solution-qbl.yaml
table-schema.json
```

## After parsing

One `summary` run produces everything. Reuse its output directory for the rest of the conversation rather than re-parsing:

```bash
python3 scripts/qbl_analyzer.py collections <output-dir>
python3 scripts/qbl_analyzer.py query <output-dir> fields --where "Formula!=" --columns "Table Name,Field Label,Formula"
```

See `analysis-guide.md` for question-to-query patterns.

## Intake behavior

- When no QBL file is present, the Skill reports exactly what is needed.
- When several QBL candidates are present, the Skill lists them and asks which to analyze.
- When one QBL candidate is clear, the Skill states the assignment and runs without an extra confirmation.
- The Skill does not ask for the optional table schema file unless its absence limits what the user asked for.

## Files that must not be used

Do not upload or process:

- `.env`
- Files containing Quickbase user tokens
- Cloud provider credentials
- Passwords
- Private keys

If a credential file is uploaded accidentally, do not inspect or reproduce its values. Tell the user to remove the file and rotate any exposed credentials.
