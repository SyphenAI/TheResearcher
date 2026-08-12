"""MITRE ATT&CK sample set, STRIDE, SaaS packs, and topic research templates."""

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

PROJECT_TEMPLATES = {
    "blank": {
        "title": "Blank research",
        "description": "General structured research. Pick this when the topic does not match a specialist pack.",
        "sections": ["Overview", "Analysis", "Findings", "Recommendations", "References"],
    },
    "exposure_review": {
        "title": "Exposure Management Review",
        "description": "External exposure, attack surface, ownership, and remediation prioritization.",
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
        "description": "Scanning coverage, triage, SLAs, exceptions, and residual risk for VM programs.",
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
        "title": "Offensive Security Summary",
        "description": "Pen testing, BAS, AEV, and red/purple team style findings and remediation.",
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
        "description": "Vendor SaaS control effectiveness, gaps, and residual risk against requirements.",
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
