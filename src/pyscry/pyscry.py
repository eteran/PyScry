import ast
import importlib
import importlib.metadata as md
import importlib.util
import itertools
import json
import logging
import sys
import sysconfig
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Protocol, TextIO

logger = logging.getLogger(__name__)

# Preload the mapping once — huge speedup
PKG_MAP = md.packages_distributions()


class PoolProtocol(Protocol):
    def map[S, T](
        self, func: Callable[[S], T], iterable: Iterable[S], chunksize: int | None = None
    ) -> list[T]: ...


@dataclass(slots=True)
class Distribution:
    name: str
    version: str | None = None

    def to_specifier(self, version_style: str = "minimum") -> str:
        if self.version is None or version_style == "none":
            return self.name
        if version_style == "compatible":
            op = "~="
        elif version_style == "exact":
            op = "=="
        else:
            op = ">="
        return f"{self.name}{op}{self.version}"


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


def module_to_distributions(module_name: str) -> list[Distribution]:
    """
    Fast lookup using importlib.metadata.packages_distributions().

    Returns a list of `Distribution` objects (name + optional version).
    If no distribution provides the module an empty list is returned.
    """
    dists = PKG_MAP.get(module_name) or []
    results: list[Distribution] = []
    for dist in dists:
        try:
            version = md.version(dist)
            results.append(Distribution(name=dist, version=version))
        except PackageNotFoundError:
            results.append(Distribution(name=dist))
    return results


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
    locations = getattr(spec, "submodule_search_locations", [])
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


def collect_imports(pool: PoolProtocol, paths: list[Path]) -> list[str]:
    """
    Collect imports from multiple source files using a multiprocessing pool.
    """
    results = pool.map(collect_imports_from_source, paths)
    return sorted(set(itertools.chain.from_iterable(results)))


def process_files(
    pool: PoolProtocol,
    paths: list[Path],
    output: TextIO | None = None,
    output_format: str = "text",
    pretty: bool = False,
    version_style: str = "minimum",
) -> None:
    """
    Main processing function: collects imports and maps them to distributions.

    The `output` parameter may be a file-like object to write results to.
    If ``None`` the function writes to ``sys.stdout``.
    """
    imports = collect_imports(pool, paths)

    logger.debug("Mapping modules to distributions...")
    mapped = pool.map(module_to_distributions, imports)
    dist_map = dict(zip(imports, mapped, strict=True))

    # Flatten and de-dupe distribution specifiers in deterministic order.
    flattened = {info.to_specifier(version_style) for specs in dist_map.values() for info in specs}
    dists = sorted(flattened)

    def create_writer() -> TextIO:
        if output is None:
            return sys.stdout
        return output

    writer = create_writer()

    match output_format:
        case "text":
            for dist in dists:
                writer.write(f"{dist}\n")
        case "json":
            # Build unresolved mapping in deterministic order with sorted candidate lists
            unresolved: dict[str, list[str]] = {}
            unresolved_modules = [m for m, d in dist_map.items() if (not is_stdlib_module(m) and not d)]
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

    for module, specs in dist_map.items():
        if not is_stdlib_module(module):
            if not specs:
                logger.info(f"  {module} → (unresolved)")
