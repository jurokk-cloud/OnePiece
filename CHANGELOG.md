# Changelog

All notable changes to `onepiece-studio` will be documented in this file.

The project follows a simple, research-software-oriented changelog style:

- `Added` for new capabilities
- `Changed` for behavior or architecture updates
- `Fixed` for bug fixes and scientific correctness corrections
- `Docs` for user-facing documentation and release-process improvements

## [1.0.1] - 2026-06-21

### Changed

- Bumped backend and frontend packaging metadata to `1.0.1`.
- Updated the `onepiece-studio` backend dependency floor to `onepiece[performance]>=1.0.1,<2.0.0`.

### Docs

- Updated release status markers in the README and Sphinx documentation.

## [1.0.0] - 2026-06-08

### Added

- Added release-grade QA wiring with `bandit`, `pre-commit`, and stricter
  packaging validation helpers for both distributions.
- Added explicit manifest files for the backend and UI distributions to make
  source archives deterministic.

### Changed

- Promoted both installable distributions to `1.0.0`.
- Tightened the backend package boundary so the `onepiece` wheel no longer
  ships legacy `pfui` artifacts or frontend code by accident.
- Gave `onepiece-studio` a clean package root under `ui/src` for independent
  publishing.
- Updated packaging metadata to modern SPDX-style license declarations and
  release-oriented build extras.

### Fixed

- Removed hard-coded local machine paths from shipped code and published report
  sources.
- Fixed the `onepiece-studio --version` output so it matches the real release
  version.
- Fixed backend and frontend wheel builds so they now produce clean `1.0.0`
  artifacts in this repository.

### Docs

- Reworked the repository README into a release-facing package overview with
  scientific formulas, diagrams, and install guidance.

## [0.7.0] - 2026-06-08

### Added

- Added a new `onepiece.xarray_vasp` module with labeled xarray workflows for
  `CHGCAR` and `DOSCAR`.
- Added `chgcar_to_xarray()`, planar/profile helpers, and DOS/PDOS xarray
  helpers for energy-window selection and band-center analysis.
- Added tests covering xarray-backed CHGCAR and DOSCAR transformations.
- Added a generated homework-style report with 10 plotted pages showing how
  OnePiece uses xarray for VASP data.

### Changed

- Bumped backend and UI packaging metadata to `0.7.0`.
- Declared `xarray` as a backend runtime dependency.

### Docs

- Added Sphinx documentation for the xarray VASP layer and linked it from the
  ASE-focused guide.

## [0.6.0] - 2026-06-08

### Added

- Added an optional Polars acceleration layer for backend paths that are truly
  tabular today: dataset text search, scalar facet/numeric filtering,
  gas-reference candidate detection, and grouped ranking.
- Added the backend extra `onepiece[performance]` and made the UI distribution
  depend on that accelerated backend variant.

### Changed

- Bumped backend and UI packaging metadata to `0.6.0`.
- Kept pandas as the scientific source of truth for ASE/object-heavy data while
  routing only scalar-safe operations through Polars when available.

### Docs

- Documented the performance extra in the install and API usage pages.

## [0.5.0] - 2026-06-08

### Added

- Added a second packaging project in `ui/pyproject.toml` so the frontend can
  be published as its own `onepiece-studio` distribution depending on the
  backend `onepiece` distribution.

### Changed

- Split the installable distributions as recommended earlier:
  - backend distribution: `onepiece`
  - UI distribution: `onepiece-studio`
- Root `pyproject.toml` now publishes the backend package only.
- Updated docs and installation guidance to reflect backend-only and full-UI
  install paths.

### Fixed

- Updated backend HDF-loading help text so it no longer assumes that every user
  installed the UI distribution.

## [0.4.0] - 2026-06-08

### Added

- Added `onepiece-studio tutorial` as a first-run command that opens the
  bundled Catalysis-Hub tutorial dataset directly in the UI.
- Added `onepiece-studio doctor` to check whether the current Python
  environment can import the main runtime dependencies and access the bundled
  dataset.
- Added a guided workflow recipe, `Adsorption + Gibbs analysis starter`, which
  derives `G` and `adsorption_free_energy` through backend DataFrame
  operations.
- Added beginner-oriented onboarding messages in the UI for empty sessions and
  starter-source loading.

### Changed

- Bumped the package version to `0.4.0`.
- Improved the built-in HDF fallback reader so it prefers the current Python
  interpreter and configurable helper paths instead of relying on one hardcoded
  local interpreter path.

### Fixed

- Made HDF loading errors clearer for missing `sympy`, missing `tables`, and
  wrong HDF key names.
- Made NumPy/HDF compatibility imports more tolerant so partial environments do
  not fail earlier than necessary during startup.

### Docs

- Expanded the README and Sphinx tutorial around a first-day student workflow.
- Added a dedicated troubleshooting page for installation and HDF loading.

## [0.3.0] - 2026-06-06

### Added

- Added a new `onepiece.vasp` backend module for reading VASP `CHGCAR` and
  `DOSCAR` files through the package API.
- Added `read_chgcar()` and `integrate_atomic_electron_populations()` for
  charge-density integration on a per-atom basis.
- Added `read_vasp_valence_electrons()` and `compute_atomic_charges()` for
  deriving atom-resolved charges when `POTCAR` or `OUTCAR` valence information
  is available next to the calculation.
- Added `read_doscar()`, `integrate_total_dos()`, and
  `integrate_projected_dos()` for total and site-projected density-of-states
  analysis.
- Added dataframe helpers `add_atomic_charge_descriptors()` and
  `add_projected_dos_descriptors()` so VASP-derived charge and PDOS quantities
  can be attached directly to OnePiece datasets.
- Added synthetic tests covering CHGCAR parsing, charge integration, DOSCAR
  parsing, projected-DOS integration, and dataframe enrichment.

### Changed

- Bumped the package version to `0.3.0`.
- Exported the new VASP readers and descriptor helpers from both `onepiece` and
  `onepiece_studio`.

### Docs

- Updated package documentation and citation metadata for the `0.3.0` release.

## [0.2.0] - 2026-06-06

### Added

- Introduced the `onepiece` backend package as the scientific execution layer
  for adsorption, thermochemistry, workflow execution, source handling, query
  filtering, and project persistence.
- Introduced the `onepiece_studio` frontend package as the Streamlit-based UI
  layer for local scientific database work.
- Added a bundled Catalysis-Hub reference HDF dataset for package-level QA.
- Added the `onepiece-studio qa` command to validate installed scientific
  behavior against the bundled reference dataset.
- Added Sphinx package documentation for installation, API usage, quality
  control, and release workflow.
- Added a repository release gate with CI checks for lint, tests, packaged QA,
  documentation build, and artifact validation.

### Changed

- Renamed the installable product from the legacy PFUI identity to
  `onepiece-studio`.
- Renamed the frontend import package to `onepiece_studio`.
- Renamed internal Streamlit session keys and source metadata fields from
  `pfui_*` to `onepiece_studio_*`.
- Moved workflow execution out of the UI layer into `onepiece.workflows`.
- Moved Controlroom filtering and materials-query logic into
  `onepiece.services.dataset_service`.
- Moved source preparation and capability profiling into `onepiece.sources`.
- Moved project save/load semantics into `onepiece.projects.persistence`.
- Tightened release engineering around wheel/sdist validation and clean-install
  checks.

### Fixed

- Corrected gas-reference auto-detection for `CO2` and `H2O` in the workflow
  pipeline.
- Prevented curation rules from excluding valid gas-reference rows solely due
  to missing structure objects.
- Fixed `Open ASE` handling and multiple UI workflow/selection regressions
  discovered during the full UI audit.
- Fixed lint-level correctness issues so Ruff now passes for the enforced rule
  set.

### Docs

- Added `LICENSE`, `CITATION.cff`, and release-process documentation for
  publishing and citation.
- Reframed the documentation site around the package rather than the earlier
  project-specific PFUI identity.
