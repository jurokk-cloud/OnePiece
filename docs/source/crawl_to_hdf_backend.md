# Crawling To HDF

This page describes the workflow as if the HDF file is produced by crawling
calculation folders. That is the right mental model even when the tutorial uses
the bundled package HDF directly.

In practice there are two equivalent entry points:

1. **Crawl first**: scan a calculation root and write a new HDF file.
2. **Load existing HDF**: treat an existing HDF file as the already materialized
   result of a previous crawl.

The bundled tutorial file follows path 2:

```text
src/onepiece/data/catalysis_hub_co2_subset.hdf
```

For documentation and teaching, we explain it as if it came from path 1.

## Crawl-Level Data Flow

```text
root/
  calc_001/
    final.traj
    out.txt
    CHGCAR
    DOSCAR
  calc_002/
    final.traj
    out.txt
    CHGCAR
    DOSCAR
        |
        v
crawl_calculation_paths(...)
        |
        v
crawl_calculation_directories(...)
        |
        v
create_calculation_frame(...)
        |
        v
enrich_electronic_summaries(...)
        |
        v
crawl_root_to_frame(...)
        |
        v
crawl_root_to_hdf(...)
```

The output is a dataframe where one row corresponds to one useful scientific
record: a surface, adsorbate, gas reference, reaction row, or calculation
summary.

## Minimal Crawl

Use this when you want a dataframe first and will decide later whether to save
it as HDF:

```python
from onepiece import crawl_root_to_frame

frame = crawl_root_to_frame(
    root="calculations/mnvo_oer",
    calc_file="final.traj",
    thermo_filename="out.txt",
    read_electronic_files=False,
)
```

This returns a `pandas.DataFrame`. At this stage the important check is not
whether every descriptor exists. The important check is whether every row has a
stable identity and enough source information to be traced back to the
calculation folder.

## Crawl Directly To HDF

Use this when you want a portable HDF artifact:

```python
from onepiece import crawl_root_to_hdf

crawl_root_to_hdf(
    root="calculations/mnvo_oer",
    output_path="data/mnvo_oer_crawl.hdf",
    key="df",
    calc_file="final.traj",
    thermo_filename="out.txt",
    read_electronic_files=False,
)
```

After this step, the HDF can be opened by the CLI:

```bash
onepiece-studio hdf data/mnvo_oer_crawl.hdf --key df --title "MnVO OER Crawl"
```

## Two-Stage Electronic Enrichment

Large VASP folders can contain heavy files. For large local datasets, separate
the structure/energy crawl from electronic descriptor enrichment:

```python
from onepiece import crawl_root_to_frame, enrich_electronic_summaries

base = crawl_root_to_frame(
    root="calculations/cu_zno_methanol",
    read_electronic_files=False,
)

enriched = enrich_electronic_summaries(
    base,
    workers=12,
)
```

This pattern is useful because the first step gives you a quick table for
screening, while the second step adds more expensive descriptors such as charge
and DOS summaries.

## Treating The Bundled HDF As Crawl Output

The bundled file can be read exactly like a crawled HDF:

```python
from onepiece import bundled_catalysis_hub_dataset
from onepiece.sources import read_hdf_path

path = bundled_catalysis_hub_dataset()
frame = read_hdf_path(path, key="df")

print(frame.shape)
print(frame.columns)
```

The current bundled file has 133 rows and 31 columns. Important columns include:

- `Name`
- `Equation`
- `reactionEnergy`
- `activationEnergy`
- `surfaceComposition`
- `facet`
- `E`
- `Formula`
- `Adsorbate`
- `Substrate`
- `struc`
- `record_class`

For a new user, this is the safest starting point: it behaves like a crawled
dataset, but it is small enough to inspect completely.

## From HDF To Managed Dataset

An HDF file is portable, but it does not by itself contain the full FAIR
contract. Once the dataframe has been checked and enriched, save it as a managed
OnePiece dataset:

```python
from onepiece.provenance import ReferenceScheme
from onepiece.storage import resolve_storage_config, save_dataset

reference_scheme = ReferenceScheme.gas_phase(
    name="Catalysis-Hub CO2 gas references",
    gas_references_eV={
        "CO2": -22.1,
        "H2": -6.8,
    },
)

config = resolve_storage_config(".onepiece")

manifest_path = save_dataset(
    frame,
    dataset_id="catalysis_hub_co2_subset",
    config=config,
    source_path=str(path),
    reference_scheme=reference_scheme,
    metadata={
        "project": "CO2 reduction tutorial",
        "source": "bundled Catalysis-Hub subset",
        "license": "check upstream source license",
        "citation": "Catalysis-Hub-derived OnePiece tutorial subset",
    },
)
```

The managed dataset contains:

- the dataframe table
- sidecars for object columns when needed
- `manifest.json`
- source path
- source/provenance metadata
- thermodynamic reference scheme

## Practical Rule

Use HDF for exchange and quick loading. Use a managed OnePiece dataset when the
table should be reused, audited, or attached to a project.
