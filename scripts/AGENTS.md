# Script guidance

These scripts are the canonical setup, startup, validation, packaging, and release helpers.

- Keep platform-specific setup explicit; do not hide missing Python, virtualenv, browser, or system-library dependencies.
- Use the checkout-local `.venv` and temporary data directories for validation.
- Preserve the exact exit status of underlying commands so failed gates cannot appear successful.
- Do not add background or detached process behavior to validation scripts without a documented lifecycle and cleanup path.
- Keep browser selection explicit when invoking Playwright; the developer or CI job chooses the installed supported engine.
