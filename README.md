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

## Module Structure

```
knowledge-agent/
├── knowledge_tiles.py    # Core: TileDomain, KnowledgeTile, TileVersion,
│                         #       TileStore, TileIndex, TileGraph
├── tile_query.py         # Query: QueryParser, QueryNode AST,
│                         #        TileQueryEngine, ProximityQuery
├── tile_trust_fusion.py  # Fusion: TrustFusionEngine, ConflictResolver,
│                         #         TileTrustConfig, FusionAuditTrail
├── wiki_database.py      # Wiki:  WikiDatabase, WikiPage,
│                         #        WikiPageVersion, TileWikiLink
├── cli.py                # CLI:   store, query, fuse, wiki, onboard, status
├── tests/                # Comprehensive test suite (pytest + standalone runner)
├── callsign1.jpg         # Agent callsign badge
└── README.md
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Query Layer                                 │
│  TileQueryEngine → QueryParser → QueryNode AST → TileStore/Index  │
├──────────────────────────────────────────────────────────────────┤
│                     Fusion Layer                                 │
│  TrustFusionEngine → ConflictResolver → TileTrustConfig           │
│  FusionAuditTrail (SHA-256 chained)                              │
├──────────────────────────────────────────────────────────────────┤
│                     Knowledge Layer                              │
│  KnowledgeTile → TileVersion → TileStore → TileIndex → TileGraph  │
├──────────────────────────────────────────────────────────────────┤
│                     Wiki Layer                                  │
│  WikiDatabase → WikiPage → TileWikiLink → BacklinkIndex           │
└──────────────────────────────────────────────────────────────────┘
```

```
                    ┌─────────────┐
                    │    CLI      │
                    │  (cli.py)   │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │  TileStore │ │TileQuery  │ │  Wiki    │
     │  + Index   │ │  Engine   │ │Database  │
     └─────┬──────┘ └─────┬─────┘ └────┬─────┘
           │              │            │
           ▼              ▼            ▼
     ┌─────────────────────────────────────┐
     │       TrustFusionEngine             │
     │  (ConflictResolver + AuditTrail)    │
     └─────────────────────────────────────┘
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

- **Conflict Strategies**: `HIGHEST_CONFIDENCE`, `HIGHEST_TRUST`, `MOST_RECENT`, `MERGE_TAGS`, `MANUAL`
- **Trust Dimensions**: Competence, Reliability, Honesty, Generosity, Reciprocity
- **Domain Trust Maps**: Different domains weight trust dimensions differently
- **Trust Decay**: Configurable daily exponential decay rate (default 0.95)
- **Audit Chain**: Every fusion operation is recorded with SHA-256 hash linking

### Wiki Integration

The `WikiDatabase` provides a versioned knowledge base with tile cross-referencing:

- **Pages** have full edit history with SHA-256 content hashing
- **Tile references** via `[[tile:id]]` syntax — automatically extracted
- **Page links** via `[[page:Topic]]` syntax — automatic backlink index
- **Cross-references** track bidirectional tile ↔ page relationships

### Query Language

The `TileQueryEngine` supports a powerful query DSL:

```
tag:python                              # tiles with tag "python"
AND(tag:python, source:wikipedia)       # boolean AND
OR(tag:python, tag:rust)                # boolean OR
NOT(tag:deprecated)                     # boolean NOT
confidence:>0.8                         # confidence range
confidence:0.5-0.9                      # confidence between values
domain:code                             # domain filter
source:wikipedia                        # source filter
id:auth                                 # ID pattern match
after:1700000000                        # tiles created after timestamp
before:1700000000                       # tiles created before timestamp
prereq:basic_auth                       # prerequisite chain query
near:basic_auth                         # proximity/related search
AGG(count, domain:code)                 # aggregate: count
AGG(avg_confidence, tag:python)         # aggregate: average confidence
AGG(top_sources, tag:python)            # aggregate: top sources
AGG(tag_breakdown, *)                   # aggregate: tag distribution
AGG(domain_breakdown, *)                # aggregate: domain distribution
*                                       # wildcard: match all tiles
```

## Quick Start

```bash
# Install (editable)
pip install -e .

# Show CLI help
python cli.py

# Onboard with sample data
python cli.py onboard

# Show agent status
python cli.py status

# Example: query tiles
python cli.py query "tag:python AND confidence:>0.8"

# Example: fuse tiles from multiple sources
python cli.py fuse source_a.json source_b.json

# Run tests
pytest tests/ -v
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
fusion = TrustFusionEngine(resolver=resolver)
fused, resolutions, conflicts = fusion.fuse_tiles({
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

### KnowledgeTile

| Method / Property | Description |
|---|---|
| `has_prerequisites(acquired)` | Check whether all prerequisite tile IDs are in the set |
| `missing_prerequisites(acquired)` | Return prerequisite IDs not yet acquired |
| `is_expired(now)` | Check whether the tile has expired (None = now) |
| `domain_compatibility(other)` | Score compatibility with another tile (0.0–1.0) |
| `clone()` | Create a deep copy |
| `to_dict()` / `from_dict()` | Serialize / deserialize |

### TileStore

| Method | Description |
|---|---|
| `put(tile, editor, note)` | Store or update a tile, creating version snapshot |
| `get(tile_id)` | Retrieve tile by ID (returns None if expired) |
| `get_all(include_expired)` | Retrieve all tiles (default: exclude expired) |
| `delete(tile_id)` | Delete a tile. Returns True if it existed |
| `get_version(tile_id, version)` | Get a specific version snapshot |
| `restore_version(tile_id, version)` | Restore tile to a previous version |
| `get_version_history(tile_id)` | Get full edit history |
| `load_tiles_from_json(path)` | Bulk-import tiles from a JSON file |
| `save_to_file(path)` / `load_from_file(path)` | Persist / restore full store to JSON |
| `tile_count()` | Total number of stored tiles |

### TileIndex

| Method | Description |
|---|---|
| `search_by_tag(tag)` | Find all tiles with a given tag |
| `search_by_tags(tags, match_all)` | Find tiles matching multiple tags (AND/OR) |
| `search_by_source(source)` | Find all tiles from a given source |
| `search_by_domain(domain)` | Find all tiles in a given domain |
| `search_by_confidence(min, max)` | Find tiles within a confidence range |
| `search_by_time_range(after, before)` | Find tiles created within a time range |
| `search_by_prerequisite(prereq_id)` | Find tiles that require a specific prerequisite |
| `search_by_id_pattern(pattern)` | Substring match on tile IDs |
| `refresh()` | Rebuild indices after store changes |
| `stats()` | Index statistics (totals, tag/source counts) |
| `all_tags()` / `all_sources()` / `all_domains()` | Enumerate unique values |

### TileGraph

| Method | Description |
|---|---|
| `add_tile(tile)` | Add tile to DAG (raises `ValueError` on cycle) |
| `remove_tile(tile_id)` | Remove a tile and clean up prerequisite references |
| `compute_depths()` | Compute depth of every tile (distance from roots) |
| `compute_frontier(acquired)` | Tiles one step from being acquirable |
| `immediate_acquirable(acquired)` | Tiles whose prerequisites are all met |
| `find_bottleneck_tiles(n)` | Tiles required by the most other tiles |
| `has_cycle()` | Check if the graph contains circular dependencies |
| `from_tile_list(tiles)` | Construct a graph from a list of tiles (classmethod) |

### TileQueryEngine

| Method | Description |
|---|---|
| `execute(query)` | Execute a query expression string → `QueryResult` |
| `execute_ast(node)` | Execute a pre-parsed `QueryNode` AST → `QueryResult` |
| `find_related(tile_id, max_results)` | Proximity search for related tiles |

`QueryResult` contains `.tiles`, `.aggregate` (if applicable), `.query_expression`, and `.execution_time_ms`.

### TrustFusionEngine

| Method | Description |
|---|---|
| `fuse_tiles(sources, strategy)` | Merge tiles from `Dict[source, List[Tile]]` |
| `trust_weighted_aggregate(tiles, field)` | Compute trust-weighted average of a numeric field |
| `check_trust_gate(tile_id, trust)` | Check if trust meets tile's access threshold |
| `update_source_trust(source, delta)` | Update a source's trust score |
| `compute_tile_trust_gain(tile_id, domain)` | Compute trust dimension gains for completing a tile |
| `get_source_reputation(source)` | Get reputation stats (trust, win rate, fusions) |
| `fleet_summary()` | Generate fleet-wide fusion summary with audit status |

### ConflictResolver

| Method | Description |
|---|---|
| `resolve(candidates, strategy)` | Resolve a conflict between candidate tiles |
| `set_source_trust(source, trust)` | Set trust score for a source (0.0–1.0) |
| `get_source_trust(source)` | Get trust score for a source (0.3 if unknown) |

### FusionAuditTrail

| Method | Description |
|---|---|
| `create_entry(event_type, source, tile_ids, context)` | Create, seal, and append an audit entry |
| `verify_chain()` | Verify integrity of entire hash chain |
| `get_entries(event_type, source, limit)` | Query audit entries with filters |
| `entry_count()` | Total number of audit entries |

### WikiDatabase

| Method | Description |
|---|---|
| `create_page(topic, content, editor, note)` | Create a new wiki page |
| `get_page(topic)` | Get a wiki page by topic |
| `edit_page(topic, content, editor, note)` | Edit a page, creating a new version |
| `delete_page(topic)` | Delete a page and clean up references |
| `get_history(topic)` | Get full edit history for a page |
| `get_version(topic, version)` | Get a specific page version |
| `restore_version(topic, version)` | Restore page to a previous version |
| `get_backlinks(topic)` | Get all pages linking to a topic |
| `get_pages_for_tile(tile_id)` | Get all pages referencing a tile |
| `get_all_cross_refs()` | Get all tile-to-page cross-references |
| `link_tile_to_page(tile_id, topic, type, context)` | Manually create a cross-reference |
| `search_pages(query)` | Search pages by topic or content |
| `list_topics()` | List all page topics |
| `save_to_file(path)` / `load_from_file(path)` | Persist / restore wiki to JSON |

## CLI Reference

```bash
# Tile management
python cli.py store <file.json>                   # Import tiles from JSON
python cli.py query "<expression>"                # Query tiles via DSL

# Fusion
python cli.py fuse <src1.json> [src2.json ...]    # Fuse tiles from sources

# Wiki
python cli.py wiki get <topic>                    # Get a wiki page
python cli.py wiki edit <topic> <content>         # Create or edit a page
python cli.py wiki history <topic>                # Show edit history
python cli.py wiki list                           # List all pages
python cli.py wiki search <query>                 # Search pages
python cli.py wiki delete <topic>                 # Delete a page

# Agent lifecycle
python cli.py onboard                             # Initialize with sample data
python cli.py status                              # Show agent statistics
python cli.py trust-report                        # Show trust fusion report
```

## Related

- **Cocapn Fleet** — the umbrella project: https://github.com/SuperInstance

## License

See the [LICENSE](LICENSE) file for details.

---

<img src="callsign1.jpg" width="128" alt="callsign">
