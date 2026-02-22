# PyScry

Analyzes your codebase and uncovers the exact Python packages behind every import.

## Features

- Recursively scans Python files for imports.
- Maps top-level modules to distributions.
- Outputs as plain text (one distribution per line) or JSON.

## Quickstart

Install for development into your current virtual environment.

```bash
pip install -e .
```

## Run the CLI

```bash
# scan current directory, text output
pyscry .

# json output (pretty) to deps.json
pyscry . -f json --pretty -o deps.json

# use 4 worker processes
pyscry . -j 4
```

## Version rendering

PyScry supports a `--version-style` option to control how package versions
are rendered in the output. Options:

- `minimum` (default): `Module>=x.y.z`
- `exact`: `Module==x.y.z`.
- `compatible`: `Module~=x.y.z`
- `none`: omit versions: `Module`


Other useful CLI options:

- `--exclude / -x PATTERN` : exclude files matching a glob pattern (basename,
  absolute path, or path relative to the provided input roots). Can be passed
  multiple times. Example: `-x "tests/*" -x "*/migrations/*"`.
- `--verbose / -v` : enable debug logging for troubleshooting.

Examples

```bash
# omit versions
pyscry . -f text --version-style none

# exclude tests and migrations
pyscry . -f json -o deps.json -x "tests/*" -x "*/migrations/*"

# enable debug logging
pyscry . -v .
```
