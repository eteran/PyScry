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
python -m pyscry.cli .

# json output (pretty) to deps.json
python -m pyscry.cli . -f json --pretty -o deps.json

# use 4 worker processes
python -m pyscry.cli . -j 4
```
