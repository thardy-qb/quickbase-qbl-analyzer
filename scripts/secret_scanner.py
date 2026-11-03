"""Flag credential-like strings that a QBL export carries in plain text.

Hardcoded secrets in pipeline configuration, code pages, or application
variables are a finding an analyst wants surfaced, so nothing here is redacted
from the inventory -- the full value stays in `parsed-qbl.json` and the CSVs
where it can be acted on. What this module adds is a prominent, locatable
warning, because the digest is the artifact people paste into tickets and chat
and a buried credential is easy to propagate by accident.

Findings carry a masked preview rather than the value itself, so the warning
section is safe to share while still naming exactly where the real value lives.

Template references such as `{{ secret }}` or `{ account.token }` are the
correct way to reference a stored credential and are never flagged.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

# Columns worth scanning, by collection. Each entry names the columns that can
# hold free text plus the columns that identify the row in a report.
SCAN_TARGETS: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    (
        "pipeline_steps",
        ("HTTP URL", "HTTP Body", "Channel Selector"),
        ("Pipeline Name", "Step Name", "Step ID"),
    ),
    ("application_variables", ("Value",), ("App Logical ID", "Name")),
    ("parameter_definitions", ("Value",), ("Parameter Logical ID",)),
    ("pages", ("Page Content", "Content", "Body"), ("App Logical ID", "Page Name")),
    ("custom_emails", ("Body", "Subject"), ("App Logical ID", "Custom Email Name", "Name")),
    ("fields", ("Formula", "Summary Formula"), ("Table Name", "Field Label")),
    ("external_resources", ("URL", "Base URL", "Endpoint"), ("Name",)),
)

# Vendor token formats. These are specific enough that a match is near-certain.
TOKEN_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("GitHub token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b"),
    ("GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ("GitLab token", r"\bglpat-[A-Za-z0-9_\-]{16,}\b"),
    ("Stripe key", r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b"),
    ("Slack token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
    ("Google OAuth token", r"\bya29\.[0-9A-Za-z_\-]{20,}\b"),
    ("SendGrid key", r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
    ("Shopify token", r"\bshp(?:at|ss|ca|pa)_[a-fA-F0-9]{32}\b"),
    ("npm token", r"\bnpm_[A-Za-z0-9]{36}\b"),
    ("DigitalOcean token", r"\bdop_v1_[a-f0-9]{64}\b"),
    ("JSON Web Token", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("PEM private key", r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ("Basic auth in URL", r"://[^/\s:@]+:[^/\s:@]+@"),
    ("Bearer token", r"\bBearer\s+[A-Za-z0-9._\-]{16,}"),
)

# Credential-ish key names. A match only counts when the value alongside the key
# looks like a real secret rather than a template reference or a placeholder.
CREDENTIAL_KEY_WORDS = (
    "api_key", "apikey", "api-key",
    "access_token", "accesstoken", "access-token",
    "refresh_token", "auth_token", "authtoken",
    "client_secret", "clientsecret",
    "private_key", "privatekey",
    "password", "passwd", "pwd",
    "secret", "token", "credential", "signature", "usertoken",
    "sas", "sig", "authorization",
)

# `key=value` in a query string, or `"key": "value"` in a JSON body.
_QUERY_PAIR = re.compile(r"([A-Za-z0-9_\-\.]+)\s*=\s*([^&\s\"'>]+)")
_JSON_PAIR = re.compile(r"\"([A-Za-z0-9_\-\.]+)\"\s*:\s*\"([^\"]+)\"")

# A stored-credential reference, which is the correct pattern and never a finding.
_TEMPLATE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{[A-Za-z0-9_\.\s\-]+\}|^\$[A-Za-z]")

# Obvious non-secrets that would otherwise trip the key-name heuristic.
_PLACEHOLDER_VALUES = {
    "", "null", "none", "nil", "true", "false", "changeme", "change_me",
    "your_api_key", "your-api-key", "xxx", "xxxx", "todo", "tbd", "example",
    "placeholder", "redacted", "secret", "password", "test", "dummy", "n/a",
}

MIN_SECRET_LENGTH = 8


def _is_template_reference(value: str) -> bool:
    return bool(_TEMPLATE.search(value.strip()))


def mask(value: str) -> str:
    """Render a locatable hint without reproducing the value."""
    text = value.strip()
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:4]}{'*' * min(12, len(text) - 6)}{text[-2:]}"


def _looks_like_secret(value: str) -> bool:
    text = value.strip().strip("'\"")
    if len(text) < MIN_SECRET_LENGTH:
        return False
    if text.casefold() in _PLACEHOLDER_VALUES:
        return False
    if _is_template_reference(text):
        return False
    # Require some character-class variety so plain words and simple
    # identifiers do not register as credentials.
    has_digit = any(c.isdigit() for c in text)
    has_alpha = any(c.isalpha() for c in text)
    return has_digit and has_alpha


def scan_text(text: str) -> List[Dict[str, str]]:
    """Return findings for one free-text value."""
    if not text:
        return []
    findings: List[Dict[str, str]] = []
    reported: set = set()

    # Vendor formats first: they identify the secret precisely, so a later
    # key-name match on the same value adds nothing.
    for label, pattern in TOKEN_PATTERNS:
        for match in re.finditer(pattern, text):
            matched = match.group(0)
            if _is_template_reference(matched) or matched in reported:
                continue
            reported.add(matched)
            findings.append({"kind": label, "masked": mask(matched)})

    for pair_pattern in (_QUERY_PAIR, _JSON_PAIR):
        for match in pair_pattern.finditer(text):
            name, value = match.group(1), match.group(2)
            normalized = name.casefold().replace("-", "_")
            if not any(word in normalized for word in CREDENTIAL_KEY_WORDS):
                continue
            if not _looks_like_secret(value):
                continue
            stripped = value.strip().strip("'\"")
            # Skip when a token pattern already reported this value, including
            # the case where it matched a substring of the assigned value.
            if any(stripped in seen or seen in stripped for seen in reported):
                continue
            reported.add(stripped)
            findings.append({"kind": f"value assigned to `{name}`", "masked": mask(value)})

    return findings


def _row_label(row: Mapping[str, Any], id_columns: Sequence[str]) -> str:
    parts = [
        str(row.get(column, "")).strip()
        for column in id_columns
        if str(row.get(column, "")).strip()
    ]
    return " / ".join(parts) if parts else "(unidentified row)"


def scan_parsed_data(parsed_data: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Scan every configured collection for credential-like strings."""
    findings: List[Dict[str, str]] = []

    for collection, columns, id_columns in SCAN_TARGETS:
        rows = parsed_data.get(collection)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in columns:
                value = row.get(column)
                if not isinstance(value, str) or not value.strip():
                    continue
                for hit in scan_text(value):
                    findings.append(
                        {
                            "collection": collection,
                            "column": column,
                            "location": _row_label(row, id_columns),
                            "kind": hit["kind"],
                            "masked": hit["masked"],
                        }
                    )

    return findings


def render_section(findings: Sequence[Mapping[str, str]]) -> List[str]:
    """Render the digest warning section. Returns [] when there is nothing to report."""
    if not findings:
        return []

    lines = [
        "## Possible hardcoded credentials",
        "",
        f"**{len(findings)} credential-like string(s) found in this export.**",
        "",
        "Treat each as compromised: rotate it, then replace the literal with a stored",
        "credential reference so the export stops carrying it.",
        "",
        "> The table below masks values so it does not restate the secret. **The full",
        "> values are not redacted anywhere else** -- they remain in this report, in",
        "> `parsed-qbl.json`, and in the CSVs, which is what makes remediation possible.",
        "> Until these are rotated, treat every generated artifact as sensitive: do not",
        "> paste them into a ticket, chat, or anywhere you would not put the credentials",
        "> themselves.",
        "",
        "| Where | Field | Kind | Value |",
        "|---|---|---|---|",
    ]
    for finding in findings:
        lines.append(
            f"| {finding['location']} | `{finding['collection']}.{finding['column']}` "
            f"| {finding['kind']} | `{finding['masked']}` |"
        )
    lines.append("")
    return lines
