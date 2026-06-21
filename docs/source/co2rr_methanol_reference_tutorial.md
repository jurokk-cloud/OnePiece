# CO2 Reduction And Methanol Reference Tutorial

This tutorial describes reference bookkeeping for CO2 reduction and methanol
synthesis style workflows in OnePiece.

The target systems are datasets with intermediates such as:

```text
CO2*, COOH*, HCOO*, CO*, CHO*, HCO*, H2CO*, CH3O*, CH3OH*
```

The same structure applies to perovskites, oxide surfaces, Cu/Ga surfaces,
Cu/ZnO interfaces, and other heterogeneous catalysts.

## Why Reference Metadata Matters

The value:

```text
adsorption_energy = -0.72 eV
```

is incomplete unless the dataset also records:

- clean-surface reference
- gas reference energies
- electrochemical convention, if any
- thermochemical corrections
- temperature and pressure assumptions
- whether energies are electronic `E` or free energies `G`

OnePiece stores this information with `ReferenceScheme`.

## Gas-Phase Reference Scheme

For thermochemical methanol or CO2 conversion analysis:

```python
from onepiece import ReferenceScheme

scheme = ReferenceScheme.gas_phase(
    name="CO2_H2_H2O_CH3OH_523K",
    gas_references_eV={
        "CO2": -22.10,
        "CO": -14.80,
        "H2": -6.80,
        "H2O": -14.20,
        "CH3OH": -29.50,
    },
    temperature_K=523.15,
    pressure_bar={"CO2": 30.0, "H2": 90.0, "CH3OH": 1.0, "H2O": 1.0},
    corrections_eV={
        "gas_thermo_source": 0.0,
    },
    metadata={
        "reaction_family": "CO2 hydrogenation to methanol",
        "reference_note": "Example numbers; replace with project-consistent DFT and thermo values.",
    },
)
```

## Example Adsorption Reactions

Useful reactions include:

```text
* + CO2(g) -> CO2*
* + CO(g) -> CO*
* + CH3OH(g) -> CH3O* + 1/2 H2(g)
* + H2O(g) -> OH* + 1/2 H2(g)
```

For methoxy from methanol:

```text
dE = E(CH3O*) + 1/2 E(H2) - E(*) - E(CH3OH)
```

OnePiece has built-in support for the common CO and methoxy examples:

```python
from onepiece.adsorption import assign_surface_references, add_adsorption_energies

frame = assign_surface_references(frame)
frame = add_adsorption_energies(
    frame,
    {
        "CO": scheme.gas_references_eV["CO"],
        "H2": scheme.gas_references_eV["H2"],
        "CH3OH": scheme.gas_references_eV["CH3OH"],
    },
)
```

For broader CO2RR intermediates, prefer recipe-based reference equations:

```python
from onepiece.adsorption import add_recipe_adsorption_energies

recipes = {
    "CO2": {"basis": "C", "gas_refs": {"CO2": 1.0}},
    "COOH": {"basis": "C", "gas_refs": {"CO2": 1.0, "H2": 0.5}},
    "HCOO": {"basis": "C", "gas_refs": {"CO2": 1.0, "H2": 0.5}},
    "CO": {"basis": "C", "gas_refs": {"CO": 1.0}},
    "CH3O": {"basis": "C", "gas_refs": {"CH3OH": 1.0, "H2": -0.5}},
}

frame = add_recipe_adsorption_energies(
    frame,
    scheme.gas_references_eV,
    recipes,
)
```

The sign convention is the OnePiece adsorption convention:

```text
E_ads,total = E(row) - E(surface_ref) - n_basis * sum_i coeff_i E(gas_i)
```

## Electrochemical Variant

For CO2 reduction under electrochemical conditions, create a CHE scheme:

```python
che = ReferenceScheme.computational_hydrogen_electrode(
    name="CO2RR_CHE_RHE",
    h2_eV=-6.80,
    h2o_eV=-14.20,
    potential_V_RHE=-0.60,
    pH=7,
    corrections_eV={
        "COOH_solvation": -0.25,
        "HCOO_solvation": -0.20,
    },
)
```

Do not mix gas-phase thermochemical columns and CHE columns under the same
generic name. Prefer explicit names such as:

```text
dG_COOH_CHE_eV
dG_HCOO_CHE_eV
E_ads_CO_gasref_eV
```

## Save And Export

```python
from onepiece import save_dataset, ro_crate_metadata
from onepiece.storage import ensure_storage_layout, read_dataset_manifest, resolve_storage_config

config = ensure_storage_layout(resolve_storage_config(".onepiece"))
manifest_path = save_dataset(
    frame,
    dataset_id="co2rr-methanol-reference-example",
    config=config,
    reference_scheme=scheme,
    metadata={
        "license": "CC-BY-4.0",
        "citation": "Replace with article or dataset citation.",
    },
)

manifest = read_dataset_manifest(manifest_path)
crate = ro_crate_metadata(manifest.provenance, name="CO2RR methanol reference example")
```

Use the command line for the same export:

```bash
onepiece-studio ro-crate .onepiece/workspace/co2rr-methanol-reference-example
```

## Physical Checks

Before using trends:

- confirm each adsorbate has the intended clean reference
- separate electronic energies from free energies
- keep gas references from the same functional and pseudopotential setup when possible
- record literature-derived corrections explicitly
- do not compare gas-phase and CHE reference columns directly
- inspect outliers with ASE structures before interpreting volcano plots

