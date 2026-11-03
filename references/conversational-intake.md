# Conversational Intake Guide

Intake should feel like a short guided form inside the conversation. It should help users supply the right file without asking questions Claude can answer from the uploads.

## Routing decision

Use this order:

1. Inspect uploaded files and classify them by content.
2. Identify the QBL export to analyze.
3. Note whether an optional table schema file was supplied.
4. Capture audience or focus preferences only when the user volunteers them.
5. Run the analysis.

## No QBL uploaded

```text
Please upload the QBL export for the solution. A `.yaml`, `.yml`, or `.txt` file is accepted.

Optional: a Quickbase table schema JSON file, which adds runtime table IDs and table metadata.
```

## Several QBL candidates

```text
Which QBL should I analyze?

1. <filename one>
2. <filename two>
3. <filename three>
```

## Complete input

Do not ask for confirmation when there is one clear QBL candidate. State the assignment and run:

```text
I'll generate the solution overview from `<filename>`.
```

When a table schema file was also uploaded:

```text
I'll generate the solution overview from `<filename>`, enriched with `<table-schema-filename>`.
```

## Optional output preferences

Do not block execution to collect these. Use them when the user volunteers them or explicitly asks for a tailored result.

### Detail level

```text
Which summary should I emphasize?

1. Executive summary
2. Full technical inventory
3. Both
```

Default: Both.

### Focus areas

```text
Which areas should I emphasize in the written summary?

1. Tables, fields, and relationships
2. Permissions and roles
3. Forms and reports
4. Pipelines and integrations
5. Quality signals and technical debt
6. All areas
```

Default: All areas.

## File assignment rules

- Use content signatures before relying on extensions.
- Treat filenames as supporting evidence, not proof.
- A file with top-level `Solution` and `Resources` YAML keys is a QBL export.
- A JSON array of objects carrying `id`, `alias`, and `name` is a table schema payload.
- If the user's wording contradicts a filename, follow the user's explicit wording.

## Error and safety responses

### Credential-like file detected

```text
One of the uploaded files appears to contain credentials or environment configuration. I will not process or display it. Remove that file before continuing, and rotate any credential that may have been exposed.
```

### Invalid file

```text
I could not classify `<filename>` as a QBL export or a table schema file. Please verify that the correct file was uploaded.
```

### Parsing failure

Identify the failed file and provide only the sanitized parser message. Do not paste raw customer configuration into the response.

## Completion response

After a successful run:

1. If the user asked a question, answer it first, grounded in the digest and any queries you ran.
2. If the user asked for a report or inventory, summarize the most important findings.
3. Link `solution-overview.xlsx` and the ZIP bundle. Mention them once; do not lead with them.
4. Mention material enrichment limits if no table schema file was supplied.
5. Quote formulas, endpoints, and pipeline configuration when they support the answer. Do not paste whole collections or the entire export.
