# OnePiece Overhaul — Audit & Roadmap

Branch: `fable-overhaul`. Goal: incremental overhaul keeping Streamlit —
better first-run experience, clearer UI, friendlier Python API, restructured
docs. Target users: grad students in computational catalysis.

## Done so far

- **Baseline established**: 134 tests pass, ruff clean (venv at
  `~/.venvs/onepiece`, Python 3.14).
- **NumPy 2 compatibility fixed** (`48ab149`): `np.trapz` was removed in
  NumPy 2.0 and broke 8 tests / 9 call sites; now routed through
  `onepiece._compat.trapezoid`.
- **Missing dependency declared** (`48ab149`): `onepiece.ir` imports seaborn,
  which was never in any requirements list; added to studio/dev/docs extras.
- **Dead duplicate removed** (`31413af`): `src/onepiece_studio/` was a
  byte-identical, never-packaged copy of `ui/src/onepiece_studio/` (~5k
  lines). `ui/src` is now the single source of truth.

## Phase 1 — completed 2026-06-10

1. `54433ba` One HDF read path (`onepiece.sources.core.read_hdf_path`);
   UI `HDFSource` delegates to it. Helper-interpreter fallback deleted;
   NumPy pickle shim documented in `onepiece._compat`; wrong-key errors
   list the file's actual keys; regression tests added. Test suite runs
   ~2.5x faster (no subprocess per HDF read).
2. `77559ff` Versions come from package metadata (`__version__` on both
   packages, CLI `--version`).
3. `046c0e4` Formula helpers deduplicated (three copies → one in
   `onepiece.adsorption`; the UI copies were dead code).
4. `d3cfc9b` Shared session-state keys centralized in
   `onepiece_studio.state`.
5. `17cd264` CI repaired: installs both packages (was silently relying
   on the deleted duplicate via PYTHONPATH), matrix extended to
   Python 3.13/3.14, ui/src linted, release_check.py fixed the same way.

## Phase 2 — completed 2026-06-10

1. `4626b11` Welcome screen: bare `onepiece-studio` opens tutorial /
   open-file / upload / recent-files page instead of an empty session.
   Fixed two pre-existing crashes the bundled tutorial dataset triggered
   (duplicate Name index labels broke `apply_dataset_query` and the
   record-detail panel) — `onepiece-studio tutorial` was broken before this.
2. `3dbc335` Friendly failure screens: CLI hdf launches and mid-session
   load failures show actionable errors with key-retry, not tracebacks.
3. PyTables stays required (see roadmap note).
4. `95ad4bc` CONTRIBUTING.md (layout, setup, NTFS pitfall, conventions);
   README leads with the bare launch.
5. `8ca1404` CLI doctor/qa output colored on TTYs (side request).

## Phase 3 — completed 2026-06-10

1. `e27c5eb` Multi-page `st.navigation` app replacing the 7-tab wall, grouped
   Data / Explore / Analyze / Advanced; "Controlroom" renamed "Filter";
   session pipeline computable without rendering; file loads cached.
2. `b22f6ed` workflow_builder.py split 1414 → 244 lines: pure computation in
   `workflow_logic.py` (Streamlit-free), Add Operation tab in
   `workflow_steps.py`, Notebook Automation tab in `workflow_automation.py`
   (the 478-line render function is now a dispatcher plus one function per
   block), shared state helpers in `workflow_session.py`. Compat re-exports
   keep existing tests and desktop scripts working; three dead `_parse_*`
   helpers removed.
3. `6f6c1dd` controlroom.py split 848 → 484 lines: filter computation goes
   through `apply_controlroom_filters` with no duplicated logic in the
   rendering module; 4 new backend tests (156 total).
4. `18d7cb9` streamlit_app.py slimmed 945 → 252 lines: app setup, navigation
   wiring, sidebar summary, and CLI entry only; page bodies live in the
   per-page modules.

Phases 1–2 were run interactively; Phase 3 tasks 2–4 above were executed by
the agent harness (`.harness/`), each gated by verification (ruff + full
suite) and a skeptical evaluator session — all three passed.

## Phase 4 — completed 2026-06-10

1. `4e0ab2a` adsorption.py (1051 lines) split into a subpackage by concern:
   `formulas.py` (stoichiometry, adsorbate detection), `references.py`
   (gas/surface references, OnePiece HDF reading), `energies.py`
   (adsorption-energy math and view), `copt.py` (constrained-optimization
   paths). Code moved verbatim; `__init__.py` re-exports every public name,
   so no caller changes; seam tests cover re-export completeness and a
   per-module size budget.
2. `4aced23` Top-level namespace curated from ~154 flat re-exports down to 15
   core names grouped by task (load data, adsorption energetics,
   thermochemistry, plotting). Every legacy export still importable via a
   lazy `__getattr__` alias that emits a DeprecationWarning naming its
   submodule home; `__dir__` keeps tab-completion to the curated set;
   internal callers import from submodules so the library never warns at
   itself. `test_public_api.py` freezes the legacy list as a contract.
3. `d8eceb3` Every curated export now has a docstring with an example —
   thirteen runnable doctests (bundled Catalysis-Hub tutorial data where
   real data is needed) plus two code-block examples for names needing
   external inputs. `test_docstring_examples.py` enforces this in CI.

All three tasks executed by the harness, each evaluator-PASSed; suite grew
156 → 308 tests, ruff clean throughout.

## Audit findings

### Backend (`src/onepiece`, ~10k lines)
- `__init__.py` re-exports ~100 names from 16 modules in one flat namespace —
  overwhelming for newcomers, no guidance on what matters.
- `adsorption.py` (1051 lines) mixes formula parsing, HDF reading, reference
  assignment, and energy math.
- `workflows/registry.py` is 15 lines against a 446-line engine — the
  registry concept is vestigial.
- UI CLI hardcodes `onepiece-studio 1.0.0` instead of reading package
  metadata.

### UI (`ui/src/onepiece_studio`, ~5k lines)
- `adapters.py:53-59` retries the byte-identical `pd.read_hdf` call in its
  `except` branch, then falls back to spawning a *second Python interpreter*
  (with hardcoded `/opt/homebrew` paths) to convert HDF → pickle → re-read.
  Needs one read path with a clear error; the NumPy 1↔2 pickle-compat shim
  (`sys.modules` monkey-patching) needs a documented, tested home.
- Giant modules/functions: `workflow_builder.py` 1411 lines
  (`_render_notebook_automation` alone is 478), `controlroom.py` 869,
  `streamlit_app.py` 860.
- Pure data logic (formula parsing, element counting) lives in UI files and
  partially duplicates backend functions (`onepiece.adsorption.formula_counts`
  vs `controlroom._formula_counts`) — the README's own "thin UI" goal is not
  upheld.
- 24 distinct `st.session_state` keys managed ad hoc, no central definition.
- Single page with 7 simultaneous tabs (Workflow, Controlroom, Data
  Management, Adsorption & Barriers, Records, Visualize, Schema).
  "Controlroom" is jargon; a new user gets everything at once.
- Good bones to keep: `doctor` env check, `qa` self-test, bundled tutorial
  dataset, beginner-guidance hooks.

### Tests & tooling
- 134 tests, heaviest on UI workflow state; core science modules thinner.
  No coverage measurement, no CI workflow in the repo.

### Docs (25 pages)
- Content is rich (worked examples, `first_day_student.md`, troubleshooting)
  but flat — no audience-based entry paths.

### Dev environment
- Repo lives on an NTFS (`ntfs3`) mount: creating a venv there stalls in
  uninterruptible I/O. Venvs must live on a Linux filesystem
  (`~/.venvs/onepiece`). Document for contributors.

## Roadmap

### Phase 1 — Foundations (correctness & hygiene)
1. Rewrite `HDFSource.load`: single read path, clear actionable errors
   (file missing / wrong key / legacy pickle), isolate the NumPy pickle shim,
   delete the helper-interpreter fallback.
2. Version from `importlib.metadata` everywhere; single source in pyproject.
3. Move pure data logic out of UI into the backend; UI imports it.
4. Central `state.py` defining all session-state keys.
5. Add GitHub Actions CI: pytest + ruff, Python 3.10–3.14.

### Phase 2 — First-run experience
1. `onepiece-studio` with no args → welcome page: open tutorial dataset,
   pick a file, recent files list — instead of requiring subcommands.
2. Friendly failure screens (bad HDF, wrong key, missing optional deps)
   with the fix spelled out.
3. ~~Evaluate making PyTables optional~~ — evaluated 2026-06-10, decision:
   **keep required**. The bundled tutorial dataset and the `qa` self-test
   are HDF, and HDF is the group's primary format (20 call sites). Revisit
   only if parquet becomes the default storage format.
4. Contributor setup guide (incl. NTFS pitfall).

### Phase 3 — UI redesign (within Streamlit)
1. Multi-page app (`st.navigation`) replacing the 7-tab wall:
   Data → Filter → Analyze → Visualize → Export, with a guided flow.
2. Rename jargon ("Controlroom" → "Filter"), progressive disclosure for
   advanced tools (workflow builder, schema inspector).
3. Split the giant modules one-page-per-module; add `st.cache_data` on loads.

### Phase 4 — Python API
1. Curated top-level namespace (~15 core functions), documented submodules,
   deprecation aliases for everything moved.
2. Split `adsorption.py`; docstrings with examples on the core API.

### Phase 5 — Docs & tutorials
1. Three entry paths: "I have a dataset, show me" (UI), "I write notebooks"
   (API), "I'm starting my thesis" (concepts).
2. Quickstart rewritten against the new welcome flow; troubleshooting
   consolidated.

### Phase 6 — Test depth
1. Coverage measurement in CI; raise coverage of energy/reference math;
   golden-file tests for the worked examples.
