---
name: invoice-trip-organizer
description: "Organize personal invoice and trip reimbursement files with local scripts. Use when Codex needs to inspect, validate, install, run, or modify the NoBusy invoice-trip-organizer workflow; classify invoices; rename files; generate trip/reimbursement summaries; manage demo-safe data; or update the related GitHub project. Do not use for real reimbursement submission, real email authorization, or approval-system actions without explicit user confirmation. Current version: 1.0.8."
---

# invoice-trip-organizer

Use this Skill for the NoBusy personal invoice and trip organization workflow.

## Source of truth

- Project directory: `/Users/linson/Documents/Personage/AI Tools Learning/WorkBuddy Skills/invoice-trip-organizer/`
- Runtime scripts: `scripts/invoice-trip-organizer/`
- WorkBuddy install: `/Users/linson/.workbuddy/skills/invoice-trip-organizer/`
- GitHub repo: `linson1786-cmd/nobusy-invoice-trip-organizer`

Treat `scripts/invoice-trip-organizer/` as the only source script directory. Root-level `scripts/*.py` files are stale and must not be reintroduced.

## Safety boundaries

- Do not submit real reimbursement applications, operate OA approval systems, or authorize real email accounts unless the user explicitly confirms that exact action.
- Do not read, commit, or publish `config.py`, `.env`, real invoices, reimbursement spreadsheets, archives, or files under `项目管理/项目记忆/`.
- Use demo-safe temporary directories for tests.

## Standard commands

Run from the project directory unless noted:

```bash
python3 scripts/invoice-trip-organizer/release_check.py
python3 scripts/invoice-trip-organizer/deploy.py --status
python3 scripts/invoice-trip-organizer/deploy.py --force
```

Demo-safe initialization:

```bash
python3 scripts/invoice-trip-organizer/setup.py init --base-dir /private/tmp/invoice-trip-demo
```

Demo-safe trip import:

```bash
printf '开始日期\t结束日期\t行程\n2026-01-04\t2026-01-06\t广州-上海-广州\n' | python3 import_trips.py
```

## Release gate

Before publishing a new version:

1. Update `scripts/invoice-trip-organizer/VERSION`.
2. Update `CHANGELOG.md` and `scripts/invoice-trip-organizer/CHANGELOG.md`.
3. Run `python3 -m py_compile scripts/invoice-trip-organizer/*.py`.
4. Run `python3 scripts/invoice-trip-organizer/release_check.py`.
5. Run a demo-safe init and trip import flow.
6. Deploy to WorkBuddy only after local checks pass.
7. Validate the installed Codex Skill with `quick_validate.py`.

Git commit messages must be English. Do not push until the user confirms.
