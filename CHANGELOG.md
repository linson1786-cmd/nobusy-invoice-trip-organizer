# Changelog

## v1.0.18 - 2026-06-24

- Added flight price comparison screenshot recognition as a non-reimbursement file category.
- Extracts flight date, amount, route, and passenger name from comparison screenshots.
- Archives flight comparison screenshots under the flight/train category without requiring invoice keywords.
- Synchronized release metadata across project README, root changelog, source changelog, WorkBuddy Skill, and Codex Skill.

## v1.0.11 - 2026-06-24

- Added lodging city extraction for accommodation invoices.
- Accommodation filenames now support a single city location field, e.g. `2026-01-12_住宿_264.00_中山_0112_WB_043.pdf`.
- City extraction prioritizes seller name, hotel-related lines, address fields, then full-text city keywords.
- On first run after upgrade, existing accommodation files in `03 已完成/` and trip attachment folders are scanned once and renamed with the new lodging city rule when a city can be identified.
- Added a one-time migration marker to avoid repeated renaming.
- Trip invoice lists are regenerated after trip attachment filenames are migrated.
- Fixed `version_manager.py` update list so shared upgrades also update `import_trips.py`, `deploy.py`, `release_check.py`, and `config_template.py`.
- Updated release checks to validate lodging city extraction and single-city filename parsing.

## v1.0.10 - 2026-06-24

- Fixed WorkBuddy "新增行程" trigger behavior: invalid stdin trigger text no longer blocks the GUI input window.
- Kept valid stdin trip data support for Codex and demo-safe automation.
- Updated WorkBuddy SKILL.md guidance to make popup input the normal local workflow.
- Fixed `deploy.py` script list so `import_trips.py` is deployed to the WorkBuddy runtime directory.

## v1.0.9 - 2026-06-24

- Fixed source drift in `import_trips.py` by adding the documented `--file/-f` mode to the source directory.
- Kept stdin pipe input explicit and verified in the release gate.
- Fixed Codex Skill demo command to run from the initialized workspace script directory.
- Added release checks to detect source/install drift for WorkBuddy deployed scripts.

## v1.0.8 - 2026-06-24

- Added `release_check.py` as a repeatable release gate for version, tracked files, required resources, Python compilation, local installs, and Codex validation.
- Added non-GUI initialization with `setup.py init --base-dir` for automated validation and demo-safe testing.
- Added missing `docs/SOP-发票文件命名标准.md` and fixed SOP copy path during initialization.
- Removed stale root-level `scripts/*.py` duplicates; `scripts/invoice-trip-organizer/` is now the single source directory.
- Fixed initialization copy list to include `import_trips.py` and `release_check.py`.
- Removed local `NoBusy-Demo` fallback paths from standard scripts; missing config now fails with clear initialization guidance.
- Fixed generated trip links to use the actual `1 月` directory format instead of `01 月`.
- Fixed invoice status counts to exclude generated `日志.md` and `台账.md` files.

## v1.0.7 - 2026-06-24

- Fixed version alignment across project source, WorkBuddy installation, and GitHub repository metadata.
- Fixed `config_template.py` path variables and removed hardcoded demo fallback paths.
- Added `import_trips.py --file/-f` input mode for file-based trip import.
- Documented fixed paths for WorkBuddy install directory, local project directory, and GitHub repository.

## v1.0.6 - 2026-06-23

- Fixed: import_trips.py GUI window not showing in sandbox environment.
- Added stdin pipe input support: `echo "data" | python3 import_trips.py`.
- Added AI conversation guide in SKILL.md for collecting trip data without GUI.
- Updated all version references to 1.0.6.

## v1.0.5 - 2026-06-23

- Renamed trip import trigger from "导入行程" to "新增行程" to avoid conflict with file import ("导入").
- Added "导入文件" as a synonym trigger for file import (`upload_files.py`).
- Updated all version references across the project to 1.0.5 (SKILL.md, setup.py defaults, deploy.py, version_manager.py docstrings).
- Security: removed `config.py` from repository (contains user paths, should not be tracked).

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
