# onepiece-studio Documentation

`onepiece-studio` is a local scientific database workbench for computational
chemistry and materials science.

It combines:

- `onepiece`: a backend engine for scientific `pandas.DataFrame` workflows
- `onepiece_studio`: a local UI for search, filtering, visualization, project
  state, and structure inspection

The package is designed for local HDF datasets, ASE structures, adsorption
workflows, reaction-path analysis, and reproducible scientific curation.

## What This Site Covers

- how to install and launch the package
- how to run the built-in package QA
- how to use the Python API and CLI
- how the UI works with `pandas` and ASE
- how to think about the package if ASE is already your native tool
- how the package is architected internally
- how to adapt the workbench to local scientific datasets

```{toctree}
:maxdepth: 2
:caption: Getting Started

tutorial
first_day_student
load_first_lab_dataset
troubleshooting
api_usage
quality_control
changelog
pandas_ase
from_notebook_to_fair_dataset
```

```{toctree}
:maxdepth: 2
:caption: ASE-Focused Guide

ase_user_guide
ase_structures_in_dataframes
dataframe_schema
fair_and_provenance
vasp_charge_and_dos
xarray_vasp
ase_to_ui_workflow_mapping
recommended_analysis_views
```

```{toctree}
:maxdepth: 2
:caption: Package And Product Design

backend_overview
crawl_to_hdf_backend
bundled_hdf_backend_tutorial
function_inventory
artifact_policy
materials_workbench_design
column_review
logos
onepiece_studio_architecture
architecture_for_ase_catalysis
onepiece_backend_api
release_workflow
```

```{toctree}
:maxdepth: 2
:caption: Scientific Workflows And Examples

visualization_recipes
catalysis_hub_worked_example
cuga_worked_example
electrochemical_oer_tutorial
co2rr_methanol_reference_tutorial
published_dft_data_intake
image_columns
```

## First Look

Start the local demo:

```bash
onepiece-studio tutorial
```

Or open a local HDF file:

```bash
onepiece-studio hdf "/path/to/database.hdf" --key df --title "Local Database"
```

Run the bundled package self-test:

```bash
onepiece-studio qa
onepiece-studio doctor
```

The screenshots below were captured from the running OnePiece Studio UI.

```{image} _static/screenshots/records.png
:alt: OnePiece Studio records view
:class: screenshot
```

```{image} _static/screenshots/visualize.png
:alt: OnePiece Studio visualization view
:class: screenshot
```
