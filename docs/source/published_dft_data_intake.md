# Published DFT Data Intake

Research articles sometimes publish DFT data as supporting information, Zenodo
archives, NOMAD uploads, Catalysis-Hub entries, GitHub repositories, CSV files,
HDF files, or raw VASP folders.

OnePiece can use those datasets, but they should be imported with provenance and
license discipline. Published numbers are not automatically reusable just
because they are downloadable.

## Intake Checklist

Before adding an external dataset, record:

| Item | Why it matters |
|---|---|
| Article citation | The dataset must remain attributable. |
| DOI or URL | Users need to find the source again. |
| License | Determines whether redistribution is allowed. |
| DFT code and version | VASP, GPAW, Quantum ESPRESSO, CP2K, etc. |
| Functional and dispersion | Energies are not comparable without this. |
| PAW/pseudopotential setup | Especially important for transition metals and oxides. |
| Slab model | Facet, termination, layers, vacuum, constraints. |
| Reference convention | Gas references, CHE, oxygen chemical potential, pH, potential. |
| Units | eV, eV/atom, kJ/mol, J/mol/K, cm-1. |
| Raw files available | `OUTCAR`, `CONTCAR`, `vasprun.xml`, `CHGCAR`, `DOSCAR`, etc. |

## Recommended Local Layout

Use a separate raw-data area outside the package source tree:

```text
external_data/
  article_slug/
    README.md
    raw/
    processed/
    onepiece/
```

Keep a short `README.md` next to the raw data:

```text
source: article DOI or repository URL
license: CC-BY-4.0 / unknown / publisher terms
downloaded_at: YYYY-MM-DD
notes: any manual conversion or missing files
```

Only commit derived, redistributable fixtures to the package repository.

## Convert To OnePiece

For raw VASP folders:

```python
from onepiece import crawl_root_to_frame

frame = crawl_root_to_frame(
    "external_data/article_slug/raw",
    calc_file="CONTCAR",
    read_electronic_files=False,
)
```

For CSV/HDF/parquet tables, normalize columns to the canonical schema:

```python
from onepiece.frame_utils import ensure_name_index

frame = raw.rename(
    columns={
        "energy": "E",
        "formula": "Formula",
        "path": "Path",
    }
)
frame = ensure_name_index(frame)
```

## Attach Reference And Provenance

```python
from onepiece import ReferenceScheme, save_dataset
from onepiece.storage import ensure_storage_layout, resolve_storage_config

scheme = ReferenceScheme.gas_phase(
    name="article-reference-scheme",
    gas_references_eV={"CO2": -22.1, "H2": -6.8},
    metadata={
        "source": "DOI or URL",
        "note": "Transcribed from supporting information; verify before publication use.",
    },
)

config = ensure_storage_layout(resolve_storage_config(".onepiece"))
save_dataset(
    frame,
    dataset_id="article-slug-normalized",
    config=config,
    source_path="external_data/article_slug/raw",
    reference_scheme=scheme,
    metadata={
        "citation": "Full citation",
        "license": "License or redistribution status",
        "doi": "DOI",
        "description": "Normalized published DFT dataset.",
    },
)
```

## Quality Gate

Before using external data in a tutorial or comparison:

```bash
onepiece-studio fair-audit .onepiece/workspace/article-slug-normalized \
  --require-reference-scheme \
  --require-publication-metadata
```

Then check:

- row count matches the publication or supporting information
- units have been converted
- references match the article's equations
- no missing clean-surface references entered adsorption calculations
- licensing permits redistribution if the data are committed

## What Not To Commit

Avoid committing:

- publisher PDFs
- proprietary raw VASP outputs if redistribution is unclear
- large CHGCAR/DOSCAR files
- downloaded archives with unknown license
- private cluster paths containing user or project-sensitive information

Prefer small, curated fixtures with clear citation and license metadata.

