import multiprocessing as mp
import os
from pathlib import Path

import click

from .pyscry import process_files


def collect_py_files(paths: list[Path]) -> list[Path]:
    """
    Collect all Python source files from the provided paths.
    If a path is a directory, it will be traversed recursively.
    """
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path.resolve())
        elif path.is_dir():
            for file in path.rglob("*.py"):
                files.append(file.resolve())
    return files


@click.command()
@click.argument("paths", default=["."], nargs=-1, type=click.Path(path_type=Path, exists=True))
@click.option(
    "--jobs", "-j", type=int, default=os.cpu_count(), help="Number of parallel jobs to use"
)
def main(paths: list[Path], jobs: int) -> None:

    if jobs < 1:
        raise click.BadParameter("Number of jobs must be at least 1")

    real_paths = collect_py_files(paths)

    if not real_paths:
        raise click.BadParameter("No Python files found in the specified paths")

    with mp.Pool(jobs) as pool:
        process_files(pool, real_paths)
