import ast
import importlib
import importlib.metadata as md
import itertools
import logging
import multiprocessing as mp
import sysconfig
from pathlib import Path

logger = logging.getLogger(__name__)

# Preload the mapping once — huge speedup
PKG_MAP = md.packages_distributions()


def find_imports(tree: ast.Module) -> set[str]:
    """
    Walk the AST to find all imported modules.
    Only top-level modules are collected (e.g. 'requests' from 'import requests' or 'from requests import get').
    Relative imports are ignored.
    """
    modules = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            if node.module:
                modules.add(node.module.split(".")[0])

    return modules


def module_to_distribution(module_name: str) -> str | None:
    """
    Fast lookup using importlib.metadata.packages_distributions().
    """
    dists = PKG_MAP.get(module_name)
    if not dists:
        return None

    # Usually only one distribution provides a top-level module
    dist = dists[0]
    version = md.version(dist)
    return f"{dist}>={version}"


def is_stdlib_module(module_name: str) -> bool:
    """
    Determine if a module is part of the Python standard library.
    This is done by checking the module's origin against the standard library path.
    """
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return False

    if spec.origin in ("built-in", "frozen"):
        return True

    origin = Path(spec.origin)
    stdlib_path = Path(sysconfig.get_paths()["stdlib"])

    try:
        origin.relative_to(stdlib_path)
        return True
    except ValueError:
        return False


def collect_imports_from_source(path: str) -> set[str]:
    """
    Read a Python source file, parse it, and collect all imported modules.
    """
    print(f"Collecting Imports... {path}")
    source = Path(path).read_text()
    tree = ast.parse(source, filename=path)
    return find_imports(tree)


def collect_imports(pool, paths: list[str]) -> list[str]:
    """
    Collect imports from multiple source files using a multiprocessing pool.
    """
    results = pool.map(collect_imports_from_source, paths)
    return list(set(itertools.chain.from_iterable(results)))


def process_files(pool, files: list[str]) -> None:
    """
    Main processing function: collects imports and maps them to distributions.
    """
    imports = collect_imports(pool, files)

    print("Mapping modules to distributions...")
    dists = pool.map(module_to_distribution, imports)
    dist_map = dict(zip(imports, dists))

    for module, dist in dist_map.items():
        if dist:
            print(dist)

    for module, dist in dist_map.items():
        if not is_stdlib_module(module):
            if not dist:
                print(f"  {module} → (unresolved)")
