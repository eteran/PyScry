import multiprocessing as mp
import os
from contextlib import ExitStack
from pathlib import Path
import fnmatch
from typing import Iterable

import click

from .pyscry import process_files


def collect_py_files(paths: list[Path], excludes: Iterable[str] | None = None) -> list[Path]:
    """
    Collect all Python source files from the provided paths.
    If a path is a directory, it will be traversed recursively.
    """
    files: list[Path] = []
    excludes = list(excludes or [])

    def is_excluded(p: Path) -> bool:
        if not excludes:
            return False
        s = p.as_posix()
        for pat in excludes:
            # match against absolute path, basename, and path relative to any input root
            if fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(p.name, pat):
                return True
            for root in paths:
                try:
                    if root.is_dir() and p.is_relative_to(root):
                        rel = p.relative_to(root).as_posix()
                        if fnmatch.fnmatch(rel, pat):
                            return True
                except Exception:
                    continue
        return False

    for path in paths:
        if path.is_file() and path.suffix == ".py":
            p = path.resolve()
            if not is_excluded(p):
                files.append(p)
        elif path.is_dir():
            for file in path.rglob("*.py"):
                p = file.resolve()
                if not is_excluded(p):
                    files.append(p)
    return files


@click.command()
@click.argument("paths", default=["."], nargs=-1, type=click.Path(path_type=Path, exists=True))
@click.option(
    "--jobs", "-j", type=int, default=os.cpu_count(), help="Number of parallel jobs to use"
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=True),
    default="text",
    help="Output format: text (lines) or json",
)
@click.option(
    "--pretty/--no-pretty",
    default=False,
    help="Pretty-print JSON output (adds indentation).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path, exists=False),
    default=None,
    help="Write discovered distributions to FILE instead of stdout",
)
@click.option(
    "--version-style",
    type=click.Choice(["compatible", "minimum", "none", "exact"], case_sensitive=True),
    default="minimum",
    help="How to render versions: compatible (~=), minimum (>=), exact (==), or none (omit)",
)
@click.option(
    "--exclude",
    "-x",
    "excludes",
    multiple=True,
    help="Exclude file patterns (glob). Can be passed multiple times.",
)
def main(
    paths: list[Path],
    jobs: int,
    output: Path | None,
    output_format: str,
    pretty: bool,
    version_style: str,
    excludes: tuple[str, ...],
) -> None:

    if jobs < 1:
        raise click.BadParameter("Number of jobs must be at least 1")

    real_paths = collect_py_files(paths, excludes=list(excludes))

    if not real_paths:
        raise click.BadParameter("No Python files found in the specified paths")

    # Manage output file and other context via ExitStack for simpler cleanup
    with ExitStack() as stack:
        fh = None
        if output is not None:
            if output.exists() and output.is_dir():
                raise click.BadParameter("--output must be a file, not a directory")
            fh = stack.enter_context(output.open("w", encoding="utf-8"))

        with mp.Pool(jobs) as pool:
            process_files(
                pool,
                real_paths,
                output=fh,
                output_format=output_format,
                pretty=pretty,
                version_style=version_style,
            )


if __name__ == "__main__":
    main()
