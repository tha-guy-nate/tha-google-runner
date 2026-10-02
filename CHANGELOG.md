# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-10-02
### Changed
- Dependencies are now pinned to exact versions (`==`) instead of `>=` floors, and updated to the latest releases: `google-auth==2.59.1`, `google-auth-oauthlib==1.5.0`, `platformdirs==4.12.2`, `tha-req-runner==0.3.0`, `tha-req-runner[httpx2]==0.3.0`. Dev dependencies are pinned the same way (`pytest==9.1.1`, `ruff==0.16.10`, `mypy==2.4.0`, `deptry==0.25.1`, `pip-audit==2.10.1`, `pytest-cov==7.1.0`).
- `__version__` is now read from the installed package metadata (`importlib.metadata`) instead of a hardcoded string, so `pyproject.toml` is the only place the version is bumped.

## [0.3.0] - 2026-09-20
### Changed
- **Breaking**: `backend: Literal["requests", "httpx"]` is now `Literal["requests", "httpx2"]` across `ThaSheets`, `ThaDocs`, `ThaDrive`, `ThaSlides`, and `ThaGmail`, following `tha-req-runner` 0.3.0's swap from `httpx` to `httpx2` (Pydantic's maintained successor). The `httpx` extra is now `httpx2`; floor bumped to `tha-req-runner>=0.3.0`. No repo in the `tha-*` family ships this backend in production, so this lands as a straight rename.

## [0.2.3] - 2026-08-21
### Fixed
- Re-locked transitive `cryptography` (pulled in via the `google-auth` runtime dependency) from `49.0.0` to `50.0.0`, resolving a known CVE (PYSEC-2026-3552) flagged by `pip-audit`.
- Re-locked transitive `pip` (pulled in via `deptry` -> `pip-api`) from `26.1.2` to `26.2.1`, resolving a separate known CVE (PYSEC-2026-3721).

## [0.2.2] - 2026-07-25
### Fixed
- Bumped `tha-req-runner` dependency floor from `>=0.2.5` to `>=0.2.7` — versions 0.2.5 and earlier are yanked on PyPI.
- Corrected `__init__.py.__version__` drift (was stuck at 0.2.0 while `pyproject.toml` had already moved to 0.2.1).
- Re-locked transitive `pyasn1` (via `google-auth` -> `pyasn1-modules`) from `0.6.3` to `0.6.4`, resolving three known CVEs (PYSEC-2026-3455/3456/3457) flagged by `pip-audit`.

## [0.2.1] - 2026-07-04
### Fixed
- `pyproject.toml` `keywords` only covered `google`/`sheets`/`docs` even though the library also wraps Drive, Slides, and Gmail — added `drive`, `slides`, `gmail`. Also removed the now-stale `gspread` GitHub topic (dropped entirely in the 0.2.0 REST migration).

## [0.2.0] - 2026-07-04
### Changed
- Replaced `google-api-python-client` (and the unused `gspread` dependency) with direct REST calls over `tha-req-runner` across all five classes (`ThaSheets`, `ThaDocs`, `ThaDrive`, `ThaSlides`, `ThaGmail`). Drops `google-api-python-client`, `gspread`, `httplib2`, `google-auth-httplib2`, `uritemplate`, `google-api-core`, `googleapis-common-protos`, `protobuf`, and `proto-plus` — the heaviest of which (`google-api-python-client`) was a 15.6MB wheel on its own. `google-auth`/`google-auth-oauthlib` are kept for credential/token handling.
- `ThaSheets`/`ThaDrive`'s export/download methods drop the SDK's chunked `MediaIoBaseDownload` loop for a single direct request — the chunking was only for progress/resumability, not a functional requirement, since Google's REST endpoints return the full body in one response either way.
- No existing public method signatures changed; this is an internal transport swap.
### Added
- `backend="requests"|"httpx"` keyword-only parameter on all five classes, forwarded to the underlying `tha-req-runner` transport. New `[httpx]` extra (`pip install tha-google-runner[httpx]`) so picking `backend="httpx"` doesn't require a second manual install.
- `GoogleHttpError` (raised for non-2xx REST responses, carrying `.status_code` and `.data`), now exported from the package alongside `GoogleError`.
- `ThaDocs.create(title) -> str` — creates a new blank document and returns its ID, mirroring `ThaSheets.create()`.
- README `## Alternatives` section (previously missing) covering gspread, google-api-python-client, PyDrive2, and EZGmail, and noting the lighter dependency footprint from this release.

## [0.1.8] - 2026-07-04
### Fixed
- `__init__.py` `__version__` was stale at `0.1.5` while `pyproject.toml` and PyPI were already at `0.1.7` — now back in sync.
- Test coverage gaps across the whole package: added tests for `auth.build_credentials`/`_oauth_credentials` (previously untested — 40% coverage), `cli.init()` (previously untested — 0% coverage), and smaller gaps in `docs.py`, `drive.py`, `errors.py`, `gmail.py`, `sheets.py`, and `slides.py` (lazy service-building, HTTP error re-raise branches, edge cases in text extraction and row normalization). Marked a handful of genuinely unreachable defensive branches (dead regex fallbacks, optional-import fallbacks for required deps) as `pragma: no cover`. Coverage is now 99% locally (100% on CI's Linux runner, where two platform-guarded `chmod` lines execute).

## [0.1.7] - 2026-06-27
### Changed
- Enabled mypy strict mode for comprehensive type checking.

## [0.1.6] - 2026-06-22
### Added
- Multi-tab support to `ThaDocs.read()` and `write()`.
- Test suite for `ThaDocs`.

## [0.1.5] - 2026-06-17
### Added
- Per-class OAuth scopes with least-privilege defaults.
- Scope-union re-authentication when combining multiple clients.

## [0.1.4] - 2026-06-16
### Changed
- Replaced `gspread` with `google-api-python-client` in `ThaSheets` for full Sheets API coverage.
- Added retry backoff across all module methods.

## [0.1.3] - 2026-06-16
### Added
- `ThaSlides` for Google Slides presentation management.
- `ThaGmail` for sending and reading Gmail messages.
- `ThaDrive.download` for downloading Drive files by ID.

## [0.1.2] - 2026-06-16
### Fixed
- mypy `no-redef` error in ADC credential variable naming.
- TestPyPI slot collision on repeated publish retries (added `skip-existing`).

## [0.1.1] - 2026-06-16
### Added
- `ThaDocs` for reading and writing Google Docs.
- Generalized auth layer supporting multi-API OAuth and ADC flows.

## [0.1.0] - 2026-06-13
### Added
- Initial release with `ThaSheets` for Google Sheets read/write and `ThaDrive` for file listing.
