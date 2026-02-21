import ast
import importlib
import importlib.metadata as md
import importlib.util
import itertools
import json
import logging
import multiprocessing.pool
import sys
import sysconfig
from pathlib import Path
from typing import TextIO

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
    # Fast path for builtin modules
    if module_name in sys.builtin_module_names:
        return True

    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return False

    origin = getattr(spec, "origin", None)
    if origin in ("built-in", "frozen"):
        return True

    # Check against stdlib and platform stdlib paths
    paths = sysconfig.get_paths()
    stdlib_path = paths.get("stdlib")
    platstdlib_path = paths.get("platstdlib")
    stdlib_paths = [Path(p) for p in (stdlib_path, platstdlib_path) if p]

    if origin:
        try:
            origin_path = Path(origin)
            for sp in stdlib_paths:
                try:
                    origin_path.relative_to(sp)
                    return True
                except Exception:
                    continue
        except Exception:
            pass

    # Namespace packages may have no origin but have search locations
    locations = getattr(spec, "submodule_search_locations", None)
    if locations:
        for loc in locations:
            try:
                loc_path = Path(loc)
                for sp in stdlib_paths:
                    try:
                        loc_path.relative_to(sp)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue

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


def collect_imports(pool: multiprocessing.pool.Pool, paths: list[Path]) -> list[str]:
    """
    Collect imports from multiple source files using a multiprocessing pool.
    """
    results = pool.map(collect_imports_from_source, paths)
    return sorted(set(itertools.chain.from_iterable(results)))


def process_files(
    pool: multiprocessing.pool.Pool,
    paths: list[Path],
    output: TextIO | None = None,
    output_format: str = "text",
    pretty: bool = False,
) -> None:
    """
    Main processing function: collects imports and maps them to distributions.

    The `output` parameter may be a file-like object to write results to.
    If ``None`` the function writes to ``sys.stdout``.
    """
    imports = collect_imports(pool, paths)

    logger.debug("Mapping modules to distributions...")
    dists = pool.map(module_to_distribution, imports)
    dist_map = dict(zip(imports, dists, strict=True))

    dists = sorted({d for d in dist_map.values() if d})

    writer: TextIO
    if output is None:
        writer = sys.stdout
    else:
        writer = output

    match output_format:
        case "text":
            for dist in dists:
                writer.write(f"{dist}\n")
        case "json":
            # Build unresolved mapping in deterministic order with sorted candidate lists
            unresolved: dict[str, list[str]] = {}
            unresolved_modules = [
                m for m, d in dist_map.items() if (not is_stdlib_module(m) and not d)
            ]
            for module in sorted(unresolved_modules):
                candidates = PKG_MAP.get(module) or []
                unresolved[module] = sorted(candidates)

            payload = {"distributions": dists, "unresolved": unresolved}
            if pretty:
                json.dump(payload, writer, indent=2, ensure_ascii=False)
            else:
                json.dump(payload, writer, separators=(",", ":"), ensure_ascii=False)
            writer.write("\n")
        case _:
            raise ValueError(f"unsupported output_format: {output_format}")

    for module, dist in dist_map.items():
        if not is_stdlib_module(module):
            if not dist:
                logger.info(f"  {module} → (unresolved)")
