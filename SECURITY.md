# Security policy

## Supported versions

Security fixes are applied to the latest version on the default branch.

## Reporting a vulnerability

Use this repository's private vulnerability-reporting feature (Security >
Report a vulnerability). Do not open a public issue or pull request for a
suspected vulnerability.

Include a clear description, reproduction steps using fabricated data, likely
impact, and any suggested mitigation. Never include client, taxpayer,
employee, payroll, banking, access-token or other sensitive data.

A valid report will be acknowledged within seven days. The fix and disclosure
timeline will be agreed with the reporter.

If GitHub private reporting is not visible, email is not published as a
fallback on purpose: enable private reporting in repository settings rather
than creating a public inbox.

## Upstream

FireFalcon is an Australian pack built on
[openfpa](https://github.com/JeffBrines/openfpa) by Guiderail. A vulnerability
in the shared `pyfpa` kernel belongs upstream. Report it to the openfpa
maintainers as well, and say here that you have done so, so the fix is not
duplicated or delayed.

## What this project does and does not do

FireFalcon runs locally against files you provide. It does not ship
credentials, does not authenticate to Xero or any other accounting system, and
does not post journals, lodge a BAS or a tax return, make payments, or send
client correspondence.

Generated connectors deliberately fail until a maintainer implements
host-authenticated access. That stub is a safety boundary. Do not paste
credentials into a connector, a config file, a fixture, an example, or a
prompt to reach a live system faster.

Treat every file the tool reads, and every model or agent output, as untrusted
input. Company financial data placed in a working directory stays on that
machine unless something else moves it. If a cloud AI service is pointed at
this workspace, that data passes to the service; check the firm's policy and
confidentiality obligations first, and de-identify by default.

Examples and fixtures in this repository are fabricated, except where they are
drawn from published public-company filings. Never commit real client data.
