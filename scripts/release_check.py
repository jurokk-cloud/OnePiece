from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT) -> None:
    print(f"\n$ {' '.join(shlex.quote(part) for part in command)}")
    subprocess.run(command, cwd=cwd, env=env, check=True)


def python_in(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def executable_in(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def require_module(module: str, install_hint: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise RuntimeError(
            f"Missing required module '{module}'. Install the suggested extras first: {install_hint}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local release checks for onepiece / onepiece-studio.")
    parser.add_argument("--skip-docs", action="store_true", help="Skip the Sphinx HTML build.")
    parser.add_argument("--skip-build", action="store_true", help="Skip wheel/sdist build and wheel install validation.")
    parser.add_argument("--skip-lint", action="store_true", help="Skip Ruff lint checks.")
    args = parser.parse_args(argv)

    env = os.environ.copy()

    require_module("onepiece", "python -m pip install -e '.[dev]'")
    require_module("onepiece_studio", "python -m pip install -e ./ui")
    if not args.skip_lint:
        require_module("ruff", "python -m pip install -e '.[dev]'")
        run([sys.executable, "-m", "ruff", "check", "src", "ui/src", "tests", "examples"], env=env)
    run([sys.executable, "-m", "pytest", "-q"], env=env)
    run([sys.executable, "-m", "onepiece_studio.cli", "qa"], env=env)
    source_files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "ui" / "src").rglob("*.py"))
    run([sys.executable, "-m", "py_compile", *[str(path) for path in source_files]], env=env)

    if not args.skip_docs:
        require_module("sphinx", "python -m pip install -e '.[docs]'")
        run([sys.executable, "-m", "sphinx", "-b", "html", "docs/source", "docs/build/html"], env=env)

    if not args.skip_build:
        require_module("build", "python -m pip install -e '.[release]'")
        require_module("twine", "python -m pip install -e '.[release]'")
        dist_dir = ROOT / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        backend_dist = dist_dir / "backend"
        ui_dist = dist_dir / "ui"
        run([sys.executable, "-m", "build", "--outdir", str(backend_dist)], env=env)
        run([sys.executable, "-m", "build", "--outdir", str(ui_dist)], env=env, cwd=ROOT / "ui")
        artifacts = sorted(backend_dist.glob("*")) + sorted(ui_dist.glob("*"))
        if not artifacts:
            raise FileNotFoundError("No build artifacts found in dist/")
        run([sys.executable, "-m", "twine", "check", *[str(path) for path in artifacts]], env=env)

        with tempfile.TemporaryDirectory(prefix="onepiece_studio_release_check_") as tmpdir:
            venv_dir = Path(tmpdir) / "venv"
            venv.EnvBuilder(with_pip=True).create(venv_dir)
            vpython = python_in(venv_dir)
            pip_env = os.environ.copy()
            run([str(vpython), "-m", "pip", "install", "--upgrade", "pip"], env=pip_env)
            backend_wheels = sorted(backend_dist.glob("onepiece-*.whl"))
            ui_wheels = sorted(ui_dist.glob("onepiece_studio-*.whl"))
            if not backend_wheels:
                raise FileNotFoundError("No backend wheel found in dist/backend")
            if not ui_wheels:
                raise FileNotFoundError("No UI wheel found in dist/ui")
            run([str(vpython), "-m", "pip", "install", str(backend_wheels[-1])], env=pip_env)
            run([str(vpython), "-m", "pip", "install", str(ui_wheels[-1])], env=pip_env)
            run([str(executable_in(venv_dir, "onepiece-studio")), "--help"], env=pip_env)
            run([str(executable_in(venv_dir, "onepiece-studio")), "qa"], env=pip_env)
            run([str(vpython), "-c", "import onepiece, onepiece_studio"], env=pip_env)

    print("\nRelease checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
