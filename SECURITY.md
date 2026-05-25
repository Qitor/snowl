# Security Policy

## Supported Versions

Snowl is currently in alpha. Security fixes are prioritized for the latest release line on `main`.

## Reporting A Vulnerability

Please do not open a public GitHub issue for an unpatched vulnerability.

Preferred reporting path:

1. Use GitHub Security Advisories or private vulnerability reporting if it is enabled for the repository.
2. If private reporting is unavailable, contact the maintainers directly through GitHub.
3. Include a clear reproduction, affected files or APIs, impact assessment, and any suggested mitigation.

## What To Include

- affected version or commit
- reproduction steps
- expected vs. actual behavior
- impact and exploitability notes
- whether credentials, secrets, or user data are involved

## Response Expectations

Maintainers aim to:

- acknowledge reports promptly
- reproduce and triage the issue
- coordinate a fix and disclosure plan
- document user-facing mitigations when a patch is not immediately available

## Security Hygiene

Contributors should:

- keep secrets out of the repository
- use environment variables for API keys and credentials
- run `pip-audit` before release-oriented changes when possible
- avoid adding debug-only or unsafe endpoints to the stable surface
