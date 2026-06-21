# Contributing to OnePiece

## Repository layout

This repository ships two Python distributions:

| Distribution | Code | What it is |
|---|---|---|
| `onepiece` | `src/onepiece/` | Backend: data import, energies, thermochemistry, storage |
| `onepiece-studio` | `ui/src/onepiece_studio/` | Streamlit workbench on top of the backend |

The UI package depends on the backend. There is exactly one copy of each
package — do not add copies of `onepiece_studio` elsewhere in the tree.

## Development setup

```bash
python -m venv ~/.venvs/onepiece          # see filesystem note below
source ~/.venvs/onepiece/bin/activate
pip install -e ".[dev]" -e ./ui
```

> **Filesystem note:** create the virtualenv on a native Linux filesystem
> (ext4, btrfs, xfs — e.g. somewhere in your home directory). Creating a
> venv on an NTFS or exFAT mount (external drives) is extremely slow and
> can hang in uninterruptible I/O. The repository itself can live anywhere.

Supported Python versions: 3.10 – 3.14.

## Running checks

```bash
python -m pytest -q                      # test suite
python -m ruff check src ui/src tests examples
python scripts/release_check.py --skip-docs --skip-build   # quick gate
python scripts/release_check.py          # full gate: docs build, wheels, twine
```

CI (`.github/workflows/ci.yml`) runs lint plus the test suite on
Python 3.10–3.14 and the release gate on every PR. All jobs install both
packages editable; nothing relies on `PYTHONPATH`.

## Trying the app

```bash
onepiece-studio                # welcome page: tutorial, open file, recent files
onepiece-studio tutorial       # open the bundled Catalysis-Hub dataset directly
onepiece-studio doctor         # environment self-check
onepiece-studio qa             # dataset round-trip self-test
```

## Conventions

- Ruff is the formatter/linter authority; run `ruff check --fix` before
  committing.
- Pure data logic (parsing, energetics, frame transforms) belongs in the
  backend, never in `ui/` — the UI renders and delegates.
- HDF files are read through `onepiece.sources.core.read_hdf_path` only;
  it owns the error messages and the NumPy pickle-compat shim
  (`onepiece._compat`).
- Session-state keys shared between UI modules are constants in
  `onepiece_studio/state.py`.
- Versions come from package metadata; never hardcode a version string.
- `OVERHAUL_NOTES.md` tracks the ongoing modernization roadmap.
