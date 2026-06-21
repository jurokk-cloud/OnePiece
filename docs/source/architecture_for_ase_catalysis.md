# Architecture For ASE-Based Catalysis Workflows

This page explains the `onepiece` architecture for readers who already work
comfortably with ASE, pandas, and computational heterogeneous catalysis data.
The intended audience is a data analyst or computational chemist who already
thinks in terms of `Atoms`, slabs, adsorbates, gas references, VASP output
folders, thermodynamic corrections, and dataframe-based post-processing.

## Core Interpretation

`onepiece` is best understood as a dataframe-first catalysis analysis backend
wrapped around ASE objects.

The central abstraction is not a custom `Calculation` class or a database ORM.
It is a `pandas.DataFrame` where:

- each row is one calculation, structure, gas reference, surface, adsorbate,
  pathway image, or Catalysis-Hub-like reaction row
- ASE `Atoms` objects live in structure columns such as `struc`, `CONTCAR`,
  `structure`, or `atoms`
- derived physical quantities are added as new columns
- the UI and workflow engine mostly orchestrate dataframe transformations

This matches how many computational catalysis projects actually work. One table
becomes the lab notebook, the metadata index, and the analysis object.

## Package Flow

The package is organized around a practical scientific pipeline:

```text
DFT folders / HDF / parquet
        |
        v
source readers + crawler
        |
        v
canonical Name-indexed DataFrame
        |
        v
ASE structure descriptors + VASP electronic descriptors
        |
        v
thermochemistry + adsorption/reference bookkeeping
        |
        v
phase diagrams, reaction paths, filters, UI, reports
```

The backend package, `onepiece`, owns the scientific operations. The frontend
package, `onepiece_studio`, owns Streamlit layout, session state, and rendering.
That split is important: the UI should collect intent and display results, while
the backend remains scriptable from notebooks, tests, and batch workflows.

## Major Backend Responsibilities

### Ingestion

`onepiece.dftdataframe_import` is the ingestion layer. It crawls calculation
folders, finds files such as `final.traj`, `CONTCAR`, `OUTCAR`, `POSCAR`,
`CHGCAR`, `DOSCAR`, and `ACF.dat`, reads structures with ASE, parses
thermochemistry files, and builds the starting dataframe.

Chemically, this is the raw feed preparation stage: many heterogeneous
calculation folders are converted into one analyzable stream.

### VASP Electronic Structure

`onepiece.vasp` handles VASP-specific electronic-structure data. It reads Bader
`ACF.dat`, `CHGCAR`, and `DOSCAR` files, then derives charge, magnetic-moment,
and projected-DOS descriptors.

For catalysis, this layer connects electronic structure to adsorbate binding:
charge transfer, spin state, projected d-band descriptors, oxidation-state
proxies, and local electronic fingerprints.

### ASE Structure Analysis

`onepiece.ase_analysis` contains geometry and local-environment descriptors. It
computes coordination environments, generalized coordination numbers, layer
labels, vacuum thickness, slab thickness, adsorption geometry, and structural
quality checks.

For an ASE user, this is the most familiar layer: ASE `Atoms` remains the
structure authority, and OnePiece adds project-wide descriptor generation.

### Adsorption References And Energies

`onepiece.adsorption` handles clean-surface matching, gas references, adsorbate
labels, formula-derived recipes, and adsorption energies.

The basic thermodynamic bookkeeping is:

```text
E_ads = E(slab + adsorbate) - E(clean slab) - sum_i nu_i E(reference_i)
```

This is the layer that makes a dataframe useful for CO2 reduction, OER
intermediates, methanol synthesis intermediates, oxide surfaces, perovskites, or
Cu/ZnO-style structure-activity analysis.

### Thermochemistry

`onepiece.thermo` handles gas-phase and adsorbate/surface Gibbs free energies.
Gas rows include translational, rotational, and vibrational terms. Adsorbate and
surface rows use the harmonic adsorbate approximation, where translation and
rotation are removed and vibrational terms are retained.

The practical model is:

```text
G_gas = E_DFT + ZPE + H_trans/rot/vib - T S_trans/rot/vib
G_ads = E_DFT + ZPE + H_vib - T S_vib
```

This is a useful first-pass treatment before adding solvent, electric field,
coverage, configurational entropy, pH, potential, or microkinetic corrections.

### Phase Diagrams

`onepiece.phase_diagrams` uses symbolic expressions and numeric scans to identify
stable phases as functions of variables such as temperature, pressure, or
chemical potential.

This is especially relevant for oxide catalysis. For MnVO, CuVO, perovskite
surfaces, hydroxylated terminations, oxygen vacancies, and reconstructed
surfaces, the active phase is often a function of oxygen chemical potential,
water pressure, pH, potential, and temperature rather than a fixed structure.

### Storage

`onepiece.storage` moves a project from notebook state into a managed dataset
layout: a manifest plus parquet or HDF tables, with object sidecars for columns
that contain ASE `Atoms`.

This is a practical compromise. Plain parquet is useful for tabular data, but it
cannot naturally preserve ASE objects.

## Scientific Strengths

The architecture is strong because it follows how computational catalysis data
is actually analyzed:

- ASE remains the structure model.
- pandas remains the analysis surface.
- each operation adds interpretable columns.
- reference matching is explicit enough to be tested.
- VASP-specific file parsing is isolated from UI code.
- the Streamlit app is a workbench over backend operations, not the source of
  scientific truth.

This makes the package usable from a notebook, a script, a saved workflow, or
the local UI.

## Main Architectural Risks

The current complexity centers are natural, but they should be watched:

- `dftdataframe_import.py` combines discovery, parsing, caching, enrichment, and
  HDF writing.
- `vasp.py` combines raw file parsers and scientific descriptors.
- `ase_analysis.py` combines geometry descriptors and plotting.
- `workflows.engine` is a dispatcher that can grow into a large central module.
- string-based adsorbate inference can silently misclassify systems if names are
  inconsistent.

These are not rewrite-level problems. They are normal for a maturing scientific
package. The important point is to keep raw parsing, physical modeling, and UI
orchestration from collapsing into the same layer.

## Reference Chemistry Matters

For adsorption thermodynamics, OnePiece is aligned with practical catalysis
screening. For example, methanol synthesis and CO2 reduction workflows need
consistent references for species such as `CO2`, `CO`, `H2`, `H2O`, `CH3OH`,
`HCOO`, `HCO`, `H2CO`, and `CH3O`.

For OER, the reference convention needs even more care:

```text
* + H2O -> OH* + H+ + e-
OH* -> O* + H+ + e-
O* + H2O -> OOH* + H+ + e-
OOH* -> * + O2 + H+ + e-
```

That means future reference schemes should carry metadata for:

- gas-phase thermochemical references
- computational hydrogen electrode assumptions
- explicit `H2`/`H2O` reference bases
- pH corrections
- electrode-potential corrections
- oxygen chemical potential
- coverage and configurational entropy corrections
- optional solvation corrections

The reference basis is part of the result. Two adsorption-energy columns are not
scientifically comparable unless their reference convention and corrections are
known.

## Recommended Evolution

The next improvements should harden boundaries rather than rewrite the package.

Split ingestion into smaller layers:

```text
discovery.py       folder crawling and marker detection
structure_io.py    ASE structure reading
thermo_io.py       out.txt / entropy parsing
electronic_io.py   CHGCAR/DOSCAR/ACF enrichment orchestration
crawler.py         high-level crawl_root_to_frame API
```

Split VASP handling into raw parsers and descriptors:

```text
vasp/acf.py
vasp/chgcar.py
vasp/doscar.py
vasp/charges.py
vasp/magnetism.py
vasp/pdos_descriptors.py
```

Move plotting out of `ase_analysis.py` into a plotting namespace. Geometry
functions should remain usable on clusters and in headless batch workflows.

Make reference schemes first-class objects:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ReferenceScheme:
    name: str
    species_energies: dict[str, float]
    chemical_potentials: dict[str, float]
    corrections: dict[str, float]
    convention: str
```

Document the dataframe schema. Columns such as `Name`, `E`, `Formula`, `Path`,
`struc`, `surface_ref_E`, `adsorbate`, `record_class`, and `fmax` are part of
the implicit API. A dataframe-first package scales only when that column contract
is explicit.

Prefer structure-based adsorbate detection when clean references exist.
Name-based heuristics are useful, but systems such as `CO`, `CO2`, `OH`, `OOH`,
`HCOO`, `HCOOH`, and `CH3O` are easy to misclassify if naming conventions drift.

## Bottom Line

OnePiece formalizes a workflow many computational catalysis groups already use
with ASE and pandas. Its scientific center is a canonical dataframe with ASE
structures plus derived thermodynamic, geometric, and electronic descriptors.

The architecture is strongest when:

- raw file parsing is separate from scientific descriptors
- reference chemistry is explicit and metadata-carrying
- plotting is separate from numerical analysis
- the dataframe schema is documented
- name heuristics are supplemented by structure-based logic

That direction makes the package suitable for serious OER, CO2 reduction,
oxide-surface, perovskite, and methanol-synthesis datasets where the difference
between a convenient dataframe and publishable thermodynamics is the reference
convention and the provenance of every correction.
