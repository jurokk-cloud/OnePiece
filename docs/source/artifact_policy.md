# Repository Artifact Policy

OnePiece contains source code, documentation, tutorials, generated figures, and
scientific example data. This page defines what should live in git and what
should be regenerated or stored elsewhere.

## Commit By Default

Commit source files:

```text
src/
ui/src/
tests/
docs/source/*.md
docs/source/conf.py
examples/*.py
scripts/*.py
notebooks/*/README.md
notebooks/*/create_*.py
notebooks/*/run_*.py
```

Commit small fixtures that are required for tests or tutorials:

```text
src/onepiece/data/*.hdf
tests/data/
small CSV fixtures
small static images used directly by docs
```

## Commit Selectively

Commit generated figures only when they are directly referenced by docs and
small enough to be practical:

```text
docs/source/_static/worked_examples/
docs/source/_static/screenshots/
```

Commit generated notebooks only when they are part of the maintained tutorial
surface and can be regenerated from a builder script.

## Do Not Commit By Default

Avoid committing build outputs:

```text
docs/build/
docs/onepiece_documentation_html.zip
```

Avoid committing temporary LaTeX outputs:

```text
*.aux
*.log
*.out
*.toc
*.nav
*.snm
*.fls
*.fdb_latexmk
```

Avoid committing Python cache and local OS files:

```text
__pycache__/
*.pyc
.DS_Store
.pytest_cache/
```

Avoid committing large raw DFT files unless they are explicitly licensed and
needed as fixtures:

```text
CHGCAR
WAVECAR
DOSCAR
vasprun.xml
OUTCAR
```

## External Data

Published DFT data should first be staged outside the package source tree,
normalized, and saved as a managed OnePiece dataset with provenance. Commit only
the minimal derived fixture if redistribution is allowed.

For example:

```text
external_data/article_slug/raw/          not committed
external_data/article_slug/processed/    not committed
src/onepiece/data/article_subset.hdf     committed only if license permits
docs/source/article_worked_example.md    committed
```

## Practical Rule

If a file is expensive to regenerate but not scientifically required by the
package, store it as a release artifact rather than in git.

If a file is required to make a tutorial reproducible, keep the smallest useful
version and document how it was generated.

