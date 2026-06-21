# Backend Function Inventory

This page is generated from the current backend source tree. It is useful when
you want to understand which module owns which operation.

## Source-Derived Function Map

```{image} _static/onepiece_function_map.svg
:alt: Source-derived OnePiece backend function map
```

## How To Read The Map

Color meaning:

- red: exported top-level API
- blue: public module-level function
- purple: class
- teal: method
- gray: private helper

The map is intentionally grouped by package/module rather than by call graph.
For backend maintenance this is usually more useful: it shows ownership,
surface area, and where new functionality should probably live.

## Full Text Inventory

The full machine-generated inventory is stored at:

```text
docs/source/_static/onepiece_function_inventory.md
```

Open it directly when you need exact function names without visual truncation.

## Practical Interpretation

For day-to-day use, focus on these module groups:

| Area | Use it for |
|---|---|
| `sources` | reading HDF files, upload handling, source fingerprints |
| `dftdataframe_import` | crawling calculation folders into dataframe/HDF form |
| `adsorption` | adsorption energies, references, formula bookkeeping |
| `thermo` | Gibbs/free-energy corrections |
| `vasp` | charge, magnetic moment, DOS, VASP-file descriptors |
| `ase_analysis` | ASE-structure descriptors and geometry analysis |
| `workflows` | repeatable dataframe operations and audit logs |
| `services` | UI/query-facing dataframe filtering |
| `storage` | managed dataset save/load |
| `provenance` | FAIR/AiiDA-like provenance records and reference schemes |
| `qa` | package and FAIR self-tests |

If a new function changes scientific meaning, it should normally live in
`adsorption`, `thermo`, `vasp`, or `ase_analysis`.

If a new function changes how the UI manipulates a dataframe, it should normally
live in `workflows` or `services`, not inside Streamlit widget code.
