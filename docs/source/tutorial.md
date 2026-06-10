# Quickstart: Launch onepiece-studio And Explore A Dataset

This page takes you from a fresh install to your first adsorption analysis
using the bundled tutorial dataset. No code and no input files are required.

## 1. Install The Package

For the full UI workbench:

```bash
pip install onepiece-studio
```

For backend-only Python workflows (no UI):

```bash
pip install onepiece
```

If you work in notebooks rather than the app, switch to
[API and CLI usage](api_usage.md) after this page.

## 2. Launch The App

```bash
onepiece-studio
```

The app opens in your browser (Streamlit prints the local URL, usually
`http://localhost:8501`) and shows the **welcome page** with three ways in:

- **New here?** — one button that opens the bundled Catalysis-Hub tutorial
  dataset. Nothing to download or configure.
- **Open your data** — enter the path to a local pandas HDF file (plus its
  HDF key, `df` by default) or upload an `.hdf`/`.h5` file.
- **Recent files** — datasets you opened before, one click to reopen.

For this quickstart, click **Open the tutorial dataset**. If you want to
skip the welcome page on later launches, `onepiece-studio tutorial` opens
the same bundled dataset directly.

## 3. Check Your Environment (Optional)

Two self-check commands are available if anything looks off:

```bash
onepiece-studio doctor    # verifies imports and the bundled dataset
onepiece-studio qa        # round-trips the bundled Catalysis-Hub dataset
```

`qa` reconstructs adsorption energies from the bundled dataset and compares
them to the stored reaction energies. A healthy install reports:

```text
[PASS] catalysis-hub self-test
- rows: 133
- adsorbate_rows: 34
- computed_adsorption_rows: 9
```

If either command fails, see [troubleshooting](troubleshooting.md).

## 4. Find Your Way Around

Once a dataset is open, the sidebar shows the workbench navigation in four
sections:

| Section | Pages | What it is for |
|---|---|---|
| **Data** | Data | Dataset overview, session data sources, and the column schema |
| **Explore** | Filter, Records, Visualize | Narrow down rows, inspect them, and plot them |
| **Analyze** | Adsorption & Barriers, Manage & Export | Adsorption workbench and saving or exporting your work |
| **Advanced** | Workflow Builder | Reproducible backend DataFrame operations |

The pages share one pipeline: data sources are merged on the **Data** page,
the **Workflow Builder** derives columns on top of them, and the **Filter**
page selects the rows that every other page works with. The sidebar always
shows how many records are currently selected.

## 5. The Workflow Model

OnePiece Studio is designed around a simple idea:

1. a local dataset is loaded into a `pandas.DataFrame`
2. the `onepiece` backend applies scientific DataFrame operations
3. the UI lets you inspect, filter, visualize, and save that work

The UI is not meant to replace scientific thinking. It is meant to make the
DataFrame workflow reproducible and easier to inspect.

## 6. First Analysis On The Tutorial Dataset

With the tutorial dataset open:

1. On the **Data** page, expand **Data Sources** to see how the bundled
   dataset is represented, and expand **Schema** to see which columns are
   numeric, which contain ASE structures, and which have missing values.
2. Go to **Advanced → Workflow Builder** and add the
   `Adsorption + Gibbs analysis starter` recipe. It assigns clean-surface
   references, derives Gibbs free energies (`G`), and calculates
   `adsorption_free_energy` where the required references are available.
3. Go to **Explore → Records** and inspect the new `G` and
   `adsorption_free_energy` columns.
4. Go to **Explore → Visualize** and start from a preset such as
   `Adsorption analysis` to compare candidates.

This sequence keeps you inside backend-driven DataFrame operations while
giving immediate visual feedback.

```{image} _static/screenshots/records.png
:alt: OnePiece Studio records view
:class: screenshot
```

## 7. Filter And Visualize

### Filter

Use the **Filter** page (under **Explore**) to:

- search by `Name`, `Formula`, dataset, or source path
- filter by composition, materials-system logic, numeric windows, or row state
- keep only rows that belong in the active analysis set

The filtered selection feeds Records, Visualize, and the Analyze pages.

### Visualize

Use the **Visualize** page to build scatter and comparison plots from numeric
columns. Good first plots are:

- energy versus composition
- formation energy versus surface area
- adsorption energy versus descriptor columns
- quality metrics such as `fmax`

If you are working with ASE/VASP-enriched adsorption datasets, the most useful
views are documented in
[Recommended Analysis Views](recommended_analysis_views.md).

```{image} _static/screenshots/visualize.png
:alt: OnePiece Studio visualization view
:class: screenshot
```

### Schema

Before a workflow becomes large, use the **Schema** expander on the **Data**
page to confirm which columns are numeric, object-like, structure-bearing, or
incomplete.

```{image} _static/screenshots/schema.png
:alt: OnePiece Studio schema view
:class: screenshot
```

## 8. Work With Scientific State, Not Just Tables

The workbench supports workflow operations, saved views, source blocks,
row-state curation, workbook edits, and project save/load — found on the
**Analyze** pages (**Adsorption & Barriers**, **Manage & Export**) and in the
**Workflow Builder**. This is what turns the software from a passive table
viewer into a real local scientific workbench.

## 9. Where To Go Next

- [Load Your First Lab Dataset](load_first_lab_dataset.md) — open your own
  HDF file from the welcome page and shape it for the workbench
- [First Day Guide For A Bachelor Student](first_day_student.md) — a slower
  onboarding path with the scientific context
- The Cu/Ga-oriented worked examples on the concepts track show how
  structure, energy, and provenance coexist in one DataFrame and how the
  workbench maps domain-specific columns into useful views
