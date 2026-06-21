# Canonical DataFrame Schema

OnePiece is dataframe-first. The package does not require every dataset to have
every column, but several column names have stable meaning across the backend,
the tutorials, and OnePiece Studio.

This page documents that implicit contract explicitly. Treat it as the schema
for a OnePiece-compatible catalytic dataset.

## Row Identity

| Column | Required | Meaning |
|---|---:|---|
| `Name` | yes | Stable row label for a calculation, structure, gas reference, surface, adsorbate, or pathway image. |
| `source_hdf` | recommended | Source file that produced the row. |
| `source_row` | recommended | Row identifier inside the source file. |
| `dataset` | recommended | Short source dataset name. |
| `dataset_label` | recommended | Human-readable source label. |

`Name` is the canonical index after `ensure_name_index(...)`. If multiple
sources are merged, `source_hdf` plus `source_row` should be used for stable UI
state, provenance, and row review.

## Structures

| Column | Required | Meaning |
|---|---:|---|
| `struc` | recommended | Preferred ASE `Atoms` object for the row. |
| `CONTCAR` | optional | ASE `Atoms` object read from a VASP `CONTCAR`. |
| `structure` | optional | Alternative ASE `Atoms` object column. |
| `atoms` | optional | Alternative ASE `Atoms` object column. |
| `Path` | recommended | Calculation folder or source path. |

The backend searches structure columns in this order in several helper
functions:

```text
struc, CONTCAR, structure, atoms
```

For new datasets, prefer `struc`.

## Energies And Forces

| Column | Required | Meaning |
|---|---:|---|
| `E` | yes for energetics | Electronic energy, normally in eV. |
| `G` | optional | Gibbs free energy after thermochemical correction. |
| `fmax` | recommended | Maximum force, usually eV/A. |
| `E_ZPE` | optional | Zero-point energy correction. |
| `Cv_trans` | optional | Gas translational heat-capacity contribution in eV. |
| `Cv_rot` | optional | Gas rotational heat-capacity contribution in eV. |
| `Cv_vib` | optional | Vibrational heat-capacity contribution in eV. |
| `S_trans` | optional | Gas translational entropy in eV/K. |
| `S_rot` | optional | Gas rotational entropy in eV/K. |
| `S_vib` | optional | Vibrational entropy in eV/K. |

`add_gibbs_free_energy(...)` uses gas-phase rows differently from surface and
adsorbate rows. Gas rows use translational, rotational, and vibrational terms.
Surface and adsorbate rows use vibrational terms only.

## Chemistry Labels

| Column | Required | Meaning |
|---|---:|---|
| `Formula` | recommended | Chemical formula string. |
| `record_class` | recommended | Semantic row class such as `gas_reference`, `surface`, `bulk`, or `adsorbate`. |
| `adsorbate` | derived | Adsorbate label inferred from name or workflow metadata. |
| `surface_key` | derived | Clean-surface matching key. |
| `is_adsorbate` | derived | Boolean marker for adsorbate rows. |

Name-based inference is useful for old HDF files, but it should not be the only
source of truth in publication datasets. Prefer explicit `record_class`,
`adsorbate`, and reference metadata when possible.

## Surface References

| Column | Required | Meaning |
|---|---:|---|
| `surface_ref_name` | derived | Matched clean-surface row name. |
| `surface_ref_E` | derived | Electronic energy of the matched clean surface. |
| `surface_ref_G` | optional | Free energy of the matched clean surface. |
| `surface_ref_formula` | derived | Formula of the clean-surface reference. |
| `surface_ref_status` | recommended | Reference match status such as `ok`, `missing`, or `ambiguous`. |
| `surface_ref_ambiguous` | derived | Boolean ambiguity flag. |

Ambiguous or missing references should block automatic adsorption-energy
interpretation. They can still be shown in the UI, but they should not silently
enter thermodynamic plots.

## Adsorption Outputs

| Column | Required | Meaning |
|---|---:|---|
| `adsorption_energy` | optional | Generic adsorption energy in eV. |
| `adsorption_free_energy` | optional | Generic adsorption free energy in eV. |
| `E_ads_*_eV` | optional | Adsorbate-specific per-adsorbate energy. |
| `E_ads_*_total_eV` | optional | Total adsorption energy for the row. |
| `n_*_adsorbates` | optional | Adsorbate count used for normalization. |

These columns are not fully reusable without reference-scheme metadata. For
publication-grade datasets, store the `ReferenceScheme` in managed dataset
provenance when calling `save_dataset(...)`.

## VASP File Paths

| Column | Required | Meaning |
|---|---:|---|
| `final_traj_path` | optional | Path to `final.traj`. |
| `contcar_path` | optional | Path to `CONTCAR`. |
| `outcar_path` | optional | Path to `OUTCAR`. |
| `poscar_path` | optional | Path to `POSCAR`. |
| `incar_path` | optional | Path to `INCAR`. |
| `kpoints_path` | optional | Path to `KPOINTS`. |
| `potcar_path` | optional | Path to `POTCAR`. |
| `chgcar_path` | optional | Path to `CHGCAR`. |
| `doscar_path` | optional | Path to `DOSCAR`. |
| `acf_path` | optional | Path to `ACF.dat`. |

These columns let descriptor functions find heavy electronic-structure files
without loading them into the dataframe.

## Provenance Columns And Manifest Fields

Managed datasets store most provenance in `manifest.json`, not row columns.
Important manifest fields are:

| Field | Meaning |
|---|---|
| `dataset_id` | Stable local dataset identifier. |
| `storage_format` | `parquet` or `hdf`. |
| `columns` | DataFrame columns present when saved. |
| `object_columns` | Columns written to the Python-object sidecar. |
| `metadata` | Human/publication metadata such as license and citation. |
| `provenance` | JSON-native entities, activities, agents, FAIR metadata, and reference scheme. |

The practical rule is:

```text
columns describe the table
manifest metadata describes the dataset
manifest provenance describes how the table was created
```

## Minimum Useful Dataset

A small dataset that supports useful OnePiece workflows should contain:

```text
Name
E
Formula
Path
struc
fmax
record_class
```

A reusable catalysis dataset should additionally include:

```text
source_hdf
source_row
surface_ref_name
surface_ref_E
adsorbate
reference scheme in manifest provenance
license and citation in manifest metadata
```

