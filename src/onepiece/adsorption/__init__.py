"""Adsorption analysis: formula parsing, reference assignment, and energy math.

The implementation lives in focused submodules; every public name remains
importable from ``onepiece.adsorption`` for backward compatibility.

- :mod:`onepiece.adsorption.formulas` -- formula/structure stoichiometry and
  adsorbate name detection
- :mod:`onepiece.adsorption.references` -- gas/surface reference assignment
  and OnePiece HDF source reading
- :mod:`onepiece.adsorption.energies` -- adsorption-energy math
- :mod:`onepiece.adsorption.copt` -- constrained-optimization path analysis
"""

from onepiece.adsorption.copt import (
    annotate_copt_paths,
    copt_barrier_summary,
    copt_profile_points,
    is_constrained_optimization,
)
from onepiece.adsorption.energies import (
    add_adsorption_energies,
    add_catalysis_hub_adsorption_energies,
    add_elemental_adsorption_energy,
    add_elemental_adsorption_free_energy,
    add_recipe_adsorption_energies,
    adsorption_view,
)
from onepiece.adsorption.formulas import (
    ADSORBATE_PATTERN,
    DEFAULT_ADSORBATE_TOKENS,
    FORMULA_PATTERN,
    NAME_COPT_PATTERN,
    add_element_count_columns,
    adsorbate_counts_from_structures,
    atom_counts,
    count_element,
    count_element_in_structure,
    formula_counts,
    get_all_elements,
    guess_adsorbate,
    primary_structure,
    row_element_count_map,
    row_elements,
    structure_columns_in_frame,
    surface_key_from_name,
)
from onepiece.adsorption.references import (
    DEFAULT_FORMULA_GAS_SPECIES,
    EQUATION_TOKEN_PATTERN,
    NON_METAL_REFERENCE_ELEMENTS,
    GasReferences,
    annotate_adsorbates,
    assign_references_before_merge,
    assign_surface_references,
    choose_surface_references,
    default_room_temperature_phase,
    infer_adsorbate_recipe,
    infer_adsorption_recipes,
    infer_reference_equation_from_formula,
    parse_reference_equation,
    read_onepiece_hdf,
    read_onepiece_hdfs,
)

__all__ = [
    "ADSORBATE_PATTERN",
    "DEFAULT_ADSORBATE_TOKENS",
    "DEFAULT_FORMULA_GAS_SPECIES",
    "EQUATION_TOKEN_PATTERN",
    "FORMULA_PATTERN",
    "GasReferences",
    "NAME_COPT_PATTERN",
    "NON_METAL_REFERENCE_ELEMENTS",
    "add_adsorption_energies",
    "add_catalysis_hub_adsorption_energies",
    "add_element_count_columns",
    "add_elemental_adsorption_energy",
    "add_elemental_adsorption_free_energy",
    "add_recipe_adsorption_energies",
    "adsorbate_counts_from_structures",
    "adsorption_view",
    "annotate_adsorbates",
    "annotate_copt_paths",
    "assign_references_before_merge",
    "assign_surface_references",
    "atom_counts",
    "choose_surface_references",
    "copt_barrier_summary",
    "copt_profile_points",
    "count_element",
    "count_element_in_structure",
    "default_room_temperature_phase",
    "formula_counts",
    "get_all_elements",
    "guess_adsorbate",
    "infer_adsorbate_recipe",
    "infer_adsorption_recipes",
    "infer_reference_equation_from_formula",
    "is_constrained_optimization",
    "parse_reference_equation",
    "primary_structure",
    "read_onepiece_hdf",
    "read_onepiece_hdfs",
    "row_element_count_map",
    "row_elements",
    "structure_columns_in_frame",
    "surface_key_from_name",
]
