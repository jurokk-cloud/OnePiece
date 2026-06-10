# pandas And ASE In This Project

## What Is A DataFrame?

A `pandas.DataFrame` is a table with named columns and indexed rows. In these Cu/Ga databases, one
row usually represents one calculation or one structure candidate.

For example:

```python
import pandas as pd

df = pd.read_hdf("CuGasurf_111.hdf", key="df")
df.shape
```

Typical operations:

```python
# show the first rows
df.head()

# list all columns
df.columns.tolist()

# inspect numeric columns
df.describe()

# sort most stable candidates first
df.sort_values("form_G_per_Area").head(10)

# select only relaxed calculations
df[df["fmax"] < 0.05]
```

## What Is ASE?

ASE, the Atomic Simulation Environment, is a Python library for representing, manipulating, reading,
writing, and analyzing atomistic structures.

In these databases, the `struc` column contains ASE `Atoms` objects:

```python
atoms = df.loc[0, "struc"]
atoms
```

Useful ASE commands:

```python
# chemical formula
atoms.get_chemical_formula()

# number of atoms
len(atoms)

# cell lengths and angles
atoms.cell.cellpar()

# Cartesian positions
atoms.get_positions()

# atomic symbols
atoms.get_chemical_symbols()
```

The powerful idea is that one DataFrame can store both plain tabular descriptors and rich Python
objects. OnePiece Studio respects that pattern: numeric columns become metrics and plot axes, text columns become
search/filter fields, and ASE columns become structure summaries in the record view.

## Reading Older HDF Files

Some HDF files were written with a different NumPy version and may contain pickled objects pointing
to `numpy._core`. OnePiece Studio's `HDFSource` installs a small compatibility alias before calling
`pd.read_hdf`.

```python
from onepiece_studio import HDFSource

source = HDFSource("CuGasurf_111.hdf", key="df")
df = source.load()
```

Use direct `pd.read_hdf` when your environment matches the writer environment. Use `HDFSource` when
you want the UI's compatibility handling. If a legacy file still fails to load, see
[Troubleshooting](troubleshooting.md#legacy-numpy-1-pickles).
