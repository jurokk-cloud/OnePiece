# created_frame.hdf analysis notebooks

This notebook series analyzes the `created_frame.hdf` table located at
`$ONEPIECE_DATA_ROOT/created_frame.hdf` (set `ONEPIECE_DATA_ROOT` to the
directory holding the file; it defaults to `data`). The notebooks use the local
`DFTDataFrame` package as the available OnePiece-compatible analysis layer,
discovered through the `DFTDATAFRAME_SRC` environment variable.

Notebooks:

1. `00_dataset_atlas_created_frame.ipynb`
2. `01_convergence_and_materials_taxonomy.ipynb`
3. `02_adsorbate_chemistry_and_reference_energies.ipynb`
4. `03_local_structure_descriptors_and_coordination.ipynb`
5. `04_reaction_pathways_and_copt_landscapes.ipynb`
6. `05_curated_methanol_reaction_path.ipynb`
7. `06_cu211_ga_methanol_mechanism_step_by_step.ipynb`

All plots are written as interactive notebook plots with `plt.show()`.
