#!/usr/bin/env python3
"""
Knowledge Agent CLI — Command-Line Interface
============================================

Provides a full CLI for interacting with the knowledge tile system,
trust fusion engine, tile query language, and wiki database.

Usage:
    python cli.py store <file.json>              Store knowledge tiles
    python cli.py query "<expression>"           Query tiles
    python cli.py fuse <source1.json> [source2..] Fuse tiles from sources
    python cli.py wiki get <topic>               Get wiki page
    python cli.py wiki edit <topic> <content>    Edit wiki page
    python cli.py wiki history <topic>           Show edit history
    python cli.py trust-report                   Show trust fusion status
    python cli.py onboard                        Set up the agent
    python cli.py status                         Show agent status
"""

from __future__ import annotations

import sys
import os
import json
import time
from typing import List, Optional

# Ensure the agent's directory is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from knowledge_tiles import (
    KnowledgeTile,
    TileStore,
    TileIndex,
    TileDomain,
    TileVersion,
)
from tile_trust_fusion import (
    TrustFusionEngine,
    ConflictResolver,
    ConflictStrategy,
    TileTrustConfig,
)
from tile_query import TileQueryEngine, QueryParser
from wiki_database import WikiDatabase


# ═══════════════════════════════════════════════════════════════
# Agent State
# ═══════════════════════════════════════════════════════════════

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(AGENT_DIR, "data")
STORE_FILE = os.path.join(DATA_DIR, "tiles.json")
WIKI_FILE = os.path.join(DATA_DIR, "wiki.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


def _ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_store() -> TileStore:
    """Load or create the tile store."""
    _ensure_data_dir()
    store = TileStore()
    if os.path.exists(STORE_FILE):
        store.load_from_file(STORE_FILE)
    return store


def _save_store(store: TileStore) -> None:
    """Persist the tile store."""
    _ensure_data_dir()
    store.save_to_file(STORE_FILE)


def _load_wiki() -> WikiDatabase:
    """Load or create the wiki database."""
    _ensure_data_dir()
    wiki = WikiDatabase()
    if os.path.exists(WIKI_FILE):
        wiki.load_from_file(WIKI_FILE)
    return wiki


def _save_wiki(wiki: WikiDatabase) -> None:
    """Persist the wiki database."""
    _ensure_data_dir()
    wiki.save_to_file(WIKI_FILE)


def _load_config() -> dict:
    """Load agent configuration."""
    _ensure_data_dir()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"onboarded": False, "created_at": time.time()}


def _save_config(config: dict) -> None:
    """Persist agent configuration."""
    _ensure_data_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# ═══════════════════════════════════════════════════════════════
# Output Helpers
# ═══════════════════════════════════════════════════════════════

def _print_json(data: object) -> None:
    """Pretty-print data as JSON."""
    print(json.dumps(data, indent=2, default=str))


def _print_success(message: str, data: object = None) -> None:
    """Print a success message."""
    result = {"status": "ok", "message": message}
    if data is not None:
        result["data"] = data
    _print_json(result)


def _print_error(message: str) -> None:
    """Print an error message."""
    _print_json({"status": "error", "message": message})


# ═══════════════════════════════════════════════════════════════
# Command Handlers
# ═══════════════════════════════════════════════════════════════

def cmd_store(args: List[str]) -> int:
    """Store knowledge tiles from a JSON file.

    Usage: store <file.json>
    """
    if not args:
        _print_error("Usage: store <file.json>")
        return 1

    filepath = args[0]
    if not os.path.exists(filepath):
        _print_error(f"File not found: {filepath}")
        return 1

    store = _load_store()
    try:
        loaded_ids = store.load_tiles_from_json(filepath)
        _save_store(store)
        _print_success(
            f"Stored {len(loaded_ids)} tiles from {filepath}",
            {"tile_ids": loaded_ids, "total_tiles": store.tile_count()},
        )
        return 0
    except Exception as e:
        _print_error(f"Failed to load tiles: {e}")
        return 1


def cmd_query(args: List[str]) -> int:
    """Query tiles using the tile query language.

    Usage: query "<expression>"
    """
    if not args:
        _print_error('Usage: query "<expression>"')
        _print_error('Examples: tag:python, AND(tag:auth, source:wiki), AGG(count, *)')
        return 1

    expression = " ".join(args)
    store = _load_store()
    index = TileIndex(store)
    engine = TileQueryEngine(store, index)

    try:
        result = engine.execute(expression)
        _print_success(
            f"Query returned {len(result.tiles)} tiles "
            f"in {result.execution_time_ms:.1f}ms",
            result.to_dict(),
        )
        return 0
    except Exception as e:
        _print_error(f"Query failed: {e}")
        return 1


def cmd_fuse(args: List[str]) -> int:
    """Fuse tiles from multiple source files.

    Usage: fuse <source1.json> [source2.json ...]
    """
    if not args:
        _print_error("Usage: fuse <source1.json> [source2.json ...]")
        return 1

    # Load tiles from each source file
    sources: dict = {}
    for filepath in args:
        source_name = os.path.splitext(os.path.basename(filepath))[0]
        if not os.path.exists(filepath):
            _print_error(f"File not found: {filepath}")
            return 1

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "tiles" in data:
            tile_list = data["tiles"]
        elif isinstance(data, list):
            tile_list = data
        else:
            tile_list = [data]

        tiles = [KnowledgeTile.from_dict(t) for t in tile_list]
        sources[source_name] = tiles

    # Run fusion
    config = TileTrustConfig()
    resolver = ConflictResolver()
    engine = TrustFusionEngine(config=config, resolver=resolver)

    fused, resolutions, conflict_ids = engine.fuse_tiles(sources)

    # Store fused tiles
    store = _load_store()
    for tile in fused:
        store.put(tile, editor="fusion", note="Fused from multiple sources")
    _save_store(store)

    _print_success(
        f"Fused {len(fused)} tiles from {len(sources)} sources "
        f"({len(conflict_ids)} conflicts resolved)",
        {
            "source_count": len(sources),
            "sources": list(sources.keys()),
            "fused_tile_count": len(fused),
            "conflict_count": len(conflict_ids),
            "conflicts": conflict_ids,
            "resolutions": [r.to_dict() for r in resolutions],
            "audit_valid": engine.audit.verify_chain()["valid"],
        },
    )
    return 0


def cmd_wiki(args: List[str]) -> int:
    """Wiki subcommands.

    Usage:
        wiki get <topic>
        wiki edit <topic> <content>
        wiki history <topic>
        wiki list
        wiki delete <topic>
        wiki search <query>
    """
    if not args:
        _print_error("Usage: wiki <get|edit|history|list|delete|search> [args...]")
        return 1

    subcmd = args[0]

    if subcmd == "get":
        return _wiki_get(args[1:])
    elif subcmd == "edit":
        return _wiki_edit(args[1:])
    elif subcmd == "history":
        return _wiki_history(args[1:])
    elif subcmd == "list":
        return _wiki_list()
    elif subcmd == "delete":
        return _wiki_delete(args[1:])
    elif subcmd == "search":
        return _wiki_search(args[1:])
    else:
        _print_error(f"Unknown wiki subcommand: {subcmd}")
        return 1


def _wiki_get(args: List[str]) -> int:
    """Get a wiki page."""
    if not args:
        _print_error("Usage: wiki get <topic>")
        return 1

    topic = args[0]
    wiki = _load_wiki()
    page = wiki.get_page(topic)
    if page is None:
        _print_error(f"Page '{topic}' not found")
        return 1

    backlinks = wiki.get_backlinks(topic)
    tile_refs = wiki.get_pages_for_tile(page.topic)

    _print_success(f"Page: {topic}", {
        "page": page.to_dict(),
        "backlinks": backlinks,
        "tile_references": [r.to_dict() for r in tile_refs],
    })
    return 0


def _wiki_edit(args: List[str]) -> int:
    """Edit or create a wiki page."""
    if len(args) < 2:
        _print_error("Usage: wiki edit <topic> <content>")
        return 1

    topic = args[0]
    content = " ".join(args[1:])
    wiki = _load_wiki()

    page = wiki.get_page(topic)
    if page is None:
        page = wiki.create_page(topic, content, editor="cli",
                                note="Created via CLI")
        _print_success(f"Created page: {topic}", page.to_dict())
    else:
        page = wiki.edit_page(topic, content, editor="cli",
                              note="Edited via CLI")
        _print_success(f"Updated page: {topic} (v{page.version})",
                      page.to_dict())

    _save_wiki(wiki)
    return 0


def _wiki_history(args: List[str]) -> int:
    """Show edit history for a wiki page."""
    if not args:
        _print_error("Usage: wiki history <topic>")
        return 1

    topic = args[0]
    wiki = _load_wiki()
    history = wiki.get_history(topic)

    if not history:
        _print_error(f"No history found for page '{topic}'")
        return 1

    _print_success(
        f"History for '{topic}' ({len(history)} versions)",
        {"versions": [v.to_dict() for v in history]},
    )
    return 0


def _wiki_list() -> int:
    """List all wiki pages."""
    wiki = _load_wiki()
    topics = wiki.list_topics()
    _print_success(f"{len(topics)} pages", {"topics": topics})
    return 0


def _wiki_delete(args: List[str]) -> int:
    """Delete a wiki page."""
    if not args:
        _print_error("Usage: wiki delete <topic>")
        return 1

    topic = args[0]
    wiki = _load_wiki()
    if wiki.delete_page(topic):
        _save_wiki(wiki)
        _print_success(f"Deleted page: {topic}")
        return 0
    else:
        _print_error(f"Page '{topic}' not found")
        return 1


def _wiki_search(args: List[str]) -> int:
    """Search wiki pages."""
    if not args:
        _print_error("Usage: wiki search <query>")
        return 1

    query = " ".join(args)
    wiki = _load_wiki()
    results = wiki.search_pages(query)

    _print_success(
        f"Found {len(results)} pages matching '{query}'",
        {"pages": [p.to_dict() for p in results]},
    )
    return 0


def cmd_trust_report(args: List[str]) -> int:
    """Show trust fusion status and source reputations."""
    store = _load_store()
    index = TileIndex(store)

    # Gather source trust data
    source_trust: dict = {}
    for tile in store.get_all():
        if tile.source not in source_trust:
            source_trust[tile.source] = {
                "tile_count": 0,
                "avg_confidence": 0.0,
                "total_confidence": 0.0,
            }
        st = source_trust[tile.source]
        st["tile_count"] += 1
        st["total_confidence"] += tile.confidence

    for source, data in source_trust.items():
        if data["tile_count"] > 0:
            data["avg_confidence"] = round(
                data["total_confidence"] / data["tile_count"], 4
            )
        del data["total_confidence"]

    _print_success("Trust report", {
        "total_tiles": store.tile_count(),
        "sources": source_trust,
        "domains": {d: len(index.search_by_domain(d))
                    for d in index.all_domains()},
        "tags": list(index.all_tags()),
        "index_stats": index.stats(),
    })
    return 0


def cmd_onboard(args: List[str]) -> int:
    """Set up the agent with initial data and configuration."""
    config = _load_config()

    if config.get("onboarded"):
        _print_success("Agent already onboarded", config)
        return 0

    # Create data directory
    _ensure_data_dir()

    # Create sample tiles
    store = _load_store()
    sample_tiles = [
        KnowledgeTile(
            id="hello_world",
            name="Hello World",
            description="A basic greeting tile",
            domain=TileDomain.CODE,
            tags=["beginner", "fundamental"],
            source="onboard",
            confidence=1.0,
        ),
        KnowledgeTile(
            id="basic_auth",
            name="Basic Authentication",
            description="Fundamental authentication concepts",
            domain=TileDomain.TRUST,
            tags=["auth", "security", "fundamental"],
            source="onboard",
            confidence=0.9,
            prerequisites=["hello_world"],
        ),
        KnowledgeTile(
            id="rest_api",
            name="REST API Design",
            description="RESTful API design principles",
            domain=TileDomain.CODE,
            tags=["api", "http", "design"],
            source="onboard",
            confidence=0.85,
            prerequisites=["hello_world"],
        ),
        KnowledgeTile(
            id="team_collab",
            name="Team Collaboration",
            description="Effective team collaboration patterns",
            domain=TileDomain.SOCIAL,
            tags=["teamwork", "communication"],
            source="onboard",
            confidence=0.8,
        ),
        KnowledgeTile(
            id="creative_problem_solving",
            name="Creative Problem Solving",
            description="Techniques for creative approaches to problems",
            domain=TileDomain.CREATIVE,
            tags=["creativity", "innovation"],
            source="onboard",
            confidence=0.75,
        ),
    ]

    for tile in sample_tiles:
        store.put(tile, editor="onboard", note="Sample tile for onboarding")
    _save_store(store)

    # Create sample wiki pages
    wiki = _load_wiki()
    wiki.create_page(
        "Getting Started",
        "Welcome to the Knowledge Agent!\n\n"
        "This agent manages knowledge tiles — composable atoms of "
        "knowledge that can be stored, queried, fused, and cross-referenced.\n\n"
        "Key tiles: [[tile:hello_world]], [[tile:basic_auth]], [[tile:rest_api]]\n\n"
        "See also: [[page:Authentication]]",
        editor="onboard",
    )
    wiki.create_page(
        "Authentication",
        "Authentication is a fundamental trust domain concept.\n\n"
        "Prerequisites: [[tile:hello_world]] -> [[tile:basic_auth]]\n\n"
        "Related: [[page:Getting Started]]",
        editor="onboard",
    )
    _save_wiki(wiki)

    # Update config
    config["onboarded"] = True
    config["created_at"] = time.time()
    config["sample_tiles"] = len(sample_tiles)
    _save_config(config)

    _print_success("Agent onboarded successfully", {
        "tiles_created": len(sample_tiles),
        "wiki_pages_created": 2,
        "data_dir": DATA_DIR,
    })
    return 0


def cmd_status(args: List[str]) -> int:
    """Show agent status and statistics."""
    config = _load_config()
    store = _load_store()
    wiki = _load_wiki()
    index = TileIndex(store)

    _print_success("Agent status", {
        "onboarded": config.get("onboarded", False),
        "created_at": config.get("created_at"),
        "tiles": {
            "total": store.tile_count(),
            "by_domain": {d: len(index.search_by_domain(d))
                          for d in index.all_domains()},
            "by_source": {s: len(index.search_by_source(s))
                          for s in index.all_sources()},
            "tags": list(index.all_tags()),
        },
        "wiki": {
            "pages": wiki.page_count(),
            "topics": wiki.list_topics(),
            "cross_refs": sum(
                len(refs) for refs in wiki.get_all_cross_refs().values()
            ),
        },
        "storage": {
            "tiles_file": STORE_FILE,
            "wiki_file": WIKI_FILE,
            "tiles_exists": os.path.exists(STORE_FILE),
            "wiki_exists": os.path.exists(WIKI_FILE),
        },
    })
    return 0


# ═══════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════

COMMANDS: dict = {
    "store": cmd_store,
    "query": cmd_query,
    "fuse": cmd_fuse,
    "wiki": cmd_wiki,
    "trust-report": cmd_trust_report,
    "onboard": cmd_onboard,
    "status": cmd_status,
}


def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Knowledge Agent CLI")
        print("=" * 40)
        print("Commands:")
        for cmd in sorted(COMMANDS.keys()):
            print(f"  {cmd}")
        print()
        print("Run: python cli.py <command> --help")
        return 0

    command = sys.argv[1]
    args = sys.argv[2:]

    handler = COMMANDS.get(command)
    if handler is None:
        _print_error(f"Unknown command: {command}")
        print(f"Available commands: {', '.join(sorted(COMMANDS.keys()))}")
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
