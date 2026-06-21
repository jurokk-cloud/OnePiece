# FAIR Data And Provenance

OnePiece is designed for computational chemistry groups that already work with
ASE, pandas, VASP outputs, HDF files, and local project folders. The goal is not
to hide that workflow. The goal is to make it auditable.

For a catalysis dataset, the scientific result is not only a number such as
`E_ads = -0.72 eV`. The result is the full chain:

- which structure was used
- which clean surface reference was matched
- which gas or electrochemical reference convention was used
- which DFT output files were parsed
- which thermochemical corrections were applied
- which workflow operation created each derived column
- which software version produced the table

This is the practical meaning of FAIR for OnePiece.

## FAIR Mapping

### Findable

OnePiece datasets should have stable identifiers and manifests:

- `dataset_id`
- `manifest.json`
- source paths
- row names
- source rows
- checksums for input files when possible
- project source fingerprints with size, modification time, format, and checksum

This lets a group find the exact table behind a figure, not just a similar HDF
file with the same name.

### Accessible

OnePiece stores managed datasets as local, inspectable files:

- parquet or HDF table
- JSON manifest
- optional object sidecar for ASE `Atoms` or other Python objects

The access model is intentionally local-first. A group can keep unpublished
data on a workstation or cluster, while still preserving enough metadata for
later publication.

### Interoperable

The package keeps the main analysis table in common Python/scientific formats:

- pandas `DataFrame`
- ASE `Atoms`
- parquet/HDF
- xarray for CHGCAR and DOSCAR-style dense arrays
- JSON manifests for metadata and provenance

This makes OnePiece compatible with existing notebooks, ASE scripts, plotting
tools, and later export layers such as NOMAD, Materials Project-style records,
RO-Crate, PROV-O, or AiiDA-adjacent workflows.

### Reusable

Reusable computational catalysis data needs more than coordinates and energies.
For adsorption, OER, CO2 reduction, or methanol synthesis, reusability requires
the reference convention:

- gas-phase reference energies
- computational hydrogen electrode assumptions
- pH and potential corrections when used
- oxygen or water chemical-potential model
- surface reference identity
- thermochemical correction source
- software and parser versions

OnePiece should therefore store reference schemes and workflow parameters as
metadata, not as hidden notebook context.

## Relationship To AiiDA

[AiiDA](https://aiida.net) is a full workflow management system and provenance
engine. Its public positioning is "FAIR by design": every input, calculation,
and output is tracked automatically in a provenance graph.

OnePiece is intentionally lighter:

- it does not replace AiiDA's database or daemon
- it does not claim every DFT calculation was launched by OnePiece
- it focuses on local post-processing, curation, dataframe analysis, and UI
  workflows

The architectural target is AiiDA-compatible thinking:

```text
entity: raw OUTCAR / final.traj / HDF / parquet table
activity: crawl, parse, assign references, add Gibbs free energy, add E_ads
agent: OnePiece version, Python runtime, user or group
entity: derived managed dataset / figure table / report
```

This gives OnePiece a provenance spine without forcing every group to migrate
its production calculations into a new workflow engine.

## Catalysis Example

For CO2 reduction or methanol chemistry on Cu/ZnO, a reusable adsorption-energy
row should make the following clear:

```text
adsorbate state: HCOO*
surface reference: clean Cu/ZnO termination
reaction/reference basis: CO2 + 1/2 H2 -> HCOO*
DFT energy source: final.traj / OUTCAR
thermochemistry source: out.txt or vibrational analysis
derived quantity: adsorption_energy
operation: add_recipe_adsorption_energies
software: onepiece version
```

For OER on MnVO or CuVO, the same principle applies, but the electrochemical
reference scheme must also be explicit:

```text
OH*, O*, OOH*
H2O/H2 computational hydrogen electrode basis
pH correction
electrode potential correction
oxygen chemical-potential convention
surface oxidation state / termination
```

If those assumptions are not recorded, the numbers may be useful inside one
notebook but are not fully reusable.

## Current OnePiece Contract

Managed OnePiece datasets use a manifest with:

- storage format
- primary key
- table file
- object sidecar file
- source path
- row and column counts
- object columns
- generic metadata
- provenance payload

The provenance payload is JSON-native and follows a compact entity/activity/agent
model. It can later be translated to richer formats, but it is already useful for
auditing local datasets.

Workflow execution also returns an audit log. Each enabled operation becomes an
activity record with:

- input dataframe entity
- output dataframe entity
- operation kind
- operation parameters
- row and column counts before and after
- added and removed columns
- success or failure status

For example, a `derive_recipe_adsorption` step should be traceable as the
activity that created adsorption-energy columns from a specific reference table
and clean-surface assignment.

Project source descriptors also carry local fingerprints for path-backed
sources. When a project is restored, OnePiece reloads the source path and can
warn if the file checksum changed since the project was saved. This matters for
HDF files that are overwritten during an active thesis project.

## Reference Scheme Metadata

For catalysis, the most important provenance object is often the reference
scheme. OnePiece datasets should record it explicitly in `metadata` or in the
workflow operation parameters.

Recommended fields:

```python
from onepiece.provenance import ReferenceScheme

scheme = ReferenceScheme.computational_hydrogen_electrode(
    name="CHE_H2_H2O",
    h2_eV=-6.77,
    h2o_eV=-14.22,
    potential_V_RHE=1.23,
    pH=14,
    corrections_eV={
        "OH_solvation": -0.30,
        "OOH_solvation": -0.35,
    },
    metadata={
        "notes": "Use one consistent setup for MnVO OER screening.",
    },
)
```

For methanol synthesis or CO2 reduction on Cu/ZnO, perovskites, or oxide
surfaces, the same field can describe a gas-phase basis:

```python
scheme = ReferenceScheme.gas_phase(
    name="CO2_H2_H2O_CH3OH",
    gas_references_eV={
        "CO2": -22.1,
        "H2": -6.8,
        "H2O": -14.2,
        "CH3OH": -29.5,
    },
    temperature_K=523.15,
    pressure_bar={
        "CO2": 30,
        "H2": 90,
        "H2O": 1,
        "CH3OH": 1,
    },
)
```

The exact numbers are project-specific. The software requirement is that the
choice is recorded. Without that, adsorption energies from OER, CO2RR, and
methanol-conversion datasets cannot be compared responsibly.

## Validation And Graph Export

Before sharing a dataset inside a group or attaching it to a manuscript, validate
the manifest provenance:

```bash
onepiece-studio fair-audit .onepiece/workspace/mnvo_oer_surface_screening \
  --require-reference-scheme \
  --require-publication-metadata
```

The same audit is available from Python:

```python
from onepiece.qa import run_fair_provenance_audit

result = run_fair_provenance_audit(
    ".onepiece/workspace/mnvo_oer_surface_screening",
    require_reference_scheme=True,
    require_publication_metadata=True,
)
```

`--require-publication-metadata` requires `manifest.metadata["license"]`
and `manifest.metadata["citation"]`. It also warns when common reusable
dataset fields such as `creators`, `description`, and `doi` are absent.

For lower-level inspection, validate the raw manifest provenance:

```python
from onepiece.provenance import validate_provenance_payload
from onepiece.storage import read_dataset_manifest

manifest = read_dataset_manifest(".onepiece/workspace/mnvo_oer_surface_screening/manifest.json")
result = validate_provenance_payload(
    manifest.provenance,
    require_reference_scheme=True,
)

if not result.passed:
    raise ValueError(result.errors)
```

For visualization or export, convert the same payload into a compact graph:

```python
from onepiece.provenance import provenance_graph, ro_crate_metadata

graph = provenance_graph(manifest.provenance)
crate = ro_crate_metadata(
    manifest.provenance,
    name="MnVO OER surface screening",
)
```

The graph contains:

- entity nodes for source files and managed datasets
- activity nodes for save/workflow operations
- agent nodes for software/runtime actors
- `used`, `generated`, and `wasAssociatedWith` edges

This is not an AiiDA database export, but it makes the OnePiece manifest easier
to translate later into PROV-O, RO-Crate, or an AiiDA-adjacent archive.

`ro_crate_metadata(...)` returns an RO-Crate-style JSON-LD metadata document.
It maps OnePiece entities to `Dataset` or `File` nodes, workflow activities to
`CreateAction` nodes, and software/runtime agents to `SoftwareApplication`
nodes. It is intended as an interoperability bridge, not as a full archival
package writer.

The same export is available from the command line:

```bash
onepiece-studio ro-crate .onepiece/workspace/mnvo_oer_surface_screening \
  --output ro-crate-metadata.json \
  --name "MnVO OER surface screening"
```

## Recommended Practice

When saving a dataset, include domain metadata:

```python
from onepiece.provenance import ReferenceScheme
from onepiece.storage import resolve_storage_config, save_dataset

config = resolve_storage_config(".onepiece")
reference_scheme = ReferenceScheme.computational_hydrogen_electrode(
    h2_eV=-6.77,
    h2o_eV=-14.22,
    potential_V_RHE=1.23,
    pH=14,
)

save_dataset(
    frame,
    dataset_id="mnvo_oer_surface_screening",
    config=config,
    source_path="raw/mnvo_created_frame.hdf",
    reference_scheme=reference_scheme,
    metadata={
        "project": "MnVO OER",
        "dft_code": "VASP",
        "exchange_correlation": "PBE+U",
        "surface_family": "MnVO",
        "license": "CC-BY-4.0",
        "citation": "Your group dataset citation or manuscript reference.",
    },
)
```

When saving a dataframe produced by the workflow engine, include the audit log:

```python
from onepiece.storage import save_dataset
from onepiece.workflows import apply_operations

workflow = apply_operations(frame, operations)

save_dataset(
    workflow.dataframe,
    dataset_id="mnvo_oer_derived",
    config=config,
    reference_scheme=reference_scheme,
    workflow_audit_log=workflow.audit_log,
)
```

The manifest then contains both the dataset save activity and the dataframe
operations that created derived columns.

For publication-grade datasets, add:

- DOI or internal dataset identifier
- license
- citation
- DFT code version
- pseudopotential set
- Hubbard U values
- reference-energy table
- workflow operation list
- checksums for source files

That is the minimum standard for OnePiece to look credible to a chemist who
cares about physical meaning, and to a data steward who cares about FAIR reuse.
