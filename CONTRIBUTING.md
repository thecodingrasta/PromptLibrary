# Contributing

Open an issue for a reproducible bug or a proposed change. For a security issue,
use the private reporting route in [SECURITY.md](SECURITY.md), not a public issue.
Keep changes focused and include a test that fails before the fix.

## Local setup

Use Python 3.12 or newer. From the repository root:

```sh
python scripts/manage.py setup --dev --browsers
python scripts/manage.py validate --browsers --security
```

On Windows, `py -3` can replace `python`; on Linux or macOS, use `python3` where
needed. Scripts use the checkout's `.venv`; there is no activation requirement.
The test suite uses temporary databases. Never point tests at your working library.
Browser installation and dependency auditing require network access.

## Code and tests

Keep business rules in services, not templates or transport handlers. HTTP and
MCP mutations must use the same validation and transaction boundaries. Bind SQL
values as parameters; interpolated identifiers must come from closed internal
allowlists. Do not add shell execution, model inference or credentials to prompts.

Use explicit type annotations. `Record` is the intentional SQLite/JSON/template
boundary; do not spread untyped values into unrelated application logic. Comments
should explain an invariant or trade-off rather than restate the code.

Inside the virtual environment:

```sh
python -m ruff check .
python -m ruff format .
python -m mypy src/promptlibrary
python -m pytest -q --ignore=tests/e2e --ignore=tests/integration
python -m pytest -q tests/integration/test_mcp_stdio.py
python -m pytest -q tests/e2e --browser chromium
```

Add migration tests for schema changes, round-trip tests for portable entities,
and browser regression tests for navigation or editing changes. Do not replace
assertions with skips to make a build green. Keep failed checks visible.

## Pull requests

Describe the problem, the change, compatibility implications and the checks you
actually ran. Include screenshots for visual changes, but no personal library
content or credentials. Update the user guide when behaviour changes. State any
use of generated code that materially affected the change and review it yourself.

The licence is GPL-3.0-or-later. Submit only work you have permission to contribute;
preserve third-party attribution. Participation is covered by the
[code of conduct](CODE_OF_CONDUCT.md).
