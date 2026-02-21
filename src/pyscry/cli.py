import argparse
import multiprocessing as mp
import os

from .pyscry import process_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Find imports and their distributions")
    parser.add_argument(
        "files",
        nargs="+",
        help="List of input files (use wildcards like *.txt if needed)",
    )
    args = parser.parse_args()

    cores = os.cpu_count() or 1

    with mp.Pool(cores) as pool:
        process_files(pool, args.files)
