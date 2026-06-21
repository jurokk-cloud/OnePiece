from __future__ import annotations

import numpy as np
import pandas as pd
from ase import Atoms
from ase.build import bulk

from onepiece import apply_operation
from onepiece.ase_analysis import (
    DoscarData,
    add_ase_analysis_descriptors,
    adsorbate_orientation_angle,
    adsorbate_surface_distance_summary,
    classify_adsorption_site,
    compare_structures_rmsd,
    compute_d_band_center,
    compute_d_band_filling,
    CoordinationEnvironment,
    coordination_environment,
    coordination_numbers,
    detect_adsorbate_desorption,
    detect_adsorbate_dissociation,
    detect_overlapping_atoms,
    detect_unphysical_bonds,
    generalized_coordination_numbers,
    plot_structure_value_3d,
    identify_surface_atom_indices,
    infer_atomic_layers,
    reaction_path_geometry_summary,
    slab_thickness,
    summarize_charge_transfer_by_layer,
    surface_reconstruction_metrics,
    vacuum_thickness,
)


def _surface() -> Atoms:
    return Atoms(
        "Cu4",
        positions=[
            (0.0, 0.0, 0.0),
            (2.5, 0.0, 0.0),
            (0.0, 0.0, 2.0),
            (2.5, 2.5, 2.0),
        ],
        cell=[8.0, 8.0, 12.0],
        pbc=[False, False, False],
    )


def _adsorbed() -> Atoms:
    slab = _surface().copy()
    adsorbate = Atoms(
        "CO",
        positions=[
            (0.0, 0.0, 3.15),
            (0.0, 0.0, 4.30),
        ],
        cell=slab.cell,
        pbc=slab.pbc,
    )
    return slab + adsorbate


def test_layer_coordination_and_site_descriptors() -> None:
    slab = _surface()
    ads = _adsorbed()

    layers = infer_atomic_layers(slab)
    assert layers.tolist() == [0, 0, 1, 1]
    assert identify_surface_atom_indices(slab) == [2, 3]
    assert np.isclose(slab_thickness(slab), 2.0)
    assert np.isclose(vacuum_thickness(slab), 10.0)

    coordination = coordination_numbers(slab)
    gcn = generalized_coordination_numbers(slab, max_coordination=4.0)
    assert coordination.shape == (4,)
    assert np.all(coordination > 0)
    assert np.all(gcn >= 0.0)

    distance_summary = adsorbate_surface_distance_summary(ads, slab)
    assert distance_summary["adsorbate_surface_bond_count"] >= 1.0
    assert distance_summary["min_adsorbate_surface_distance"] < 1.3
    assert classify_adsorption_site(ads, slab) == "top"
    assert np.isclose(adsorbate_orientation_angle(ads, slab), 0.0)


def test_coordination_environment_reuses_packed_graph_for_large_clusters() -> None:
    cluster = bulk("Cu", "fcc", a=3.6, cubic=True).repeat((3, 3, 3))
    cluster.pbc = False
    cluster.cell = cluster.cell * 1.5

    environment = coordination_environment(cluster)

    assert isinstance(environment, CoordinationEnvironment)
    assert environment.natoms == len(cluster)
    assert environment.indptr.shape == (len(cluster) + 1,)
    assert environment.indices.ndim == 1
    assert environment.coordination.shape == (len(cluster),)
    assert environment.indices.dtype == np.int32
    assert environment.coordination.dtype == np.int32

    coordination_from_environment = coordination_numbers(environment)
    coordination_from_atoms = coordination_numbers(cluster)
    gcn_from_environment = generalized_coordination_numbers(environment)
    gcn_from_atoms = generalized_coordination_numbers(cluster)

    np.testing.assert_allclose(coordination_from_environment, coordination_from_atoms)
    np.testing.assert_allclose(gcn_from_environment, gcn_from_atoms)
    assert np.isfinite(gcn_from_environment).all()
    assert float(np.mean(coordination_from_environment)) > 0.0


def test_structure_comparison_reconstruction_and_path_summary() -> None:
    slab = _surface()
    moved = slab.copy()
    moved.positions[2, 0] += 0.2
    ads = moved + Atoms("CO", positions=[(0.0, 0.0, 3.15), (0.0, 0.0, 4.30)], cell=slab.cell, pbc=slab.pbc)

    rmsd = compare_structures_rmsd(slab, moved)
    reconstruction = surface_reconstruction_metrics(ads, slab)
    path = reaction_path_geometry_summary([_adsorbed(), ads], surface_reference=slab)

    assert rmsd > 0.0
    assert reconstruction["surface_reconstruction_rmsd"] > 0.0
    assert reconstruction["surface_reconstruction_max_displacement"] >= reconstruction["surface_reconstruction_rmsd"]
    assert path["path_image_count"] == 2.0
    assert path["path_max_rmsd_from_initial"] > 0.0


def test_dissociation_desorption_and_qc_flags() -> None:
    slab = _surface()
    dissociated = slab + Atoms(
        "H2",
        positions=[(4.5, 4.5, 6.0), (6.5, 6.5, 6.0)],
        cell=slab.cell,
        pbc=slab.pbc,
    )
    broken = Atoms("H2", positions=[(0.0, 0.0, 0.0), (0.1, 0.0, 0.0)], cell=[8.0, 8.0, 8.0], pbc=False)

    dissociation = detect_adsorbate_dissociation(dissociated, slab)
    assert dissociation["adsorbate_is_dissociated"] is True
    assert dissociation["adsorbate_fragment_count"] == 2.0
    assert detect_adsorbate_desorption(dissociated, slab) is True

    overlap = detect_overlapping_atoms(broken)
    unphysical = detect_unphysical_bonds(broken)
    assert overlap["has_overlapping_atoms"] is True
    assert unphysical["has_unphysical_bonds"] is True


def test_d_band_and_charge_layer_summaries() -> None:
    energies = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    signal = np.array([0.0, 1.0, 2.0, 1.0, 0.0])
    site_dos = np.stack([signal, signal, signal, signal, signal], axis=0)[np.newaxis, :, :]
    doscar = DoscarData(
        energies=energies,
        total_dos=np.array([signal]),
        integrated_total_dos=np.array([np.cumsum(signal)]),
        site_dos=site_dos,
        efermi=0.0,
        source_path="synthetic",
        orbital_columns={"dxy": 0, "dyz": 1, "dz2": 2, "dxz": 3, "dx2": 4},
    )

    center = compute_d_band_center(doscar)
    filling = compute_d_band_filling(doscar)
    layer_summary = summarize_charge_transfer_by_layer(_surface(), [0.1, 0.2, -0.1, -0.2])

    assert np.isclose(center, 0.0)
    assert 0.0 < filling < 1.0
    assert np.isclose(layer_summary["top_layer_charge_sum_e"], -0.3)
    assert np.isclose(layer_summary["bottom_layer_charge_sum_e"], 0.3)


def test_dataframe_descriptor_workbench_and_workflow_operation() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Cu-211-clean", "Cu-211-clean-CO-1"],
            "struc": [_surface(), _adsorbed()],
            "Path": ["/tmp/clean", "/tmp/ads"],
            "E": [-10.0, -12.5],
            "atomic_charges": [[0.0, 0.0, 0.0, 0.0], [0.1, 0.0, -0.1, 0.0, 0.3, -0.3]],
        }
    )

    result = add_ase_analysis_descriptors(frame)
    row = result.loc[result["Name"] == "Cu-211-clean-CO-1"].iloc[0]
    assert row["adsorption_site"] == "top"
    assert bool(row["adsorbate_desorbed"]) is False
    assert bool(row["adsorbate_is_dissociated"]) is False
    assert row["surface_reconstruction_rmsd"] >= 0.0
    assert np.isfinite(row["mean_coordination"])

    workflow = apply_operation(
        frame,
        {
            "kind": "derive_ase_analysis_descriptors",
            "structure_column": "struc",
            "calculation_path_column": "Path",
            "include_pdos": False,
        },
    )
    workflow_row = workflow.loc[workflow["Name"] == "Cu-211-clean-CO-1"].iloc[0]
    assert workflow_row["adsorption_site"] == "top"


def test_plot_structure_value_3d_returns_figure_for_gcn_values() -> None:
    cluster = bulk("Cu", "fcc", a=3.6, cubic=True)
    cluster.pbc = False
    values = generalized_coordination_numbers(cluster)

    fig, ax = plot_structure_value_3d(cluster, values, "GCN test")

    assert fig is not None
    assert ax.get_title() == "GCN test"
