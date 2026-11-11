#!/usr/bin/env python3
"""Fixture hygiene: reserved example domains and placeholder hosts, and no network imports.

Standard library only, no test runner required:

    python3 tests/test_privacy.py

Most of what the Skill contains is library code: the QBL parser under
`scripts/qblparser/`, and PyYAML and XlsxWriter under `scripts/vendor/`.
Library code is the easiest place for a stray address or host to slip through
unread, so every file is scanned, not only the scripts.

Anything that is only an example belongs on one of the allowlists below. Prefer the
reserved-for-documentation domains over inventing a realistic-looking address.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent

SCANNED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".toml"}
SKIPPED_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", "build", "dist"}

# Domains reserved for documentation and examples, the synthetic ones the
# credential-scanner fixtures need, and the contact address in XlsxWriter's
# licence.
ALLOWED_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net",
    "corp.com", "intranet.corp", "vendor.com", "warehouse.example.com",
    "cpan.org",
}

# Quickbase hostnames that are public product surfaces, and the placeholder
# realms used in documentation.
ALLOWED_QUICKBASE_HOSTS = {
    "quickbase.com", "www.quickbase.com", "api.quickbase.com",
    "help.quickbase.com", "developer.quickbase.com", "community.quickbase.com",
    "example.quickbase.com", "myrealm.quickbase.com",
}

EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[A-Za-z]{2,})")
QUICKBASE_HOST = re.compile(r"\b([\w-]+(?:\.[\w-]+)*\.quickbase\.com)\b", re.I)
REALM_DBID_URL = re.compile(r"https?://[\w.-]+/db/b[a-z0-9]{8}", re.I)
NETWORK_IMPORT = re.compile(
    r"\s*(?:import|from)\s+(?:urllib\.request|urllib\.error|urllib(?=\s|$)|http|socket"
    r"|ssl|requests|httpx|aiohttp|ftplib|smtplib)\b")


def scanned_files():
    """Every text file in the Skill, bundled dependencies included."""
    for path in sorted(SKILL_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIPPED_DIR_NAMES for part in path.parts):
            continue
        yield path


def _report(hits):
    """Render offending values and the files holding them."""
    return "\n".join(
        f"  {value}\n" + "\n".join(f"      {path}" for path in sorted(paths))
        for value, paths in sorted(hits.items())
    )


class FixtureHygieneTests(unittest.TestCase):
    def _collect(self, finder):
        hits = {}
        for path in scanned_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for value in finder(text):
                hits.setdefault(value, set()).add(str(path.relative_to(SKILL_ROOT)))
        return hits

    def test_no_third_party_email_addresses(self):
        def finder(text):
            return {
                match.group(0)
                for match in EMAIL.finditer(text)
                if match.group(1).lower() not in ALLOWED_EMAIL_DOMAINS
            }

        hits = self._collect(finder)
        self.assertFalse(
            hits,
            "Email addresses outside the documentation domains:\n"
            + _report(hits)
            + "\n\nUse an example.com address, or add the domain to "
            "ALLOWED_EMAIL_DOMAINS if it names nobody.",
        )

    def test_quickbase_hostnames_are_public_or_placeholders(self):
        def finder(text):
            return {
                match.group(1)
                for match in QUICKBASE_HOST.finditer(text)
                if match.group(1).lower() not in ALLOWED_QUICKBASE_HOSTS
            }

        hits = self._collect(finder)
        self.assertFalse(
            hits,
            "Quickbase hostnames that are not public or placeholder hosts:\n"
            + _report(hits)
            + "\n\nUse "
            "example.quickbase.com, or add the host to ALLOWED_QUICKBASE_HOSTS "
            "if it is a public product surface.",
        )

    def test_urls_use_placeholder_dbids(self):
        hits = self._collect(lambda text: set(REALM_DBID_URL.findall(text)))
        self.assertFalse(
            hits,
            "URLs carrying what look like Quickbase dbids:\n" + _report(hits),
        )

    def test_no_module_can_open_a_network_connection(self):
        """The file-only promise, enforced against what is on disk.

        This Skill parses what the user uploads and never calls Quickbase, so
        no shipped module may import a networking library. `urllib.parse` only
        splits strings and is allowed.
        """
        hits = {}
        for path in sorted((SKILL_ROOT / "scripts").rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if NETWORK_IMPORT.match(line):
                    hits.setdefault(str(path.relative_to(SKILL_ROOT)), set()).add(f"{number}: {line.strip()}")
        self.assertFalse(hits, "Modules importing a networking library:\n" + _report(hits))


if __name__ == "__main__":
    unittest.main()
