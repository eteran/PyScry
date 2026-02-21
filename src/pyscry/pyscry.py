import ast
import importlib
import importlib.metadata as md
import importlib.util
import itertools
import logging
import multiprocessing.pool
import sysconfig
from pathlib import Path

logger = logging.getLogger(__name__)

# Preload the mapping once — huge speedup
PKG_MAP = md.packages_distributions()


def find_imports(tree: ast.Module) -> set[str]:
    """
    Walk the AST to find all imported modules.
    Only top-level modules are collected.
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
    try:
        version = md.version(dist)
        return f"{dist}>={version}"
    except md.PackageNotFoundError:
        return dist


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


def collect_imports_from_source(path: Path) -> set[str]:
    """
    Read a Python source file, parse it, and collect all imported modules.
    """
    logger.debug(f"Collecting Imports... {path}")

    try:
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        return find_imports(tree)
    except SyntaxError as e:
        logger.warning(f"Syntax error in {path}: {e}")
        return set()
    except OSError as e:
        logger.warning(f"Error reading {path}: {e}")
        return set()


def collect_imports(pool, paths: list[Path]) -> list[str]:
    """
    Collect imports from multiple source files using an executor that
    provides a ``map(func, iterable)`` method (e.g. ``multiprocessing.Pool``
    or ``concurrent.futures.ThreadPoolExecutor``).
    """
    results = list(pool.map(collect_imports_from_source, paths))
    return sorted(set(itertools.chain.from_iterable(results)))


def process_files(pool, paths: list[Path]) -> None:
    """
    Main processing function: collects imports and maps them to distributions.
    """
    imports = collect_imports(pool, paths)

    logger.debug("Mapping modules to distributions...")
    dists = list(pool.map(module_to_distribution, imports))
    dist_map = dict(zip(imports, dists, strict=True))

    dists = {d for d in dist_map.values() if d}

    for dist in dists:
        print(dist)

    for module, dist in dist_map.items():
        if not is_stdlib_module(module):
            if not dist:
                logger.info(f"  {module} → (unresolved)")
