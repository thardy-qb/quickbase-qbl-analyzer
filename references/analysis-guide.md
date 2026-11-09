# Analysis Guide

How to answer questions about a parsed solution without reading the whole inventory.

## The three-tier rule

1. **`solution-digest.md`** — read this first. Nothing in it is sampled: every table, relationship, role, pipeline, outbound endpoint, and flagged field is listed. Expect a few KB for a small application. It grows with the solution, so on a large one, read the architecture and integration sections and query for the long lists rather than loading the whole file.
2. **`query`** — use for everything the digest caps or omits. Only matching rows are printed, so cost scales with the answer, not the solution.
3. **`parsed-qbl.json`** — do not read this directly except on a genuinely small solution. It runs 7-12x the size of the source QBL; on a large realm that is tens of megabytes.

Every truncated list in the digest names the query that returns the rest. Follow it rather than guessing.

## Commands

Discover what is available and what columns exist:

```bash
python3 scripts/qbl_analyzer.py collections <output-dir>
```

Query one collection:

```bash
python3 scripts/qbl_analyzer.py query <output-dir> <collection> \
  --where "<column><op><value>" --columns "A,B,C" --limit 50
```

| Operator | Meaning |
|---|---|
| `col=value` | equals, case-insensitive |
| `col=` | cell is blank or `N/A` |
| `col!=value` | not equal |
| `col!=` | cell is non-blank |
| `col=~text` | contains, case-insensitive |
| `col!~text` | does not contain |
| `col>N` `col<N` `col>=N` `col<=N` | numeric comparison |

Repeat `--where` to AND conditions. Add `--distinct` to collapse duplicate projected rows, `--count` for counts only, `--limit -1` for everything, and `--format json` or `--format csv` when you need to post-process.

Column and collection names are matched case-insensitively but never abbreviated, and an unknown name returns the closest matches and the valid list. **Do not guess column names**: `references/collection-columns.md` lists the exact columns of every collection. The ones most often guessed wrong:

| Collection | Guess | Actual column |
|---|---|---|
| `relationships` | `Parent Table`, `Child Table` | `Parent Table Name`, `Child Table Name` |
| `relationships` | `Reference Field` | `Reference Field Name` |
| `pipeline_steps` | `Selector`, `Action` | `Channel Selector`, `Step SubType` |
| `pipeline_steps` | `Table` | `Table Name` (the step's table, its target's for an update) |
| `fields` | `Label`, `Type` | `Field Label`, `Field Type` |
| `rules` | `Name`, `Conditions` | `Rule Name`, `Rule Summary` |

## Question patterns

### "What does this application do?"

Read `solution-digest.md`. The architecture and integration sections are written for exactly this.

### "What breaks if I change or delete this field?"

The matrix collections are the dependency graph. Check each surface the field could appear on:

```bash
python3 scripts/qbl_analyzer.py query <dir> fields --where "Field Logical ID=$Field_X" \
  --columns "Field Label,Used in Reports,Used in Charts,Used in Forms,Used in Form Rules,Used in Custom Data Rules,Referenced in Formulas,Used in Relationships,Used in Dashboards,Used in Permissions,Used in Pipelines,Used in Custom Emails,Used in Connected Tables,Total Usage Count"
```

Then enumerate the actual references:

```bash
python3 scripts/qbl_analyzer.py query <dir> report_field_matrix   --where "Field Logical ID=$Field_X" --columns "Report Name,Table Name,Used As"
python3 scripts/qbl_analyzer.py query <dir> field_form_matrix     --where "Field Logical ID=$Field_X" --columns "Form Name,Table Name,Form Section Name,Form Row Logical ID"
python3 scripts/qbl_analyzer.py query <dir> field_pipeline_matrix --where "Field Logical ID=$Field_X" --columns "Pipeline Name,Step Name,Reference Context"
python3 scripts/qbl_analyzer.py query <dir> field_role_matrix     --where "Field Logical ID=$Field_X" --columns "Role Name,Usage Type,Usage Context"
```

`report_field_matrix` carries one row per way a report names the field, and
`Used As` says which way: a column, a chart axis, a calendar's start date, a
sort key, or `Filters.Criteria` — a field the report filters on by numeric id
and mentions nowhere else. Deleting a field a report only filters on breaks the
report silently, so read that column rather than counting rows.

`field_role_matrix`'s `Usage Type` includes `Custom Access Rule`: a role whose
record-level access is decided by a query over that field. A field can also be
named by a criteria pointing at a field the table does not have — `Usage
Context` says so rather than dropping the row, because a permission decided by
a missing field is worth seeing.

A search widget on a home page names fields too, and those are in
`page_widgets` rather than a field matrix:

```bash
python3 scripts/qbl_analyzer.py query <dir> page_widgets --where "Widget Type=~Search" \
  --columns "Page Name,Widget Type,Points At,Parent Widget Logical ID"
```

### "What are our integration points?"

```bash
python3 scripts/qbl_analyzer.py query <dir> pipeline_steps --where "HTTP URL!=" \
  --columns "Pipeline Name,HTTP Method,HTTP URL" --distinct
```

Add `connected_tables` and `external_resources` for non-pipeline integrations.

### "What does this pipeline actually do?" / "What's risky about it?"

The digest already lists, for every pipeline, its schedule and timezone, each step's selector and table, its filter, the fields a trigger watches, and what each step sets. Read that first. For the full values:

```bash
python3 scripts/qbl_analyzer.py query <dir> pipelines --columns "Pipeline Name,Trigger,Schedule,Schedule Timezone,Description,Owner"
python3 scripts/qbl_analyzer.py query <dir> pipeline_steps --where "Pipeline Logical ID=$Pipeline_X" \
  --columns "Step ID,Step Name,Step Type,Step Depth,Channel Selector,Table Name,Target Step ID,Filters,Trigger Fields,Input Mappings,HTTP Method,HTTP URL"
```

Rows are in step order. `Step Type` distinguishes a plain step from an `if statement` or `loop`, and `Step Depth` says how deeply a step is nested, so you can reconstruct control flow. `Filters` is the step's condition as written (`status equals "Completed"`); `Input Mappings` is what it writes, `Field = value` pairs separated by `; `. An update inside a loop names no table of its own: `Target Step ID` names the search whose record it updates, and `Table Name` is that search's table (`Table Source` says `Target step`).

Questions worth asking of each pipeline: does a scheduled one check for work it already did (a filter that would stop a duplicate)? Does a record trigger fire on any change (`Trigger On All Fields=Yes`) or only on named fields? Does a filter test a choice value that a rename would silently break?

### "Which pipelines read or write this table?"

```bash
python3 scripts/qbl_analyzer.py query <dir> pipeline_table_matrix --where "Table Logical ID=$Table_X" \
  --columns "Pipeline Name,Step Name,Reference Context" --distinct
```

`Reference Context` tells you *how* the table was referenced — a native step data source, a step target (`Reference Type=Target Step`, an update of a record an earlier search found), an HTTP body field, or a URL parameter. Whether a step reads or writes is its `Channel Selector` in `pipeline_steps`: `create`, `update`, `upsert` and `delete` write; `search` and the `on_*` triggers read.

### "How are the tables related?"

The digest lists each relationship once. The `relationships` collection has **two rows per relationship**, because the export writes each one on both of its tables; `Relationship Side` says which half a row is, and `Counterpart Relationship Logical ID` names the other half. Count or list on one side:

```bash
python3 scripts/qbl_analyzer.py query <dir> relationships --where "Relationship Side=Child" \
  --columns "Parent Table Name,Child Table Name,Reference Field Name,Total Reference Fields"
```

The manifest's `relationship_count` is the number of relationships; `entity_counts.relationships` is the number of rows.

### "What do the form rules do?"

```bash
python3 scripts/qbl_analyzer.py query <dir> rules --columns "Table Name,Form Name,Rule Name,Enabled,Rule Summary,Condition Fields,Action Fields"
```

`Rule Summary` reads `When Status IsEqualTo "New" -> Hide Resolution Notes`. Condition groups are read through, so a field a rule tests is in `Condition Fields` and marked `Used in Form Rules` in `fields`.

### "Who can see or edit what?"

```bash
python3 scripts/qbl_analyzer.py query <dir> roles --columns "Role Name,Edit App,Manage Users,Disable Access"
python3 scripts/qbl_analyzer.py query <dir> permissions --where "Role Name=Viewer"
python3 scripts/qbl_analyzer.py query <dir> field_role_matrix --where "Role Name=Viewer" --columns "Table Name,Field Label,Permission Type"
```

### "Show me the formulas"

```bash
python3 scripts/qbl_analyzer.py query <dir> fields --where "Formula!=" \
  --columns "Table Name,Field Label,Field Type,Formula" --limit -1
```

Formula-query fields are worth separating, since they carry different performance characteristics:

```bash
python3 scripts/qbl_analyzer.py query <dir> fields --where "Is Formula Query=Yes" \
  --columns "Table Name,Field Label,Formula"
```

### "Where is the technical debt?"

```bash
python3 scripts/qbl_analyzer.py query <dir> fields --where "Potentially Unused=Yes" \
  --columns "Table Name,Field Label,Field Type" --limit -1
python3 scripts/qbl_analyzer.py query <dir> report_duplicates --columns "Duplicate Group,Report Name,Table Name"
```

### "What would stop this from deploying?"

Validation findings are in the digest and in `solution-summary.md`, grouped by
code with the fix for each. Read those rather than querying — the findings are
not a parsed collection.

Five layers run over the document: `SCH` (schema shape), `REF` (does a `!Ref`
resolve, and to the right kind), `VAL` (value domains), `STR` (container rules,
such as an application with no home page), and `FML` (does a formula name a
field that exists — no other layer can see inside a formula body).

Severity is the thing to report accurately:

- **error** — the platform rejects this. It blocks a deployment.
- **warning** — pre-existing debt, most often a `REF000` `!BadRef` that
  Quickbase itself wrote into the export because a reference could not be
  resolved at export time. It deploys fine.

`REF000` counts are a good technical-debt signal in their own right: each one is
a reference the platform could not resolve when the solution was exported.

Give the fix the finding carries rather than improvising one. For several codes
the obvious response is wrong — `SCH001`, an unrecognised type, is skipped by
Quickbase with a warning rather than rejected, so the object is simply missing;
the fix is correcting the type name, not adding properties.

### The `Potentially Unused` flag is bounded by what the export records

The parser's usage flags cover reports, report filters, forms, form rules, custom data rules, formulas, relationships, dashboards, charts, field properties, permissions, pipelines, custom emails, and connected tables. The last three arrive as their own columns - `Used in Pipelines`, `Used in Custom Emails`, `Used in Connected Tables` - and they feed `Total Usage Count` and `Potentially Unused`, so a field read by a pipeline every night and used nowhere else is not flagged. The digest also cross-checks the flag against the reference collections and reports how many flagged fields some collection still references. A nonzero count means those fields need a manual look before anyone treats them as unused.

What the flag still cannot see is anything the export does not record: a code page, a URL formula, an external integration.

To check one field yourself:

```bash
python3 scripts/qbl_analyzer.py query <dir> field_pipeline_matrix     --where "Field Logical ID=$Field_X"
python3 scripts/qbl_analyzer.py query <dir> custom_email_field_matrix --where "Field Logical ID=$Field_X"
python3 scripts/qbl_analyzer.py query <dir> connected_table_fields    --where "Field Logical ID=$Field_X"
```

Even a field with no reference anywhere is a review candidate, not a confirmed dead field — a code page, URL formula, or external integration can reference it in ways a QBL export does not record. Say so when reporting.

## Reporting guidance

- Ground every claim in a query you actually ran. Name the collection and filter.
- Quote formulas, URLs, and pipeline configuration when they answer the question. That is what this data is for.
- Say when a result is capped. `--limit` truncation is reported in the query footer; pass it through rather than presenting a partial list as complete.
- Distinguish what the QBL states from what you inferred. Reference counts are stated; "this pipeline probably syncs orders nightly" is inference.
- Matrix collections carry one row per reference, so the same pair can repeat legitimately. Use `--distinct` when you want unique pairs and do not report raw row counts as if they were entity counts.
