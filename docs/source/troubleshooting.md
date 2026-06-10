# Troubleshooting

This is the single troubleshooting page for OnePiece and OnePiece Studio.
Other pages link here instead of repeating the fixes. Work top to bottom:
the self-checks first, then the specific failure you are seeing.

## Start With The Self-Checks: `doctor` And `qa`

Two installed commands tell you whether the problem is your environment or
your dataset:

```bash
onepiece-studio doctor    # is this Python environment complete?
onepiece-studio qa        # does the backend still compute correct science?
```

- `doctor` checks that the runtime dependencies import and that the bundled
  tutorial dataset is available. It exits non-zero and prints `[FAIL]` lines
  when something is missing.
- `qa` loads the bundled Catalysis-Hub reference dataset, reconstructs
  adsorption energies, and compares them against the stored reaction
  energies. A healthy install prints `[PASS] catalysis-hub self-test`.
  See [Quality Control And Package QA](quality_control.md) for what each
  reported number means.

If both pass but your own file will not open, the problem is almost
certainly the dataset, not the installation — continue below.

## HDF File Will Not Load

All HDF reads go through one backend entry point
(`onepiece.read_hdf_path`), which turns the common failures into explicit
messages. Match the message you see to a case below.

### Wrong file path

```text
Dataset file not found: ...
```

Check the path. Both pandas HDF files (`.hdf`, `.h5`) and parquet dataset
directories are supported.

### Wrong HDF key

```text
Could not load HDF file '...' with key '...'. The file exists, but the
requested HDF key was not found. Available keys: ...
```

A pandas HDF file stores tables under named keys; OnePiece defaults to
`df`. The error message lists the keys actually present in the file — pick
one of those. In the UI, set the key in the **Open your data** form on the
welcome page; on the command line, pass `--key`:

```bash
onepiece-studio hdf "/path/to/your_dataset.hdf" --key df
```

A related symptom: the dataset opens but looks empty or has the wrong
columns. That usually means a valid-but-wrong key was used.

### Missing optional dependencies

```text
Could not load HDF file '...' because PyTables is unavailable ...
Could not load HDF file '...' because the current Python environment is
missing the optional dependency 'sympy' ...
```

Reading pandas HDF files requires `tables` (PyTables), and some stored
objects need `sympy` to unpickle. Repair the active environment:

```bash
pip install --upgrade onepiece-studio   # or: pip install onepiece
```

or install the named package directly (`pip install tables`). Then re-run
`onepiece-studio doctor` to confirm the environment is complete.

### Legacy NumPy-1 pickles

```text
Could not load HDF file '...' because it appears to contain legacy
NumPy-pickled objects from an older environment.
```

Older OnePiece HDF files store pickled objects (ASE `Atoms`, arrays) whose
module paths changed between NumPy 1 (`numpy.core`) and NumPy 2
(`numpy._core`). The backend installs a compatibility alias before reading,
so these files normally load transparently — through the UI, through
`onepiece.read_hdf_path`, or through `HDFSource` (see
[Reading Older HDF Files](pandas_ase.md#reading-older-hdf-files)). A plain
`pd.read_hdf` call does not get this shim, so prefer the OnePiece readers
for old files.

If the error above still appears, the compatibility reader could not
reconstruct the pickles automatically. The reliable fix is to re-export the
file from an environment matching the one that wrote it (load it there,
then write it out again with current libraries).

## Install Stalls Or Is Extremely Slow (NTFS / exFAT)

Creating a virtualenv on an NTFS or exFAT mount (typical for external
drives) is extremely slow and can hang in uninterruptible I/O. Create the
venv on a native Linux filesystem (ext4, btrfs, xfs — e.g. somewhere in
your home directory):

```bash
python -m venv ~/.venvs/onepiece
source ~/.venvs/onepiece/bin/activate
pip install onepiece-studio
```

The repository or your datasets can live anywhere, including NTFS — only
the virtualenv placement matters.

## Recommended Recovery

When an environment is in an unclear state, the simplest repair path is a
fresh install plus the self-checks:

```bash
pip install --upgrade pip
pip install --upgrade onepiece-studio
onepiece-studio doctor
onepiece-studio qa
```

Then launch the known-good bundled dataset:

```bash
onepiece-studio tutorial
```

If a command still fails, keep the exact terminal output. The exact error
message is usually more useful than a screenshot of the browser.

## Before Blaming Your Own Dataset

Always confirm first that:

- the tutorial dataset opens (`onepiece-studio tutorial`)
- `onepiece-studio qa` passes
- the `Adsorption + Gibbs analysis starter` recipe in
  **Advanced → Workflow Builder** adds its columns without errors

If all three work, problems with your own project are much more likely to
be dataset-structure issues than installation issues — see
[Load Your First Lab Dataset](load_first_lab_dataset.md) for what a
well-shaped dataset needs.
