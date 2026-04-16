#!/usr/bin/env python3
"""
Build a single self-contained Jupyter notebook cell for Kaggle.

The generated cell does three things in order:
1. Installs the Python dependencies declared in `pyproject.toml`.
2. Inlines the local project modules with `stickytape`.
3. Appends the contents of `benchmark/tasks.py`, which exposes the task objects
   and example commands that the notebook user can run manually.

The result is a plain text printed to stdout. Run
`python3 build_kaggle_notebook.py`, then paste the output into a notebook cell.
"""
import pathlib
from typing import Iterable

import stickytape
from pyproject_parser import PyProject
from benchmark.infrastructure import PROMPTS_DIR

ENTRYPOINT = "_kaggle_runner.py"


def _install_dependencies() -> Iterable[str]:
    """Convert project dependencies into `%pip install ...` notebook commands."""
    pyproject_toml = PyProject.load("pyproject.toml")
    dependencies = pyproject_toml.project.get("dependencies", [])
    for dependency in dependencies:
        yield f"%pip install {dependency}"


def main():
    output = []

    python_paths = [pathlib.Path(__file__).parent]

    def new_build(self: stickytape.ModuleWriterGenerator) -> str:
        """
        Patch (hackily) `stickytape.ModuleWriterGenerator.build` to make repeated notebook
        executions behave like a fresh import.

        `stickytape` normally writes bundled modules into the temporary module
        directory, but it does not clear already-imported entries from
        `sys.modules`. In a regular script that is fine because the process
        starts once and exits. In Jupyter, users often rerun the same cell after
        editing it or after changing runtime state. Without clearing
        `sys.modules`, Python would keep serving the old in-memory module
        objects, so the freshly written files would be ignored on re-import.

        Deleting each bundled module from `sys.modules` before writing it forces
        Python to load the regenerated module code on the next import.
        """
        output = []
        for module_path, module_source in self._modules.values():
            # Convert file paths such as `benchmark/tasks.py` or
            # `benchmark/__init__.py` into importable module names.
            python_module_name = str(module_path).removesuffix(".py").removesuffix("/__init__").replace("/", ".")
            # If the module was imported during an earlier notebook execution,
            # drop it from the import cache so the rewritten file is used.
            output.append("    if '{0}' in __stickytape_sys.modules: del __stickytape_sys.modules['{0}']\n".format(python_module_name))
            # Keep the original `stickytape` behavior: write the bundled module
            # source into the temporary package directory.
            output.append("    __stickytape_write_module({0}, {1})\n".format(
                repr(module_path),
                repr(module_source)
            ))
        return "".join(output)

    stickytape.ModuleWriterGenerator.build = new_build

    # 1. Emit Kaggle-friendly dependency installation commands.
    output.append("# Installing dependencies")
    # curl is useful for an LLM, which will be running inside the same container at Kaggle.
    output.append("!apt update && apt install -y curl")
    # Install Python packages from pyproject.toml to run our code.
    output.extend(_install_dependencies())

    # 2. Emit the `stickytape` runtime prelude plus all bundled local modules.
    output.append("# Saving our code into a temporary package directory")
    output.append(stickytape._prelude())
    output.append(stickytape._generate_module_writers(
        ENTRYPOINT,
        sys_path=python_paths,
        add_python_modules=[],
    ))
    for prompt in PROMPTS_DIR.glob("*.md"):
        output.append("    __stickytape_write_module({0}, {1})".format(
            repr(f"benchmark/prompts/{prompt.name}"), repr(prompt.read_bytes())
        ))
    output.extend([
        # After writing module files, tell Python's import system to forget any
        # stale filesystem metadata before the entrypoint imports them.
        "    import importlib as __stickytape_importlib",
        "    __stickytape_importlib.invalidate_caches()"
    ])

    # 3. Add an entrypoint for the Jupyter notebook's cell at Kaggle.
    output.append(stickytape._indent(pathlib.Path(ENTRYPOINT).read_text()))

    print("\n".join(output))


if __name__ == "__main__":
    main()
