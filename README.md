# knowledge-agent

A Python library that queries, processes, and fuses *knowledge tiles*.  
Part of the **Cocapn Fleet** (https://github.com/SuperInstance).

## Overview

**knowledge-agent** implements the Knowledge Tiling framework — a composable, versioned system for managing atomic units of knowledge within the Cocapn Fleet. Knowledge tiles are the fundamental building blocks from which all fleet agent capabilities are constructed. Each tile carries rich metadata including provenance (source, confidence), domain classification, prerequisite chains, version history with SHA-256 content hashes, and configurable expiry.

The system provides four integrated layers: a tile store with versioning, a graph-based prerequisite DAG, a flexible query DSL with boolean operators and aggregation, and a trust-aware fusion engine that merges tiles from multiple sources using weighted conflict resolution with a tamper-evident audit trail.

### Key Features

- **Five capability domains** — Code, Social, Trust, Creative, Infrastructure
- **Versioned tiles** with SHA-256 content hashes and immutable snapshots
- **Prerequisite DAG** with cycle detection, depth computation, and frontier analysis
- **Query DSL** supporting tag, source, domain, confidence, proximity, and boolean operators
- **Trust-based fusion** with configurable conflict resolution strategies
- **Cryptographic audit trail** with SHA-256 hash chaining for tamper-evidence
- **Wiki database** with bidirectional tile/page cross-referencing and automatic backlinks

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Query Layer                                 │
│  TileQueryEngine → QueryParser → QueryNode AST → TileStore/Index  │
├──────────────────────────────────────────────────────────────────┤
│                     Fusion Layer                                 │
│  TrustFusionEngine → ConflictResolver → TrustFusionConfig         │
│  FusionAuditTrail (SHA-256 chained)                              │
├──────────────────────────────────────────────────────────────────┤
│                     Knowledge Layer                              │
│  KnowledgeTile → TileVersion → TileStore → TileIndex → TileGraph  │
├──────────────────────────────────────────────────────────────────┤
│                     Wiki Layer                                  │
│  WikiDatabase → WikiPage → TileWikiLink → BacklinkIndex           │
└──────────────────────────────────────────────────────────────────┘
```

## Knowledge Model

### Knowledge Tiles

A `KnowledgeTile` is the atomic unit of knowledge. Every tile has:

- **Identity**: Unique ID, human-readable name, description
- **Domain**: One of five capability domains (CODE, SOCIAL, TRUST, CREATIVE, INFRASTRUCTURE)
- **Provenance**: Source attribution, confidence score (0.0–1.0), creation/update timestamps
- **Composition**: Prerequisites forming a DAG, enabling progressive capability acquisition
- **Lifecycle**: Optional expiry timestamp for time-sensitive knowledge
- **Versioning**: Full edit history with SHA-256 content hashes and lineage chains

### Trust Fusion

The `TrustFusionEngine` merges tiles from multiple sources using trust-weighted aggregation:

- **Conflict Strategies**: `HIGHEST_CONFIDENCE`, `HAST_TRUST`, `MOST_RECENT`, `MERGE_TAGS`, `MANUAL`
- **Trust Dimensions**: Competence, Reliability, Honesty, Generosity, Reciprocity
- **Domain Trust Maps**: Different domains weight trust dimensions differently
- **Trust Decay**: Configurable daily exponential decay rate (default 0.95)
- **Audit Chain**: Every fusion operation is recorded with SHA-256 hash linking

### Query Language

The `TileQueryEngine` supports a powerful query DSL:

```
tag:python                              # tiles with tag "python"
AND(tag:python, source:wikipedia)          # boolean AND
OR(tag:python, tag:rust)                  # boolean OR
NOT(tag:deprecated)                       # boolean NOT
confidence:>0.8                           # confidence range
near:basic_auth                           # proximity search
AGG(count, domain:code)                   # aggregate query
AGG(top_sources, tag:python)             # aggregate with top sources
prereq:basic_auth                         # prerequisite chain query
```

## Quick Start

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

### Programmatic API

```python
from knowledge_tiles import KnowledgeTile, TileDomain, TileStore, TileIndex, TileGraph
from tile_query import TileQueryEngine, QueryParser
from tile_trust_fusion import TrustFusionEngine, ConflictResolver, ConflictStrategy
from wiki_database import WikiDatabase

# Create and store tiles
store = TileStore()
store.put(KnowledgeTile(
    id="basic_http",
    name="Basic HTTP Authentication",
    domain=TileDomain.CODE,
    tags=["http", "auth", "web"],
    confidence=0.95,
    source="wikipedia",
))

# Build index and run queries
index = TileIndex(store)
engine = TileQueryEngine(store, index)
result = engine.execute("tag:http AND confidence:>0.8")
print(f"Found {len(result.tiles)} tiles")

# Proximity search — find related tiles
related = engine.find_related("basic_http", max_results=5)

# Build prerequisite graph
graph = TileGraph.from_tile_list(store.get_all())
frontier = graph.compute_frontier(acquired={"basic_http"})
bottlenecks = graph.find_bottleneck_tiles(top_n=5)

# Fuse tiles from multiple sources
resolver = ConflictResolver(source_trust={"wikipedia": 0.9, "internal": 0.7})
engine = TrustFusionEngine(resolver=resolver)
fused, resolutions, conflicts = engine.fuse_tiles({
    "wikipedia": [wiki_tile_1, wiki_tile_2],
    "internal": [internal_tile_1],
})
print(f"Fused {len(fused)} tiles, {len(conflicts)} conflicts")

# Wiki integration
wiki = WikiDatabase()
wiki.create_page("Authentication", "See [[tile:basic_http]] for HTTP auth basics.")
backlinks = wiki.get_backlinks("Authentication")
```

## API Reference

### TileStore

| Method | Description |
|--------|-------------|
| `put(tile, editor, note)` | Store or update a tile, creating version snapshot |
| `get(tile_id)` | Retrieve tile by ID (returns None if expired) |
| `get_version(tile_id, version)` | Get a specific version snapshot |
| `restore_version(tile_id, version)` | Restore tile to a previous version |
| `get_version_history(tile_id)` | Get full edit history |
| `save_to_file(path)` | Persist all tiles and versions to JSON |
| `load_from_file(path)` | Load tiles and versions from JSON |

### TileGraph

| Method | Description |
|--------|-------------|
| `add_tile(tile)` | Add tile to DAG (raises ValueError on cycle) |
| `compute_depths()` | Compute depth of every tile (distance from roots) |
| `compute_frontier(acquired)` | Tiles one step from being acquirable |
| `immediate_acquirable(acquired)` | Tiles whose prerequisites are all met |
| `find_bottleneck_tiles(n)` | Tiles required by the most other tiles |

### TrustFusionEngine

| Method | Description |
|--------|-------------|
| `fuse_tiles(sources, strategy)` | Merge tiles from multiple sources |
| `trust_weighted_aggregate(tiles, field)` | Compute trust-weighted average |
| `check_trust_gate(tile_id, trust)` | Check if trust meets tile's threshold |
| `update_source_trust(source, delta)` | Update a source's trust score |
| `fleet_summary()` | Generate fleet-wide fusion summary |

## Related

- **Cocapn Fleet** – the umbrella project: https://github.com/SuperInstance

## License

See the [LICENSE](LICENSE) file for details.

---

<img src="callsign1.jpg" width="128" alt="callsign">
