from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from ase import Atoms
from ase.calculators.vasp.vasp_auxiliary import VaspChargeDensity

from onepiece import (
    add_adsorbate_charge_descriptors,
    add_atomic_charge_descriptors,
    add_atomic_magnetic_moment_descriptors,
    add_atomic_reference_difference_descriptors,
    add_projected_dos_descriptors,
    apply_operation,
    atomic_charge_long_table,
    compute_atomic_charges,
    doscar_projected_long_table,
    integrate_atomic_electron_populations,
    integrate_projected_dos,
    integrate_total_dos,
    read_acf_dat,
    read_chgcar,
    read_doscar,
    read_vasp_valence_electrons,
)


def test_chgcar_atomic_population_and_charge_integration(tmp_path: Path) -> None:
    calc_dir = tmp_path / "calc"
    calc_dir.mkdir()
    atoms = Atoms(
        "HeBe",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    charge_density = np.array([[[1.0]], [[3.0]]], dtype=float)
    writer = VaspChargeDensity(None)
    writer.atoms = [atoms]
    writer.chg = [charge_density]
    writer.write(calc_dir / "CHGCAR", format="chgcar")
    (calc_dir / "POTCAR").write_text("ZVAL   =   2.000\nZVAL   =   4.000\n")

    chgcar = read_chgcar(calc_dir / "CHGCAR")
    populations = integrate_atomic_electron_populations(chgcar)
    reference = read_vasp_valence_electrons(calc_dir / "CHGCAR", atoms=chgcar.atoms)
    charges = compute_atomic_charges(chgcar, reference_electrons=reference)

    assert chgcar.grid_shape == (2, 1, 1)
    assert np.allclose(populations, [1.0, 3.0])
    assert np.allclose(reference, [2.0, 4.0])
    assert np.allclose(charges, [1.0, 1.0])


def test_add_atomic_charge_descriptors_uses_chgcar_and_potcar(tmp_path: Path) -> None:
    calc_dir = tmp_path / "calc"
    calc_dir.mkdir()
    atoms = Atoms(
        "HeBe",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    writer = VaspChargeDensity(None)
    writer.atoms = [atoms]
    writer.chg = [np.array([[[1.0]], [[3.0]]], dtype=float)]
    writer.write(calc_dir / "CHGCAR", format="chgcar")
    (calc_dir / "POTCAR").write_text("ZVAL   =   2.000\nZVAL   =   4.000\n")

    frame = pd.DataFrame({"Name": ["test"], "Path": [str(calc_dir)], "struc": [atoms]})
    enriched = add_atomic_charge_descriptors(frame)
    row = enriched.iloc[0]

    assert row["integrated_electron_populations"] == [1.0, 3.0]
    assert row["atomic_charges"] == [1.0, 1.0]
    assert np.isclose(row["average_He_charge"], 1.0)
    assert np.isclose(row["average_Be_charge"], 1.0)
    assert np.isclose(row["average_He_electron_population"], 1.0)
    assert np.isclose(row["average_Be_electron_population"], 3.0)


def test_read_acf_and_default_atomic_charge_descriptors_prefer_bader(tmp_path: Path) -> None:
    calc_dir = tmp_path / "acf_calc"
    calc_dir.mkdir()
    atoms = Atoms(
        "HeBe",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    _write_acf(calc_dir / "ACF.dat", atoms, [1.1, 2.9])
    (calc_dir / "POTCAR").write_text("ZVAL   =   2.000\nZVAL   =   4.000\n")

    acf = read_acf_dat(calc_dir / "ACF.dat")
    named_acf = read_acf_dat(calc_dir / "ACF.dat", calculation_name="acf_calc")
    assert np.allclose(acf["CHARGE"].to_numpy(dtype=float), [1.1, 2.9])
    assert named_acf.index.names == ["calculation_name", "atom_index"]
    assert named_acf.index.tolist()[0] == ("acf_calc", 1)

    frame = pd.DataFrame({"Name": ["test"], "Path": [str(calc_dir)], "struc": [atoms]})
    enriched = add_atomic_charge_descriptors(frame)
    row = enriched.iloc[0]

    assert row["charge_source_used"] == "acf"
    assert row["integrated_electron_populations"] == [1.1, 2.9]
    assert np.allclose(row["atomic_charges"], [0.9, 1.1])
    assert bool(row["charge_coordinate_match"]) is True
    assert np.isclose(row["charge_coordinate_max_delta_A"], 0.0)


def test_doscar_reading_and_projected_dos_integration(tmp_path: Path) -> None:
    doscar_path = tmp_path / "DOSCAR"
    _write_synthetic_doscar(doscar_path)

    doscar = read_doscar(doscar_path)

    assert np.allclose(doscar.energies, [-2.0, -1.0, 0.0, 1.0, 2.0])
    assert np.isclose(integrate_total_dos(doscar, energy_window=(-1.0, 1.0)), 3.0)
    assert np.isclose(
        integrate_projected_dos(
            doscar,
            atom_indices=[0],
            orbitals=["d"],
            energy_window=(-1.0, 1.0),
        ),
        3.0,
    )


def test_add_projected_dos_descriptors_adds_dataframe_columns(tmp_path: Path) -> None:
    calc_dir = tmp_path / "calc"
    calc_dir.mkdir()
    doscar_path = calc_dir / "DOSCAR"
    _write_synthetic_doscar(doscar_path)
    atoms = Atoms("HeBe")
    frame = pd.DataFrame({"Name": ["test"], "Path": [str(calc_dir)], "struc": [atoms]})

    enriched = add_projected_dos_descriptors(
        frame,
        [
            {
                "column": "be_d_pdos_below_ef",
                "elements": ["Be"],
                "orbitals": ["d"],
                "energy_window": (-1.0, 1.0),
            }
        ],
    )

    assert np.isclose(enriched.loc["test", "be_d_pdos_below_ef"], 1.5)


def test_atomic_charge_and_pdos_long_tables_use_calculation_name_multiindex(tmp_path: Path) -> None:
    calc_dir = tmp_path / "calc"
    calc_dir.mkdir()
    atoms = Atoms(
        "HeBe",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    writer = VaspChargeDensity(None)
    writer.atoms = [atoms]
    writer.chg = [np.array([[[1.0]], [[3.0]]], dtype=float)]
    writer.write(calc_dir / "CHGCAR", format="chgcar")
    (calc_dir / "POTCAR").write_text("ZVAL   =   2.000\nZVAL   =   4.000\n")
    _write_synthetic_doscar(calc_dir / "DOSCAR")

    enriched = add_atomic_charge_descriptors(pd.DataFrame({"Name": ["calc-a"], "Path": [str(calc_dir)], "struc": [atoms]}))
    charge_table = atomic_charge_long_table(enriched)
    pdos_table = doscar_projected_long_table(calc_dir / "DOSCAR", calculation_name="calc-a")

    assert charge_table.index.names == ["calculation_name", "atom_index"]
    assert charge_table.index.tolist()[0] == ("calc-a", 0)
    assert pdos_table.index.names == ["calculation_name", "atom_index", "orbital", "energy_index"]
    assert pdos_table.index.tolist()[0][0] == "calc-a"


def test_adsorbate_charge_descriptors_compare_surface_and_gas_references(tmp_path: Path) -> None:
    root = tmp_path / "charge_refs"
    clean_dir = root / "clean"
    gas_dir = root / "gas"
    ads_dir = root / "ads"
    clean_dir.mkdir(parents=True)
    gas_dir.mkdir(parents=True)
    ads_dir.mkdir(parents=True)

    clean_atoms = Atoms(
        "Cu2",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    gas_atoms = Atoms(
        "CO",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]],
        cell=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    ads_atoms = Atoms(
        "Cu2CO",
        positions=[[0.5, 0.5, 0.5], [1.5, 0.5, 0.5], [2.5, 0.5, 0.5], [3.5, 0.5, 0.5]],
        cell=[[4.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        pbc=True,
    )
    _write_chgcar(clean_dir / "CHGCAR", clean_atoms, np.array([[[11.0]], [[11.0]]], dtype=float))
    _write_chgcar(gas_dir / "CHGCAR", gas_atoms, np.array([[[4.0]], [[6.0]]], dtype=float))
    _write_chgcar(
        ads_dir / "CHGCAR",
        ads_atoms,
        np.array([[[10.9]], [[10.8]], [[4.2]], [[6.1]]], dtype=float),
    )
    (clean_dir / "POTCAR").write_text("ZVAL   =   11.000\n")
    (gas_dir / "POTCAR").write_text("ZVAL   =   4.000\nZVAL   =   6.000\n")
    (ads_dir / "POTCAR").write_text("ZVAL   =   11.000\nZVAL   =   4.000\nZVAL   =   6.000\n")
    _write_acf(clean_dir / "ACF.dat", clean_atoms, [11.0, 11.0])
    _write_acf(gas_dir / "ACF.dat", gas_atoms, [4.0, 6.0])
    _write_acf(ads_dir / "ACF.dat", ads_atoms, [10.9, 10.8, 4.2, 6.1])

    frame = pd.DataFrame(
        {
            "Name": ["Cu-211-clean", "gasphases-CO", "Cu-211-clean-CO-1"],
            "Formula": ["Cu2", "CO", "Cu2CO"],
            "Path": [str(clean_dir), str(gas_dir), str(ads_dir)],
            "struc": [clean_atoms, gas_atoms, ads_atoms],
            "E": [-10.0, -14.0, -25.0],
            "record_class": ["surface", "gas_reference", "adsorbate"],
        }
    )

    enriched = add_adsorbate_charge_descriptors(frame)
    row = enriched.loc[enriched["Name"] == "Cu-211-clean-CO-1"].iloc[0]

    assert row["adsorbate_reference_mode"] == "gas_phase"
    assert np.isclose(row["adsorbate_integrated_electrons"], 10.3)
    assert np.isclose(row["adsorbate_reference_integrated_electrons"], 10.0)
    assert np.isclose(row["adsorbate_integrated_electrons_delta_vs_ref"], 0.3)
    assert np.isclose(row["adsorbate_net_charge_e"], -0.3)
    assert np.isclose(row["adsorbate_charge_delta_vs_ref_e"], -0.3)
    assert np.isclose(row["surface_integrated_electrons_delta_vs_ref"], -0.3)
    assert np.isclose(row["surface_net_charge_delta_vs_ref_e"], 0.3)
    assert np.isclose(row["charge_balance_residual_e"], 0.0)

    workflow_row = apply_operation(
        frame,
        {
            "kind": "derive_vasp_charge_descriptors",
            "charge_source": "acf",
            "calculation_path_column": "Path",
            "structure_column": "struc",
        },
    ).loc[lambda data: data["Name"] == "Cu-211-clean-CO-1"].iloc[0]
    assert np.isclose(workflow_row["adsorbate_charge_delta_vs_ref_e"], -0.3)
    assert workflow_row["charge_source_used"] == "acf"


def _write_synthetic_doscar(path: Path) -> None:
    lines = [
        "2   generated DOSCAR\n",
        "header line 2\n",
        "header line 3\n",
        "header line 4\n",
        "header line 5\n",
        "  2.000000 -2.000000 5 0.000000 0.000000\n",
    ]
    energies = [-2.0, -1.0, 0.0, 1.0, 2.0]
    total = [0.0, 1.0, 2.0, 1.0, 0.0]
    integrated = [0.0, 0.5, 2.0, 3.5, 4.0]
    for energy, dos_value, int_value in zip(energies, total, integrated, strict=False):
        lines.append(f"{energy:10.6f} {dos_value:10.6f} {int_value:10.6f}\n")

    atom_blocks = [
        {
            "s": [0.0, 0.0, 0.0, 0.0, 0.0],
            "p": [0.0, 0.0, 0.0, 0.0, 0.0],
            "d": [0.0, 1.0, 2.0, 1.0, 0.0],
        },
        {
            "s": [0.0, 0.0, 0.0, 0.0, 0.0],
            "p": [0.0, 0.0, 0.0, 0.0, 0.0],
            "d": [0.0, 0.5, 1.0, 0.5, 0.0],
        },
    ]
    for block in atom_blocks:
        lines.append("  2.000000 -2.000000 5 0.000000 0.000000\n")
        for idx, energy in enumerate(energies):
            lines.append(
                f"{energy:10.6f} {block['s'][idx]:10.6f} {block['p'][idx]:10.6f} {block['d'][idx]:10.6f}\n"
            )

    path.write_text("".join(lines))


def _write_chgcar(path: Path, atoms: Atoms, density: np.ndarray) -> None:
    writer = VaspChargeDensity(None)
    writer.atoms = [atoms]
    writer.chg = [density]
    writer.write(path, format="chgcar")


def _write_acf(path: Path, atoms: Atoms, charges: list[float]) -> None:
    lines = [
        "    #         X           Y           Z        CHARGE     MIN DIST   ATOMIC VOL\n",
        " --------------------------------------------------------------------------------\n",
    ]
    for index, (position, charge) in enumerate(zip(atoms.get_positions(), charges, strict=False), start=1):
        lines.append(
            f"{index:5d} {position[0]:11.6f} {position[1]:11.6f} {position[2]:11.6f} "
            f"{charge:11.6f} {0.1:11.6f} {5.0:11.6f}\n"
        )
    lines.extend(
        [
            " --------------------------------------------------------------------------------\n",
            " VACUUM CHARGE:               0.0000\n",
            " VACUUM VOLUME:               0.0000\n",
            f" NUMBER OF ELECTRONS:        {sum(charges):11.6f}\n",
        ]
    )
    path.write_text("".join(lines))


def test_atomic_magnetic_moments_from_structure_and_reference_delta_vectors(tmp_path: Path) -> None:
    root = tmp_path / "mag_refs"
    clean_dir = root / "clean"
    gas_dir = root / "gas"
    ads_dir = root / "ads"
    clean_dir.mkdir(parents=True)
    gas_dir.mkdir(parents=True)
    ads_dir.mkdir(parents=True)

    clean_atoms = Atoms("Cu2", positions=[[0, 0, 0], [2, 0, 0]], cell=[6, 6, 6], pbc=True)
    gas_atoms = Atoms("CO", positions=[[0, 0, 0], [1.2, 0, 0]], cell=[6, 6, 6], pbc=True)
    ads_atoms = Atoms("Cu2CO", positions=[[0, 0, 0], [2, 0, 0], [0, 0, 2.5], [1.2, 0, 2.5]], cell=[8, 6, 8], pbc=True)

    clean_atoms.set_initial_magnetic_moments([0.0, 0.0])
    gas_atoms.set_initial_magnetic_moments([0.1, -0.1])
    ads_atoms.set_initial_magnetic_moments([0.0, 0.0, 0.2, -0.05])

    (clean_dir / "POTCAR").write_text("""ZVAL   =   11.000
""")
    (gas_dir / "POTCAR").write_text("""ZVAL   =   4.000
ZVAL   =   6.000
""")
    (ads_dir / "POTCAR").write_text("""ZVAL   =   11.000
ZVAL   =   4.000
ZVAL   =   6.000
""")
    _write_acf(clean_dir / "ACF.dat", clean_atoms, [11.0, 11.0])
    _write_acf(gas_dir / "ACF.dat", gas_atoms, [4.0, 6.0])
    _write_acf(ads_dir / "ACF.dat", ads_atoms, [10.9, 10.8, 4.2, 6.1])

    frame = pd.DataFrame(
        {
            "Name": ["Cu-211-clean", "gasphases-CO", "Cu-211-clean-CO-1"],
            "Formula": ["Cu2", "CO", "Cu2CO"],
            "Path": [str(clean_dir), str(gas_dir), str(ads_dir)],
            "struc": [clean_atoms, gas_atoms, ads_atoms],
            "E": [-10.0, -14.0, -25.0],
            "record_class": ["surface", "gas_reference", "adsorbate"],
        }
    )

    magnetic = add_atomic_magnetic_moment_descriptors(frame)
    assert magnetic.loc["Cu-211-clean", "atomic_magnetic_moments"] == [0.0, 0.0]
    assert magnetic.loc["gasphases-CO", "atomic_magnetic_moments"] == [0.1, -0.1]

    enriched = add_atomic_reference_difference_descriptors(frame)
    row = enriched.loc[enriched["Name"] == "Cu-211-clean-CO-1"].iloc[0]

    assert np.allclose(row["atomic_charge_delta_vs_valence_ref_e"], [0.1, 0.2, -0.2, -0.1])
    assert np.allclose(row["atomic_charge_delta_vs_surface_ref_e"][:2], [0.1, 0.2], equal_nan=True)
    assert np.isnan(row["atomic_charge_delta_vs_surface_ref_e"][2])
    assert np.allclose(row["atomic_charge_delta_vs_gas_ref_e"][2:], [-0.2, -0.1], equal_nan=True)
    assert np.allclose(row["atomic_magnetic_moment_delta_vs_surface_ref"][:2], [0.0, 0.0], equal_nan=True)
    assert np.allclose(row["atomic_magnetic_moment_delta_vs_gas_ref"][2:], [0.1, 0.05], equal_nan=True)

    long_table = atomic_charge_long_table(enriched)
    assert "atomic_magnetic_moment" in long_table.columns
