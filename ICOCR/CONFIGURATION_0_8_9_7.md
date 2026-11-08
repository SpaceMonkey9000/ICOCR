# ICOCR 0.8.9.7 configuration

- `%LOCALAPPDATA%/ICSuite/ICOCR/settings.json`: application UI settings, preprocessing, tuning and logic diagrams.
- Shared `DATA/rules/`: single authoritative collection of modular rule JSON files, including ranking.
- Shared `DATA/models/`: body detection and OCR models.
- Shared `DATA/db/`: component database.
- For portable/source execution, shared DATA defaults to a sibling `DATA` directory; packaged execution defaults to `%LOCALAPPDATA%/ICSuite/DATA`.
- `ICLENS_DATA` or `%LOCALAPPDATA%/ICSuite/data_location.json` (legacy IC_Tools read fallback) overrides the DATA location.
- First launch seeds missing bundled rule modules and settings without overwriting existing files. There is no legacy config migration.
- Restart required to apply rule changes.
- For a clean 0.8.9.7 test, use empty ICSuite ICOCR and DATA directories. Existing 0.8.9.6 files are not automatically converted.
