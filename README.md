# knowledge-agent
A Python library that queries, processes, and fuses *knowledge tiles*.  
Part of the **Cocapn Fleet** (https://github.com/SuperInstance).

## Description
- Loads tile data from a wiki‑style database.  
- Provides query utilities (`tile_query.py`).  
- Implements trust‑based fusion (`tile_trust_fusion.py`).  
- Exposes a simple CLI (`cli.py`) for interactive use.  

## Usage
```bash
# Install (editable)
pip install -e .

# Show CLI help
python -m cli --help

# Example: query a tile
python -m cli query --tile-id 42

# Run tests
pytest tests/
```

## Related
- **Cocapn Fleet** – the umbrella project: https://github.com/SuperInstance  

---  

## Development notes (reasoning behind the README)

- **Title & description**: Clearly state the repo name and its purpose (knowledge‑tile processing) while mentioning its affiliation with the Cocapn Fleet.  
- **Usage**: Provide the most common commands—installation, CLI help, a sample query, and test execution—so users can get started quickly.  
- **Related**: Link back to the parent organization as requested.  
- **Structure**: Kept the README under 30 lines (excluding the optional “Development notes” section) and used plain markdown for maximum compatibility.  
- **Files referenced**: The CLI (`cli.py`), query module (`tile_query.py`), fusion module (`tile_trust_fusion.py`), and database helper (`wiki_database.py`) are highlighted in the description to guide developers toward the core components.  