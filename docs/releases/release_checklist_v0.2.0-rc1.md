# v0.2.0-rc1 Release Checklist

## Automated Checks

- [x] `app/__init__.py` exists.
- [x] `start.bat` sets `PYTHONPATH=%CD%`.
- [x] `start.bat` uses `.venv\Scripts\python.exe -m streamlit run app\main.py`.
- [x] `start.bat` is ASCII and CRLF.
- [x] preflight rejects unsupported Python versions.
- [x] preflight detects wheelhouse Python tag mismatch.
- [x] empty SQLite database initializes.
- [x] v0.1 SQLite database migrates.
- [x] repeated `init_db()` is idempotent.
- [x] old `save_review_run(findings)` call remains compatible.
- [x] case creation, query and deletion are covered.
- [x] single review and batch review can associate `case_id`.
- [x] batch failure does not block successful files.
- [x] history query works.
- [x] manual review records can be saved after reopening history.
- [x] case-level ZIP exports.
- [x] case-level ZIP excludes source documents and SQLite databases.
- [x] field difference suggestions include “建议人工复核”.
- [x] SQLite does not store full document body text.
- [x] legacy single-document mode still passes.
- [x] legacy full-review mode still passes.
- [x] Word and ZIP export still pass.

## Manual Windows Checks

- [ ] Install Python 3.12 on a clean Windows machine.
- [ ] Unzip `LegalFactReview_v0.2.0-rc1_windows_portable.zip`.
- [ ] Double-click `start.bat`.
- [ ] Confirm `.venv` is created with Python 3.12.
- [ ] Confirm browser opens `http://localhost:<port>`.
- [ ] Confirm `logs/startup.log` is written.
- [ ] Confirm Case 02 single-document demo works.
- [ ] Confirm Case 01 full-review demo works.
- [ ] Confirm Case 08 batch review works inside a case workspace.
- [ ] Confirm case-level package opens on Windows and contains Chinese filenames.
- [ ] If using wheelhouse, confirm wheelhouse tag matches Python version, for example cp312 with Python 3.12.

## Release Files

- [x] Release notes created: `docs/releases/v0.2.0-rc1.md`.
- [x] Checklist created: `docs/releases/release_checklist_v0.2.0-rc1.md`.
- [x] README updated.
- [x] Quick start updated.
- [x] User manual updated.
- [ ] Release ZIP generated.
- [ ] SHA256 file generated.
