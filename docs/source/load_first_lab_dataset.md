# Load Your First Lab Dataset

This page is for a new student who already confirmed that:

- `onepiece-studio doctor` passes
- `onepiece-studio qa` passes
- `onepiece-studio tutorial` opens correctly

Now the next step is to load the first real group dataset.

## 1. Pick The Right File

Use a dataset file that already contains a table of calculations, for example:

- `.hdf`
- a OnePiece parquet/manifest dataset
- a folder tree only if your group explicitly wants you to crawl raw calculations

If you are unsure, ask for the file that the group already uses for analysis.

## 2. Know What The Main Table Is

For HDF files, the most common key is:

```bash
df
```

If the dataset opens but looks empty, the wrong key is often the reason.

## 3. Check The Minimum Required Columns

A useful first dataset should contain at least some of these columns:

- `Name`
- `Formula`
- `E`
- `Path`
- one structure column such as `struc`, `CONTCAR`, or another ASE `Atoms` column

Good additional columns are:

- `fmax`
- `dataset`
- `surface_ref`
- element counts
- adsorption-related columns
- thermochemistry columns

## 4. Open It In The UI

Example:

```bash
onepiece-studio hdf "/path/to/your_dataset.hdf" --key df --title "My Lab Dataset"
```

## 5. First Checks In The UI

After loading, open these tabs in order:

1. `Data Sources`
2. `Schema`
3. `Records`
4. `Workflow`
5. `Visualize`

In `Schema`, confirm:

- row count is reasonable
- important columns exist
- numeric columns are really numeric
- structure columns are present
- missing values are not overwhelming

## 6. First Workflow To Run

Start with one safe backend-driven workflow, for example:

- `Adsorption + Gibbs analysis starter`

or, if the dataset is still raw:

- element counting
- reference assignment
- simple derived-column creation

The goal is to confirm that backend operations work on the real lab dataset.

## 7. First Plot To Make

Use one simple plot first:

- `E` vs composition
- adsorption energy vs descriptor
- `fmax` distribution
- count of rows by dataset or material type

Do not start with a complex publication plot.

## 8. If Loading Fails

The common causes (wrong path, wrong HDF key, missing optional
dependencies, legacy NumPy-1 pickles) and their fixes are collected in
[Troubleshooting](troubleshooting.md). Match the error message you see to
the cases there.

## 9. If The Dataset Loads But Analysis Fails

Usually that means one of these is missing:

- consistent row identity (`Name`)
- clear reference rows
- usable structure column
- numeric energy column
- enough metadata to distinguish gas, bulk, slab, and adsorbate rows

## 10. What To Save For The Supervisor

After the first successful load, save:

- the exact file path
- the key used
- the row count
- the main columns present
- the first workflow that worked
- the first plot that looked reasonable

That gives the group a reproducible starting point.
