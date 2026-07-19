# Security Policy

## Supported Versions

django-micboard follows [Calendar Versioning](https://calver.org/) (`YY.MM.PATCH`).
Security fixes are applied to the **latest released version** only.

| Version | Supported |
|---------|-----------|
| Latest  | ✅ Security fixes applied |
| Older   | ❌ Upgrade to latest |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's [private security advisory](https://github.com/justprosound/django-micboard/security/advisories/new)
to report vulnerabilities confidentially. This lets us coordinate a fix and
disclosure timeline before any details become public.

**What to include:**

- A description of the vulnerability and the affected component
- Steps to reproduce or a proof-of-concept (if safe to share)
- The impact you believe this has (data exposure, privilege escalation, etc.)
- Any suggested mitigations you are aware of

**Response timeline:**

- **Acknowledgement**: within 5 business days (Note: This project is maintained by a single developer; please allow for occasional delays)
- **Status update**: within 14 business days
- **Coordinated disclosure**: after a patch is available, following responsible
  disclosure best practices

## Scope

This project is a **reusable Django application** — it does not operate its own
servers or handle user data directly. Vulnerabilities in the library that could
affect downstream deployers are in scope. Issues in optional dependencies or
integrations should be reported to the upstream project, though we appreciate
a heads-up so we can track mitigations.

## Security Design Principles

- All GitHub Actions workflow steps are pinned to immutable commit SHAs
- Release artifacts carry [SLSA level 2 provenance](https://slsa.dev/) via
  `actions/attest`
- Dependency updates are automated via Renovate (Python) and Dependabot
  (GitHub Actions)
- Supply-chain health is monitored via the
  [OpenSSF Scorecard](https://securityscorecards.dev/#/github.com/justprosound/django-micboard)
- Vulnerability scanning runs on every pull request (`uv audit`, Bandit,
  CodeQL) and weekly (OSV-Scanner full repository scan)

## Acknowledgements

We follow the [Coordinated Vulnerability Disclosure](https://www.cisa.gov/coordinated-vulnerability-disclosure-process)
process. Researchers who responsibly disclose valid vulnerabilities will be
credited in the release notes unless they prefer to remain anonymous.
