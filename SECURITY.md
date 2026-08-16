# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability**. That opens a private thread with the
maintainer.

Include what you found, how to reproduce it, and what an attacker gets. Expect a
first reply within a week. This is a personal project maintained in spare time.

## Supported versions

The latest commit on the default branch. There are no maintained release
branches.

## Scope

In scope: credential handling, JQL or SQL injection through configuration, and
anything that sends defect data somewhere other than where you configured.

Out of scope: the accuracy limits described in the README. Classification is
heuristic, so a miscategorised defect is a quality issue rather than a
vulnerability.

## Handling the data

A defect export is more sensitive than it looks:

- It names employees, and pairs them with what they broke and how long it took
  to fix.
- It describes unfixed weaknesses in a live product, in detail, with
  reproduction steps.
- The local SQLite store (`DB_PATH`, default `defect_intelligence.db`) holds all
  of it in plain text.

So: keep the database out of the repository (`.gitignore` covers the default
name), keep generated reports out of issues and screenshots, and do not paste
defect summaries into a public bug report about this tool. Invented rows make a
better reproduction case anyway.

## Credentials and third parties

- **The JIRA token should be read-only.** Nothing here writes to JIRA, so a
  token with write scope grants more than the tool needs.
- **`OPENAI_API_KEY` is optional, and it changes where your data goes.** With it
  set, defect summaries and descriptions are sent to OpenAI for classification.
  That is a third party receiving your organisation's defect text. Without it
  the tool falls back to the local ML path and still works. Decide deliberately.
- `.env` is gitignored. Keep it that way.

## If you leak a credential

Rotating is the fix. Deleting the key from a file, or rewriting git history,
does not revoke anything: assume any token that was ever committed is
compromised and issue a new one.
