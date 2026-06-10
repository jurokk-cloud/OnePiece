# onepiece-studio Documentation

`onepiece-studio` is a local scientific database workbench for computational
chemistry and materials science.

It combines:

- `onepiece`: a backend engine for scientific `pandas.DataFrame` workflows
- `onepiece_studio`: a local UI for search, filtering, visualization, project
  state, and structure inspection

The package is designed for local HDF datasets, ASE structures, adsorption
workflows, reaction-path analysis, and reproducible scientific curation.

## Quick Launch

```bash
pip install onepiece-studio
onepiece-studio
```

The welcome page lets you open the bundled tutorial dataset, a local HDF
file, or a recent file. To jump straight into the tutorial dataset:

```bash
onepiece-studio tutorial
```

## Choose Your Path

The documentation is organized into three tracks. Pick the one that matches
how you want to work today.

### I have a dataset — show me

You have an HDF file (or want to try the bundled one) and want to explore it
in the app without writing code. Start with the
[tutorial](tutorial.md), then load
[your own lab dataset](load_first_lab_dataset.md).

```{toctree}
:maxdepth: 2
:caption: "Use the App (UI Track)"

tutorial
load_first_lab_dataset
image_columns
recommended_analysis_views
quality_control
troubleshooting
```

### I write notebooks

You work in Python — pandas, ASE, maybe xarray — and want the `onepiece`
backend as a library, with the UI as an optional companion. Start with
[API and CLI usage](api_usage.md).

```{toctree}
:maxdepth: 2
:caption: "Work in Python (Notebook Track)"

api_usage
pandas_ase
ase_user_guide
ase_structures_in_dataframes
ase_to_ui_workflow_mapping
vasp_charge_and_dos
xarray_vasp
visualization_recipes
```

### I'm starting my thesis

You just joined a computational chemistry or catalysis group and want the
concepts, worked examples, and project background — not just tool commands.
Start with the [first day guide](first_day_student.md), then walk through the
worked examples.

```{toctree}
:maxdepth: 2
:caption: "Learn the Concepts (Thesis Track)"

first_day_student
catalysis_hub_worked_example
cuga_worked_example
materials_workbench_design
column_review
onepiece_studio_architecture
onepiece_backend_api
release_workflow
logos
changelog
```

## First Look

The screenshots below were captured from the running OnePiece Studio UI.

```{image} _static/screenshots/records.png
:alt: OnePiece Studio records view
:class: screenshot
```

```{image} _static/screenshots/visualize.png
:alt: OnePiece Studio visualization view
:class: screenshot
```
