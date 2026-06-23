# Changelog

## v1.0.4 - 2026-06-23

- Fixed import_trips dialog not appearing on other users' machines.
  - Root cause: `show_input_dialog_macos()` silently swallowed all exceptions and returned None.
  - Fix: Print actual error messages; add file-editor fallback when tkinter is unavailable.
  - Full platform support: macOS / Windows / Linux with tkinter -> file-editor two-level fallback.
- Added tkinter installation hints for each platform on ImportError.
- Submit button text now includes shortcut hint "Ctrl+Enter".

## v1.0.3 - 2026-06-23

- Added batch trip import feature (`import_trips.py`).
  - Text input dialog for pasting tab-separated trip data.
  - Supports multiple date formats: `2026-01-04`, `2026/3/11`, `2026.3.11`.
  - Auto-skips header rows and empty lines; supports mixed multi-block paste.
  - Deduplicates by date range: skips existing trips, only creates new ones.
  - Auto-creates trip folders, trip details, invoice matching, and trip overview updates.
- Fixed: `setup.py init` no longer overwrites existing `config.py` (preserves user email/auth config).

## v1.0.2 - 2026-06-23

- Added online upgrade: `deploy.py --upgrade` pulls latest version from GitHub.
- Added remote version check: `deploy.py --check-update`.
- Triple fallback for version detection: git ls-remote -> GitHub API -> raw VERSION file.
- Config protection: upgrade never overwrites user `config.py`.
- Fixed: file selection dialog reappearing on double-click (osascript returncode vs stdout priority).
- Fixed: `'-128' in err_lower` TypeError (integer in string lookup).

## v1.0.1 - 2026-06-23

- Standardized the project for GitHub repository management.
- Added repository-level security policy.
- Strengthened `.gitignore` for local config, user data, archives, and generated files.
- Confirmed the public identity as `Linson` and the brand as `NoBusy 别虾忙｜AI 管理实战`.

## v1.0.0 - 2026-06-23

- Initial WorkBuddy Skill release for personal trip and invoice organization.
- Added invoice recognition, file organization, trip association, email attachment download, and local output workflow.
