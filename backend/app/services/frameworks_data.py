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

def _defs(*rows: tuple[str, str, str]) -> list[dict]:
    """Build section_defs from (title, prompt, seed_body) tuples."""
    out = []
    for title, prompt, body in rows:
        seed = f"# {title}\n\n{body.strip()}\n"
        out.append({"title": title, "prompt": prompt.strip(), "seed": seed})
    return out


PROJECT_TEMPLATES = {
    "blank": {
        "title": "Blank research",
        "description": "General structured research. Pick this when the topic does not match a specialist pack.",
        "sections": ["Overview", "Analysis", "Findings", "Recommendations", "References"],
        "section_defs": _defs(
            (
                "Overview",
                "Frame the leadership decision, audience, and outcome this note must unlock.",
                "Decision blocked today:\n\nAudience:\n\nIn scope / out of scope:\n",
            ),
            (
                "Analysis",
                "Explain the program or market pattern with evidence and uncertainty marks.",
                "Current state:\n\nPattern or failure mode:\n\nEvidence (link sources):\n",
            ),
            (
                "Findings",
                "List specific findings a security leader can act on. Mark confidence.",
                "| Finding | Why it matters | Confidence | Source |\n| --- | --- | --- | --- |\n|  |  | medium |  |\n",
            ),
            (
                "Recommendations",
                "Sequence actions: do now, build next, stop. Include residual risk.",
                "**Do now**\n- \n\n**Build next**\n- \n\n**Stop**\n- \n\nResidual risk after these moves:\n",
            ),
            (
                "References",
                "Primary sources only. No invented stats.",
                "- \n",
            ),
        ),
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
        "section_defs": _defs(
            (
                "Scope and assets",
                "Define internet-facing scope, asset classes, and ownership model under review.",
                "Business context:\n\nAsset classes in scope:\n\nKnown ownership model:\n\nOut of scope:\n",
            ),
            (
                "Exposure inventory",
                "Summarize discovery coverage, shadow assets, and ownership gaps without dumping raw scanner noise.",
                "Discovery sources:\n\nCoverage holes:\n\nShadow / unowned exposures:\n\nInventory theater risks:\n",
            ),
            (
                "Threat framing (MITRE / STRIDE)",
                "Map likely ATT&CK techniques and STRIDE categories for the highest-value exposures.",
                "ATT&CK techniques:\n- \n\nSTRIDE notes:\n- \n\nMost plausible attacker path:\n",
            ),
            (
                "Risk prioritization",
                "Rank by exploitability and business blast radius, not raw severity alone.",
                "Prioritization model:\n\nTop risks:\n1. \n2. \n3. \n\nWhat current scoring gets wrong:\n",
            ),
            (
                "Remediation plan",
                "Close the loop: own, fix, validate, re-check. Sequence now/next/stop.",
                "**Do now**\n- \n\n**Build next**\n- \n\n**Stop**\n- \n\nValidation method after fix:\n\nResidual internet-facing risk:\n",
            ),
            (
                "References",
                "Primary sources for discovery methods, standards, and ATT&CK.",
                "- MITRE ATT&CK: https://attack.mitre.org/\n- \n",
            ),
        ),
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
        "section_defs": _defs(
            (
                "Program scope",
                "Define environments, asset classes, and what 'managed' means for this VM program.",
                "Environments:\n\nAsset classes:\n\nTools in play:\n\nSuccess definition for leadership:\n",
            ),
            (
                "Discovery and coverage",
                "Where does scanning miss assets, cloud accounts, or network segments?",
                "Coverage strengths:\n\nCoverage holes:\n\nAgent / network / cloud gaps:\n",
            ),
            (
                "Triage and SLA performance",
                "Assess triage quality and whether SLAs match change capacity.",
                "Triage model today:\n\nSLA targets vs reality:\n\nExploitability signals used (KEV/EPSS/other):\n",
            ),
            (
                "Exception handling",
                "Quantify exception debt and forever-accepted risk.",
                "Exception volume / age patterns:\n\nCompensating controls quality:\n\nResidual risk from exceptions:\n",
            ),
            (
                "Metrics and gaps",
                "Replace CVE-count theater with metrics that drive action.",
                "Metrics leaders see today:\n\nMetrics that should replace them:\n\nProgram gaps:\n",
            ),
            (
                "Recommendations",
                "Sequence VM program changes: now / next / stop.",
                "**Do now**\n- \n\n**Build next**\n- \n\n**Stop**\n- \n\nResidual risk after changes:\n",
            ),
            (
                "References",
                "KEV, standards, and primary program sources.",
                "- CISA KEV: https://www.cisa.gov/known-exploited-vulnerabilities-catalog\n- \n",
            ),
        ),
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
        "section_defs": _defs(
            (
                "Executive summary",
                "Leadership view: residual risk, method mix, and the decision this note unlocks.",
                "Decision for leadership:\n\nResidual risk in one paragraph:\n\nRecommended validation mix:\n",
            ),
            (
                "Rules of engagement notes",
                "High-level scope and constraints only. No client secrets or exploit detail.",
                "Scope boundaries:\n\nConstraints:\n\nWhat was intentionally out of scope:\n",
            ),
            (
                "Penetration testing outcomes",
                "Translate depth findings into program patterns, not ticket dumps.",
                "What depth testing revealed:\n\nPattern across assets:\n\nLimit of point-in-time testing:\n",
            ),
            (
                "BAS and AEV validation",
                "Where continuous validation and exploitability validation change residual risk.",
                "BAS value in this context:\n\nAEV / exploitability validation value:\n\nWhen pen testing is still required:\n",
            ),
            (
                "Red / purple team narrative",
                "Objective-driven paths and detection quality at technique level.",
                "Likely objectives:\n\nATT&CK techniques:\n- \n\nDetection / response friction:\n",
            ),
            (
                "Detection opportunities",
                "Map findings to detection engineering opportunities.",
                "High-value detections:\n- \n\nTelemetry gaps:\n- \n",
            ),
            (
                "Remediation roadmap",
                "Sequence fixes and validation cadence. Now / next / stop.",
                "**Do now**\n- \n\n**Build next**\n- \n\n**Stop**\n- \n\nSuggested validation cadence:\n",
            ),
            (
                "References",
                "ATT&CK and primary method sources.",
                "- MITRE ATT&CK: https://attack.mitre.org/\n- \n",
            ),
        ),
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
        "section_defs": _defs(
            (
                "Business context",
                "Data class, trust boundary, and why this vendor matters.",
                "Business use case:\n\nData class / sensitivity:\n\nTrust boundary notes:\n",
            ),
            (
                "Identity and access controls",
                "SSO, MFA, SCIM, roles, break-glass. Mark met/partial/gap.",
                "| Control | Status | Evidence | Residual risk |\n| --- | --- | --- | --- |\n| SSO / MFA |  |  |  |\n| SCIM / lifecycle |  |  |  |\n",
            ),
            (
                "Data protection controls",
                "Encryption, key management, DLP, residency, retention.",
                "| Control | Status | Evidence | Residual risk |\n| --- | --- | --- | --- |\n| Encryption at rest/in transit |  |  |  |\n| CMEK/BYOK |  |  |  |\n",
            ),
            (
                "Logging and detection",
                "Admin/user logs, SIEM export, retention, immutability.",
                "Logging strengths:\n\nGaps:\n\nSIEM / IR usefulness:\n",
            ),
            (
                "Exposure and VM operations controls",
                "Vendor attack surface handling and vuln response commitments.",
                "External exposure posture:\n\nVuln disclosure / fix cadence:\n\nCustomer visibility:\n",
            ),
            (
                "Assurance and compliance",
                "SOC2/ISO/pen tests: what they cover and what they do not prove.",
                "Assurance artifacts reviewed:\n\nWhat they do not prove:\n",
            ),
            (
                "Gap matrix and residual risk",
                "Roll up material gaps and residual risk after compensating controls.",
                "Material gaps:\n1. \n\nCompensating controls:\n\nResidual risk summary:\n",
            ),
            (
                "Recommendation",
                "Accept, accept with conditions, or reject path. Include exit considerations.",
                "Recommendation:\n\nConditions:\n\nExit / contingency notes:\n",
            ),
            (
                "References",
                "Vendor docs and assurance sources.",
                "- \n",
            ),
        ),
    },
    "tester_to_analyst": {
        "title": "Tester to Analyst note",
        "description": (
            "Bridge hands-on testing experience into research insight writing: decision framing, "
            "market or program patterns, residual risk, and leadership recommendations."
        ),
        "sections": [
            "Decision the note must unlock",
            "What testing experience taught me",
            "Program or market pattern",
            "Threat framing (MITRE / STRIDE)",
            "What buyers get wrong",
            "Options and tradeoffs",
            "Recommendations (now / next / stop)",
            "Evidence still needed",
            "References",
        ],
        "section_defs": _defs(
            (
                "Decision the note must unlock",
                "State the leadership decision, audience, and cost of waiting a quarter.",
                "Audience:\n\nDecision blocked today:\n\nCost of inaction (90 days):\n\nWhat success looks like:\n",
            ),
            (
                "What testing experience taught me",
                "Extract a repeatable pattern from hands-on work. No war stories, no client IDs, no exploit steps.",
                "Pattern observed across engagements:\n\nWhat scanners or process missed:\n\nWhat good validation changed:\n",
            ),
            (
                "Program or market pattern",
                "Generalize from testing into a program or market insight buyers can use.",
                "Program pattern:\n\nWhere spend is wasted:\n\nWhere outcomes improve:\n",
            ),
            (
                "Threat framing (MITRE / STRIDE)",
                "Map the pattern to ATT&CK techniques and STRIDE categories at a responsible level.",
                "ATT&CK techniques:\n- \n\nSTRIDE categories in play:\n- \n\nWhy this path matters to a buyer:\n",
            ),
            (
                "What buyers get wrong",
                "Name common buyer mistakes: tooling theater, metric theater, cadence mistakes.",
                "Common mistakes:\n1. \n2. \n3. \n\nWhat good looks like instead:\n",
            ),
            (
                "Options and tradeoffs",
                "Compare realistic options including doing nothing and stopping a practice.",
                "| Option | Upside | Downside | Residual risk |\n| --- | --- | --- | --- |\n|  |  |  |  |\n",
            ),
            (
                "Recommendations (now / next / stop)",
                "Sequence recommendations for a security leader. Be direct.",
                "**Do now**\n- \n\n**Build next**\n- \n\n**Stop**\n- \n\nResidual risk after these moves:\n",
            ),
            (
                "Evidence still needed",
                "List claims that still need primary sources before publish.",
                "- [ ] Claim:\n  Source needed:\n  Confidence today: low/medium\n",
            ),
            (
                "References",
                "Primary sources only.",
                "- MITRE ATT&CK: https://attack.mitre.org/\n- \n",
            ),
        ),
    },
}
