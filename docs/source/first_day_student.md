# First Day Guide For A Bachelor Student

This page is written for a student who has just joined a computational
chemistry or catalysis group and needs a reliable path from zero to a useful
first analysis.

## Goal Of The First Day

On day one, the goal is not to understand the entire package. The goal is:

1. install the software in one clean Python environment
2. verify that the environment works
3. open a known-good dataset
4. run one backend workflow successfully
5. inspect the resulting columns in the UI

If those five steps work, the student is ready to move from package problems to
scientific questions.

## What To Install

For a student who will use the UI, install:

```bash
pip install onepiece-studio
```

This also installs the backend package `onepiece`.

## The Three Commands To Remember

If a student remembers only three commands, they should be these:

```bash
onepiece-studio doctor
onepiece-studio qa
onepiece-studio tutorial
```

They mean:

- `doctor`: check whether the Python environment is complete
- `qa`: verify the package against the bundled reference dataset
- `tutorial`: open a known-good example in the browser UI

## The Recommended First Session

Run:

```bash
onepiece-studio doctor
onepiece-studio qa
onepiece-studio tutorial
```

Then in the UI:

1. open `Data Sources`
2. confirm that one dataset is loaded
3. open `Schema`
4. look for columns such as `Name`, `Formula`, `E`, and structure columns
5. open `Workflow`
6. run `Adsorption + Gibbs analysis starter`
7. open `Records`
8. confirm that new columns such as `G` and `adsorption_free_energy` appear
9. open `Visualize`
10. choose a simple scatter plot from numeric columns

That is enough for a successful first day.

## What The Student Should Understand Early

The UI is not the scientific engine. The backend is.

The real model is:

1. OnePiece loads a dataset into a DataFrame
2. backend functions add or transform scientific columns
3. OnePiece Studio shows the result and lets the user inspect it

This is important because it keeps the work reproducible. A student should
learn to think in terms of:

- rows
- columns
- references
- derived quantities
- saved workflow steps

## What To Do Before Loading A Real Group Dataset

Do not start with the group's hardest dataset.

Before loading project data, the student should confirm that:

- `onepiece-studio doctor` passes
- `onepiece-studio qa` passes
- the tutorial dataset opens
- one backend workflow runs without errors

If all four are true, any later problem is much more likely to come from the
project dataset structure than from the installation itself.

## First Real Questions The Student Can Answer

After the first successful session, useful beginner questions are:

- Which datasets contain gas, slab, and adsorbate rows?
- Which columns are already numeric and ready for plotting?
- Which rows are converged?
- Which structures belong to the same surface reference?
- Which adsorption energies were already computed and which still need
  references?

These are good first-day and first-week questions because they build intuition
without forcing the student to understand every implementation detail at once.

## If Something Fails

Follow the recovery path and the error-specific fixes in
[Troubleshooting](troubleshooting.md). Keep the exact terminal output: for
beginners, the exact error message is usually more useful than a screenshot
of the browser alone.

## What The Supervisor Or PhD Student Should Provide

To make the package genuinely usable for a new bachelor student, the local
project should also provide:

- one clean example dataset
- one sentence describing what each row represents
- one recommended workflow recipe
- one recommended first plot
- one naming convention for saved views and derived columns

The package can support a student well, but the lab still needs to provide a
small amount of scientific orientation.
