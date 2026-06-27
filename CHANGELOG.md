# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
