# Test guidance

Keep tests isolated from live PromptLibrary data by using temporary data directories.

- Browser journeys use an explicitly selected, installed Playwright browser: `python -m pytest -q tests/e2e --browser <installed-browser>`.
- Do not treat a missing browser binary or system library as a passing test.
- Add regression coverage at the lowest layer that proves the behavior, then add HTTP/MCP or browser coverage when the contract crosses interfaces.
- Preserve migration, snapshot, export/import, backup, workflow ordering, and security negative-path coverage.
