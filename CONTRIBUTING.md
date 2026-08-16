# Contributing

Thanks for taking a look. This is a small project, so the process is short.

## Getting set up

Python 3.11 or 3.12. **Not 3.13**: `jira==3.5.1` imports `imghdr`, removed from
the standard library in 3.13, so the import fails before anything runs.

```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

The tests need no JIRA credentials and make no network calls.

## Before you open a pull request

```bash
bash tools/local_gate.sh
```

Lint, unit tests, and a collection smoke check. CI runs the same script, so a
green gate locally means a green gate on GitHub. If it is red, fix the code —
never loosen a check to make it pass.

## The rule that matters most here

**Every number this tool prints will be quoted at somebody.**

Escape rate, reopen rate, resolution rate, average age: these end up in a
quality review, in a slide, in an argument about whether a release is ready. A
figure that looks precise does not get questioned, so a wrong one does more
damage than a missing one.

That makes the edge cases the important part, not an afterthought. Any change to
an aggregation needs tests for:

- **An empty input.** `pandas` returns NaN for the mean of an empty series, and
  NaN survives rounding, JSON encoding and string formatting. It reached a
  report as "Resolution Rate: nan%" before `_safe_mean` existed.
- **A single row.** Anything comparing first against last, or dividing by
  `n - 1`, breaks here.
- **The units.** A rate is a percentage (0–100) everywhere in this codebase.
  Two summaries once disagreed, and the dashboard multiplied one of them by 100
  a second time, displaying 65% as "6500.0%".

And the distinction that runs through all of it: **unknown is not zero.** An
empty result set returns `None`, not `0`. A resolution rate of 0% says nothing
was fixed; `None` says there was nothing to measure. Do not collapse them.

## What not to send

No real JIRA exports, ticket keys, project keys, board names, sprint names,
assignee names, or defect summaries. A defect export names employees and
describes unfixed weaknesses in a live product.

No credentials. The JIRA API token and `OPENAI_API_KEY` belong in `.env`, which
is gitignored.

## Reporting bugs

Open an issue with the shape of the data that misbehaved (invented rows are
fine, and preferred), what the tool reported, and what you expected.

A metric that looks wrong is worth reporting even if you are not certain. That
is the failure mode that matters here.
