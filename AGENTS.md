# Repository Instructions

## Markdown Style

* Use `*` for unordered list items in Markdown files.
* Apply this consistently in `readme.md`, `changelog.md`, and add-on documentation.
* Do not mix `-` and `*` list markers in the same document unless preserving quoted or external text.
* Keep changelog entries concise and user-facing.
* Add new changelog entries under the unreleased or next-version heading before release preparation.

## Branching and Commits

* Keep feature or alpha work on a dev or feature branch until it has been tested with NVDA and LibreOffice Writer.
* Do not commit directly to `master` unless the change is release-ready.
* Keep commits focused: separate feature changes, documentation updates, and release preparation when practical.

## Add-on Contents

* Do not commit `__pycache__/`, `*.pyc`, backup files, local probes, or generated `.nvda-addon` packages.
* Before copying files from an alpha workspace, separate production modules from probes, backups, and generated artifacts.

## Validation

* Run `ruff check` and `ruff format --check` on changed Python files before committing.
* For table navigation changes, verify behavior manually in NVDA with LibreOffice Writer tables.

## Writer Table Navigation

* Avoid adding acceptance probe shortcuts such as `NVDA+control+f*` to production builds.
* Be careful when changing `control+alt` table movement gestures because they may overlap with NVDA native table navigation.
