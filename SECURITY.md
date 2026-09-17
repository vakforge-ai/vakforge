# Security policy

## Supported versions

vakforge is pre-alpha. Only the latest release on PyPI receives fixes.

## Reporting a vulnerability

Email **vakforge.ai@gmail.com** with the subject line `SECURITY: <short summary>`.

Please include:

- what is affected (CLI command, module, the landing page, the release workflow)
- steps to reproduce, or a proof of concept
- the version (`vakforge --version`) and your OS

Do not open a public issue for security problems, and do not attach real customer audio, transcripts or personal data to a report. Synthetic examples are enough.

We aim to acknowledge reports within 3 working days and to agree a disclosure date with you once a fix is ready.

## Scope

In scope: code in this repository, the published `vakforge` package, and the release pipeline.

Especially relevant to this project: anything that lets personal data skip redaction in `prepare`, lets rows without consent reach a training set or export, or sends data off the machine without the user being told first.

Out of scope: vulnerabilities in upstream models or libraries that vakforge calls. Report those upstream; we will pin or patch around them.
