# Repository instructions

PromptLibrary is a single-operator prompt and guided-workflow library. Keep the
browser and MCP interfaces aligned through the shared services. Do not add model
inference, shell execution, automatic remote merging or multi-user claims without
an explicit design change.

Start with README.md, docs/architecture.md and the relevant service and tests.
Use temporary data directories. Do not open or export a user's live library unless
they specifically authorised that operation. Never echo remote credentials.

Run `python scripts/manage.py setup --dev --browsers`, then
`python scripts/manage.py validate --browsers --security`. A missing dependency,
blocked browser, unavailable provider or absent platform is an unverified gate,
not a passing test. Report the exact checks run and any failures.

Use explicit types, small services and parameterised SQL. Preserve transaction,
foreign-key, snapshot and saved-run invariants. Test old-schema migration and
round-trip behaviour when changing stored data. Update the packaged user guide
for visible behaviour and preserve licences and notices.

Do not commit caches, databases, credentials, screenshots containing private data,
internal plans or fabricated validation evidence. Do not publish a release or
change remote repository settings unless the user explicitly requests that action.
