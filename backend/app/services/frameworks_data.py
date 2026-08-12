"""MITRE ATT&CK sample set, STRIDE, SaaS packs, and Gartner panel templates.

Templates are shaped for a Senior Director Analyst interview deliverable covering
Offensive Security, Exposure Management, and Vulnerability Management.
"""

from __future__ import annotations

STRIDE = [
    {"id": "spoofing", "name": "Spoofing", "prompt": "Who/what can be impersonated?"},
    {"id": "tampering", "name": "Tampering", "prompt": "What data/process can be altered?"},
    {"id": "repudiation", "name": "Repudiation", "prompt": "Can actors deny actions?"},
    {"id": "info_disclosure", "name": "Information Disclosure", "prompt": "What sensitive data leaks?"},
    {"id": "dos", "name": "Denial of Service", "prompt": "How can availability be denied?"},
    {"id": "eop", "name": "Elevation of Privilege", "prompt": "How can privileges escalate?"},
]

MITRE_TECHNIQUES = [
    {"id": "T1078", "name": "Valid Accounts", "tactic": "Defense Evasion / Persistence / Privilege Escalation / Initial Access"},
    {"id": "T1190", "name": "Exploit Public-Facing Application", "tactic": "Initial Access"},
    {"id": "T1566", "name": "Phishing", "tactic": "Initial Access"},
    {"id": "T1133", "name": "External Remote Services", "tactic": "Persistence / Initial Access"},
    {"id": "T1059", "name": "Command and Scripting Interpreter", "tactic": "Execution"},
    {"id": "T1021", "name": "Remote Services", "tactic": "Lateral Movement"},
    {"id": "T1087", "name": "Account Discovery", "tactic": "Discovery"},
    {"id": "T1082", "name": "System Information Discovery", "tactic": "Discovery"},
    {"id": "T1048", "name": "Exfiltration Over Alternative Protocol", "tactic": "Exfiltration"},
    {"id": "T1486", "name": "Data Encrypted for Impact", "tactic": "Impact"},
    {"id": "T1530", "name": "Data from Cloud Storage", "tactic": "Collection"},
    {"id": "T1098", "name": "Account Manipulation", "tactic": "Persistence / Privilege Escalation"},
    {"id": "T1071", "name": "Application Layer Protocol", "tactic": "Command and Control"},
    {"id": "T1552", "name": "Unsecured Credentials", "tactic": "Credential Access"},
    {"id": "T1195", "name": "Supply Chain Compromise", "tactic": "Initial Access"},
    {"id": "T1595", "name": "Active Scanning", "tactic": "Reconnaissance"},
    {"id": "T1580", "name": "Cloud Infrastructure Discovery", "tactic": "Discovery"},
    {"id": "T1210", "name": "Exploitation of Remote Services", "tactic": "Lateral Movement"},
]

SAAS_CONTROL_PACKS = [
    {
        "id": "identity_access",
        "name": "Identity and Access",
        "controls": [
            "SSO / SAML / OIDC",
            "MFA enforcement",
            "SCIM provisioning",
            "Role-based access",
            "Session timeout / conditional access",
            "Break-glass account controls",
        ],
    },
    {
        "id": "data_protection",
        "name": "Data Protection",
        "controls": [
            "Encryption at rest",
            "Encryption in transit",
            "Customer key options (CMEK/BYOK)",
            "DLP / egress controls",
            "Data residency options",
            "Retention and deletion",
        ],
    },
    {
        "id": "logging_detection",
        "name": "Logging and Detection",
        "controls": [
            "Admin audit logs",
            "User activity logs",
            "SIEM export / API",
            "Alerting integrations",
            "Log retention period",
            "Immutable / protected logs",
        ],
    },
    {
        "id": "secure_sdlc",
        "name": "Secure SDLC and Assurance",
        "controls": [
            "SOC 2 / ISO reports",
            "Pen test cadence",
            "Vulnerability disclosure",
            "Dependency / SBOM support",
            "Change management",
            "Incident response commitments",
        ],
    },
    {
        "id": "exposure_vm_ops",
        "name": "Exposure and VM Operations",
        "controls": [
            "Continuous attack surface discovery",
            "Asset ownership / prioritization",
            "Risk-based vuln scoring",
            "SLA and exception workflow",
            "BAS / AEV integration",
            "Remediation orchestration",
        ],
    },
]

# Primary interview deliverable structure: Gartner Senior Director Analyst panel project
GARTNER_PANEL_SECTIONS = [
    {
        "title": "1. Research charter and client problem",
        "prompt": (
            "Frame the security leader problem this insight solves. Who is the buyer "
            "(CISO, Head of SecOps, VM lead)? What decision are they stuck on?"
        ),
        "seed": (
            "# 1. Research charter and client problem\n\n"
            "## Client persona\n_Who is asking, and what outcome do they need?_\n\n"
            "## Decision barrier\n_What stops them from acting today?_\n\n"
            "## Insight promise\n_What must-have insight will this note deliver?_\n"
        ),
    },
    {
        "title": "2. Market definition and scope",
        "prompt": (
            "Define Exposure Management, Vulnerability Management, and Offensive Security "
            "for this research note. Clarify boundaries and overlaps."
        ),
        "seed": (
            "# 2. Market definition and scope\n\n"
            "## Exposure Management\n\n## Vulnerability Management\n\n"
            "## Offensive Security\n\n## What is in / out of scope\n"
        ),
    },
    {
        "title": "3. Offensive Security landscape",
        "prompt": (
            "Cover penetration testing, breach and attack simulation (BAS), adversarial "
            "exposure validation (AEV), red team and purple team. Compare outcomes, buyers, limits."
        ),
        "seed": (
            "# 3. Offensive Security landscape\n\n"
            "## Penetration testing\n\n## Breach and attack simulation (BAS)\n\n"
            "## Adversarial exposure validation (AEV)\n\n"
            "## Red team / purple team\n\n## When each approach wins\n"
        ),
    },
    {
        "title": "4. Exposure Management landscape",
        "prompt": (
            "Analyze continuous attack surface management, prioritization, ownership, "
            "and how exposure programs connect to remediation and offensive validation."
        ),
        "seed": (
            "# 4. Exposure Management landscape\n\n"
            "## Discovery and inventory\n\n## Prioritization models\n\n"
            "## Ownership and workflow\n\n## Link to remediation and validation\n"
        ),
    },
    {
        "title": "5. Vulnerability Management landscape",
        "prompt": (
            "Assess VM maturity: coverage, risk-based scoring, SLAs, exceptions, metrics, "
            "and residual risk communication to executives."
        ),
        "seed": (
            "# 5. Vulnerability Management landscape\n\n"
            "## Coverage and tooling\n\n## Risk-based triage\n\n"
            "## SLA and exception governance\n\n## Executive metrics that matter\n"
        ),
    },
    {
        "title": "6. Cross-domain interplay and market trends",
        "prompt": (
            "Synthesize how OffSec, EM, and VM reinforce each other. Predict market shifts "
            "clients and vendors should act on in the next 12 to 24 months."
        ),
        "seed": (
            "# 6. Cross-domain interplay and market trends\n\n"
            "## How the three domains connect\n\n## Buyer pressure points\n\n"
            "## 12 to 24 month predictions\n\n## Implications for vendors\n"
        ),
    },
    {
        "title": "7. Threat framing (MITRE ATT&CK and STRIDE)",
        "prompt": (
            "Map priority techniques and STRIDE categories to the research problem. "
            "Show how validation and prioritization should follow attacker-relevant paths."
        ),
        "seed": (
            "# 7. Threat framing (MITRE ATT&CK and STRIDE)\n\n"
            "## Priority ATT&CK techniques\n\n## STRIDE view of the system/process\n\n"
            "## Attack path narrative\n"
        ),
    },
    {
        "title": "8. Vendor and control patterns",
        "prompt": (
            "Compare SaaS and platform control patterns that support EM/VM/OffSec outcomes. "
            "Call out common gaps and residual risk."
        ),
        "seed": (
            "# 8. Vendor and control patterns\n\n"
            "## Capability patterns that matter\n\n## Common control gaps\n\n"
            "## Residual risk after tooling\n"
        ),
    },
    {
        "title": "9. Actionable recommendations for security leaders",
        "prompt": (
            "Write pragmatic, provocative guidance security leaders can apply now. "
            "Include sequencing, metrics, and what to stop doing."
        ),
        "seed": (
            "# 9. Actionable recommendations for security leaders\n\n"
            "## Do now (0 to 90 days)\n\n## Build next (3 to 12 months)\n\n"
            "## Stop or deprioritize\n\n## Success metrics\n"
        ),
    },
    {
        "title": "10. Research positions and agenda",
        "prompt": (
            "State independent insights positions. Note where you would push Gartner research "
            "agenda, peer debate, or future notes."
        ),
        "seed": (
            "# 10. Research positions and agenda\n\n"
            "## Position statements\n\n## Open debates\n\n## Follow-on research topics\n"
        ),
    },
    {
        "title": "11. Executive presentation outline",
        "prompt": (
            "Build a high-value presentation outline for client briefings or conference delivery. "
            "Keep it executive-ready with crisp talking points."
        ),
        "seed": (
            "# 11. Executive presentation outline\n\n"
            "## Opening hook\n\n## Three insights\n\n## Proof points\n\n"
            "## Ask / next steps for the client\n"
        ),
    },
    {
        "title": "12. Peer review notes and references",
        "prompt": (
            "Capture peer-review feedback, evidence quality notes, and full references. "
            "Keep citations ready for APA/MLA/Chicago export."
        ),
        "seed": (
            "# 12. Peer review notes and references\n\n"
            "## Peer review checklist\n\n## Evidence gaps to close\n\n## References\n"
        ),
    },
]

PROJECT_TEMPLATES = {
    "gartner_panel": {
        "title": "Gartner Senior Director panel project",
        "description": (
            "Interview deliverable template for Security Operations: Offensive Security, "
            "Exposure Management, and Vulnerability Management. Structured for must-have "
            "insights, market prediction, and client-actionable advice."
        ),
        "sections": [s["title"] for s in GARTNER_PANEL_SECTIONS],
        "section_defs": GARTNER_PANEL_SECTIONS,
    },
    "blank": {
        "title": "Blank research",
        "description": "Empty structured research project.",
        "sections": ["Overview", "Analysis", "Findings", "Recommendations", "References"],
    },
    "exposure_review": {
        "title": "Exposure Management Review",
        "description": "External exposure, attack surface, and remediation prioritization.",
        "sections": [
            "Scope and assets",
            "Exposure inventory",
            "Threat framing (MITRE / STRIDE)",
            "Risk prioritization",
            "Remediation plan",
            "References",
        ],
    },
    "vuln_management": {
        "title": "Vulnerability Management Assessment",
        "description": "Scanning, triage, SLAs, and residual risk for vuln program maturity.",
        "sections": [
            "Program scope",
            "Discovery and coverage",
            "Triage and SLA performance",
            "Exception handling",
            "Metrics and gaps",
            "Recommendations",
            "References",
        ],
    },
    "offensive_summary": {
        "title": "Offensive Assessment Summary",
        "description": "Ethical offensive findings summary covering PT, BAS, AEV, red/purple team.",
        "sections": [
            "Executive summary",
            "Rules of engagement notes",
            "Penetration testing outcomes",
            "BAS and AEV validation",
            "Red / purple team narrative",
            "Detection opportunities",
            "Remediation roadmap",
            "References",
        ],
    },
    "saas_control_review": {
        "title": "SaaS Control Review",
        "description": "Vendor SaaS security control effectiveness against research requirements.",
        "sections": [
            "Business context",
            "Identity and access controls",
            "Data protection controls",
            "Logging and detection",
            "Exposure and VM operations controls",
            "Assurance and compliance",
            "Gap matrix and residual risk",
            "Recommendation",
            "References",
        ],
    },
}
