"""Offline trusted reference snippets for SecOps research."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings

DEFAULT_REFS = {
    "mitre_attack": {
        "title": "MITRE ATT&CK",
        "url": "https://attack.mitre.org/",
        "notes": "Enterprise technique catalog for adversary behavior mapping.",
        "sample_techniques": [
            {"id": "T1078", "name": "Valid Accounts"},
            {"id": "T1190", "name": "Exploit Public-Facing Application"},
            {"id": "T1566", "name": "Phishing"},
            {"id": "T1059", "name": "Command and Scripting Interpreter"},
            {"id": "T1021", "name": "Remote Services"},
            {"id": "T1486", "name": "Data Encrypted for Impact"},
            {"id": "T1048", "name": "Exfiltration Over Alternative Protocol"},
            {"id": "T1087", "name": "Account Discovery"},
        ],
    },
    "stride": {
        "title": "STRIDE threat categories",
        "url": "https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats",
        "categories": [
            {"id": "S", "name": "Spoofing", "property": "Authentication"},
            {"id": "T", "name": "Tampering", "property": "Integrity"},
            {"id": "R", "name": "Repudiation", "property": "Non-repudiation"},
            {"id": "I", "name": "Information Disclosure", "property": "Confidentiality"},
            {"id": "D", "name": "Denial of Service", "property": "Availability"},
            {"id": "E", "name": "Elevation of Privilege", "property": "Authorization"},
        ],
    },
    "nist_csf": {
        "title": "NIST Cybersecurity Framework",
        "url": "https://www.nist.gov/cyberframework",
        "functions": ["Govern", "Identify", "Protect", "Detect", "Respond", "Recover"],
    },
    "owasp": {
        "title": "OWASP Top 10",
        "url": "https://owasp.org/www-project-top-ten/",
        "notes": "Web app risk baseline for SaaS control reviews.",
    },
}


def refs_path() -> Path:
    path = get_settings().data_dir / "refs" / "trusted_refs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_REFS, indent=2), encoding="utf-8")
    return path


def load_refs() -> dict:
    try:
        return json.loads(refs_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_REFS


def trusted_refs_snippet(max_chars: int = 1800) -> str:
    refs = load_refs()
    lines = []
    mitre = refs.get("mitre_attack", {})
    lines.append(f"MITRE ATT&CK: {mitre.get('url', '')}")
    for t in (mitre.get("sample_techniques") or [])[:8]:
        lines.append(f"- {t.get('id')} {t.get('name')}")
    stride = refs.get("stride", {})
    lines.append(f"STRIDE: {stride.get('url', '')}")
    for c in stride.get("categories") or []:
        lines.append(f"- {c.get('id')}/{c.get('name')} ({c.get('property')})")
    text = "\n".join(lines)
    return text[:max_chars]
