#!/usr/bin/env python3
"""
Knowledge Tiles System — Core Atomic Knowledge Units for the Knowledge Agent
============================================================================

Implements the Knowledge Tiling framework extracted from holodeck-studio,
adapted as a standalone module. Tiles are composable, versioned atoms of
knowledge with metadata (source, confidence, tags, expiry) and lineage
tracking.

Architecture:
    TileDomain        — the five capability domains
    KnowledgeTile     — atomic capability unit with metadata
    TileVersion       — immutable version snapshot for lineage
    TileStore         — persistent store and retrieve tiles
    TileIndex         — search/index tiles by tags, source, confidence
    TileGraph         — directed acyclic graph of prerequisites

Design principles:
1. Tiles are the atoms from which all capabilities are built
2. Every tile carries provenance (source, confidence, lineage)
3. Tiles compose through prerequisite chains
4. Versioning enables safe mutation and rollback
5. Tags and expiry support lifecycle management
"""

from __future__ import annotations

import json
import time
import copy
import hashlib
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# Tile Domain
# ═══════════════════════════════════════════════════════════════

class TileDomain(Enum):
    """The five capability domains that tiles belong to."""
    CODE = "code"
    SOCIAL = "social"
    TRUST = "trust"
    CREATIVE = "creative"
    INFRASTRUCTURE = "infrastructure"


# ═══════════════════════════════════════════════════════════════
# TileVersion — Immutable Version Snapshot
# ═══════════════════════════════════════════════════════════════

@dataclass
class TileVersion:
    """An immutable snapshot of a tile at a point in time.

    Each version stores a content hash for integrity, a timestamp,
    and optional parent version for lineage tracking.

    Attributes:
        version: Monotonically increasing version number.
        content_hash: SHA-256 hash of the tile's content at this version.
        timestamp: Unix timestamp when this version was created.
        parent_version: Version number of the predecessor (None for v0).
        editor: Name/ID of the agent that created this version.
        note: Optional human-readable change note.
        snapshot: Full serialized tile state at this version.
    """
    version: int
    content_hash: str
    timestamp: float = field(default_factory=time.time)
    parent_version: Optional[int] = None
    editor: str = "system"
    note: str = ""
    snapshot: dict = field(default_factory=dict)

    @staticmethod
    def compute_hash(data: dict) -> str:
        """Compute SHA-256 hash of serialized tile data."""
        content = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """Serialize this version to a dictionary."""
        return {
            "version": self.version,
            "content_hash": self.content_hash,
            "timestamp": self.timestamp,
            "parent_version": self.parent_version,
            "editor": self.editor,
            "note": self.note,
            "snapshot": self.snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TileVersion:
        """Deserialize a version from a dictionary."""
        return cls(
            version=data["version"],
            content_hash=data["content_hash"],
            timestamp=data.get("timestamp", time.time()),
            parent_version=data.get("parent_version"),
            editor=data.get("editor", "system"),
            note=data.get("note", ""),
            snapshot=data.get("snapshot", {}),
        )


# ═══════════════════════════════════════════════════════════════
# KnowledgeTile — Atomic Knowledge Unit
# ═══════════════════════════════════════════════════════════════

@dataclass
class KnowledgeTile:
    """A single minimal, composable knowledge atom.

    Extends the holodeck-studio KnowledgeTile with standalone metadata:
    source provenance, confidence scoring, expiry, and lineage tracking.

    Attributes:
        id: Unique identifier (e.g., "basic_movement").
        name: Human-readable name.
        description: What this tile represents.
        domain: Which capability domain this belongs to.
        prerequisites: IDs of tiles that must be acquired first.
        tags: Categorization tags for indexing.
        difficulty: Acquisition difficulty (0.0-1.0, higher = harder).
        source: Provenance — where this tile originated.
        confidence: Confidence in the tile's accuracy (0.0-1.0).
        expires_at: Optional Unix timestamp for tile expiration (0 = never).
        created_at: Timestamp when the tile was created.
        updated_at: Timestamp when the tile was last modified.
        version: Current version number.
        lineage: List of version numbers forming the edit chain.
        metadata: Arbitrary additional key-value metadata.
    """
    id: str
    name: str
    description: str = ""
    domain: TileDomain = TileDomain.CODE
    prerequisites: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    difficulty: float = 0.3
    source: str = "system"
    confidence: float = 1.0
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 0
    lineage: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_prerequisites(self, acquired: Set[str]) -> bool:
        """Check whether all prerequisite tiles are in the acquired set."""
        return all(p in acquired for p in self.prerequisites)

    def missing_prerequisites(self, acquired: Set[str]) -> List[str]:
        """Return prerequisite tile IDs not yet acquired."""
        return [p for p in self.prerequisites if p not in acquired]

    def is_expired(self, now: Optional[float] = None) -> bool:
        """Check whether this tile has expired."""
        if self.expires_at <= 0:
            return False
        check_time = now or time.time()
        return check_time > self.expires_at

    def domain_compatibility(self, other: KnowledgeTile) -> float:
        """Score compatibility of two tiles (0.0-1.0).

        Cross-domain pairs score higher (1.0); same-domain pairs score 0.5.
        """
        return 1.0 if self.domain != other.domain else 0.5

    def to_dict(self) -> dict:
        """Serialize the tile to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain.value,
            "prerequisites": list(self.prerequisites),
            "tags": list(self.tags),
            "difficulty": self.difficulty,
            "source": self.source,
            "confidence": self.confidence,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "lineage": list(self.lineage),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeTile:
        """Deserialize a tile from a dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            domain=TileDomain(data.get("domain", "code")),
            prerequisites=data.get("prerequisites", []),
            tags=data.get("tags", []),
            difficulty=data.get("difficulty", 0.3),
            source=data.get("source", "system"),
            confidence=data.get("confidence", 1.0),
            expires_at=data.get("expires_at", 0.0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            version=data.get("version", 0),
            lineage=data.get("lineage", []),
            metadata=data.get("metadata", {}),
        )

    def clone(self) -> KnowledgeTile:
        """Create a deep copy of this tile."""
        return copy.deepcopy(self)


# ═══════════════════════════════════════════════════════════════
# TileStore — Store and Retrieve Tiles
# ═══════════════════════════════════════════════════════════════

class TileStore:
    """Persistent store for knowledge tiles with versioning.

    Stores tiles in memory with optional JSON persistence. Supports
    CRUD operations with automatic version snapshots on mutation.

    Attributes:
        tiles: Dict of tile_id -> KnowledgeTile.
        versions: Dict of tile_id -> list of TileVersion snapshots.
    """

    def __init__(self) -> None:
        self.tiles: Dict[str, KnowledgeTile] = {}
        self.versions: Dict[str, List[TileVersion]] = {}

    def put(self, tile: KnowledgeTile, editor: str = "system",
            note: str = "") -> KnowledgeTile:
        """Store or update a tile, creating a version snapshot.

        Args:
            tile: The tile to store.
            editor: Name of the agent performing the update.
            note: Optional change note for the version.

        Returns:
            The stored tile (with updated version/timestamp).
        """
        now = time.time()

        if tile.id in self.tiles:
            # Create version snapshot of current state
            existing = self.tiles[tile.id]
            version_num = existing.version + 1
            snapshot = existing.to_dict()
            content_hash = TileVersion.compute_hash(snapshot)
            parent_v = existing.version

            tv = TileVersion(
                version=version_num,
                content_hash=content_hash,
                timestamp=now,
                parent_version=parent_v,
                editor=editor,
                note=note,
                snapshot=snapshot,
            )
            if tile.id not in self.versions:
                self.versions[tile.id] = []
            self.versions[tile.id].append(tv)

            # Update lineage
            tile.version = version_num
            tile.lineage = list(existing.lineage) + [existing.version]
            tile.updated_at = now
        else:
            # First version
            snapshot = tile.to_dict()
            content_hash = TileVersion.compute_hash(snapshot)
            tv = TileVersion(
                version=0,
                content_hash=content_hash,
                timestamp=now,
                editor=editor,
                note=note or "Initial creation",
                snapshot=snapshot,
            )
            self.versions[tile.id] = [tv]
            tile.version = 0
            tile.lineage = []
            tile.created_at = now
            tile.updated_at = now

        self.tiles[tile.id] = tile
        return tile

    def get(self, tile_id: str) -> Optional[KnowledgeTile]:
        """Retrieve a tile by ID. Returns None if not found."""
        tile = self.tiles.get(tile_id)
        if tile and tile.is_expired():
            return None
        return tile

    def get_all(self, include_expired: bool = False) -> List[KnowledgeTile]:
        """Retrieve all tiles, optionally including expired ones."""
        now = time.time()
        result = []
        for tile in self.tiles.values():
            if include_expired or not tile.is_expired(now):
                result.append(tile)
        return result

    def delete(self, tile_id: str) -> bool:
        """Delete a tile. Returns True if it existed."""
        if tile_id in self.tiles:
            del self.tiles[tile_id]
            return True
        return False

    def get_version(self, tile_id: str,
                    version_num: int) -> Optional[TileVersion]:
        """Get a specific version of a tile."""
        version_list = self.versions.get(tile_id, [])
        for v in version_list:
            if v.version == version_num:
                return v
        return None

    def get_version_history(self, tile_id: str) -> List[TileVersion]:
        """Get the full version history for a tile."""
        return list(self.versions.get(tile_id, []))

    def restore_version(self, tile_id: str,
                        version_num: int) -> Optional[KnowledgeTile]:
        """Restore a tile to a specific version.

        Args:
            tile_id: The tile to restore.
            version_num: The version number to restore.

        Returns:
            The restored tile, or None if version not found.
        """
        tv = self.get_version(tile_id, version_num)
        if tv is None:
            return None
        restored = KnowledgeTile.from_dict(tv.snapshot)
        return self.put(restored, editor="system",
                        note=f"Restored from version {version_num}")

    def tile_count(self) -> int:
        """Total number of stored tiles."""
        return len(self.tiles)

    def save_to_file(self, path: str) -> None:
        """Persist all tiles and versions to a JSON file."""
        data = {
            "tiles": {tid: t.to_dict() for tid, t in self.tiles.items()},
            "versions": {
                tid: [v.to_dict() for v in vlist]
                for tid, vlist in self.versions.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_from_file(self, path: str) -> None:
        """Load tiles and versions from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.tiles.clear()
        self.versions.clear()
        for tid, tdata in data.get("tiles", {}).items():
            self.tiles[tid] = KnowledgeTile.from_dict(tdata)
        for tid, vlist in data.get("versions", {}).items():
            self.versions[tid] = [TileVersion.from_dict(v) for v in vlist]

    def load_tiles_from_json(self, path: str) -> List[str]:
        """Load tiles from a tile-definition JSON file.

        The file should be a list of tile dicts or a dict with a "tiles" key.

        Returns:
            List of tile IDs that were loaded.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "tiles" in data:
            tile_list = data["tiles"]
        elif isinstance(data, list):
            tile_list = data
        else:
            tile_list = [data]

        loaded_ids: List[str] = []
        for tdata in tile_list:
            tile = KnowledgeTile.from_dict(tdata)
            self.put(tile, editor="import", note="Imported from file")
            loaded_ids.append(tile.id)

        return loaded_ids

    def to_dict(self) -> dict:
        """Serialize the entire store to a dictionary."""
        return {
            "tile_count": len(self.tiles),
            "tiles": {tid: t.to_dict() for tid, t in self.tiles.items()},
            "versioned_tiles": list(self.versions.keys()),
        }


# ═══════════════════════════════════════════════════════════════
# TileIndex — Search and Index Tiles
# ═══════════════════════════════════════════════════════════════

class TileIndex:
    """Search and index engine for knowledge tiles.

    Maintains inverted indices on tags, source, and domain for fast
    lookup. Supports range queries on confidence and timestamps.

    Attributes:
        store: Reference to the TileStore being indexed.
        _tag_index: Inverted index: tag -> set of tile_ids.
        _source_index: Inverted index: source -> set of tile_ids.
        _domain_index: Inverted index: domain -> set of tile_ids.
    """

    def __init__(self, store: TileStore) -> None:
        self.store = store
        self._tag_index: Dict[str, Set[str]] = {}
        self._source_index: Dict[str, Set[str]] = {}
        self._domain_index: Dict[str, Set[str]] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild all inverted indices from the store."""
        self._tag_index.clear()
        self._source_index.clear()
        self._domain_index.clear()

        for tile in self.store.get_all(include_expired=True):
            # Tag index
            for tag in tile.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(tile.id)
            # Source index
            src = tile.source
            if src not in self._source_index:
                self._source_index[src] = set()
            self._source_index[src].add(tile.id)
            # Domain index
            dom = tile.domain.value
            if dom not in self._domain_index:
                self._domain_index[dom] = set()
            self._domain_index[dom].add(tile.id)

    def refresh(self) -> None:
        """Refresh indices to reflect store changes."""
        self._rebuild()

    def search_by_tag(self, tag: str) -> List[KnowledgeTile]:
        """Find all tiles with a given tag."""
        ids = self._tag_index.get(tag, set())
        return [self.store.get(tid) for tid in ids if self.store.get(tid) is not None]

    def search_by_tags(self, tags: List[str], match_all: bool = True) -> List[KnowledgeTile]:
        """Find tiles matching one or more tags.

        Args:
            tags: List of tags to search.
            match_all: If True, tile must have ALL tags. If False, ANY tag.

        Returns:
            Matching tiles.
        """
        if not tags:
            return self.store.get_all()

        id_sets = [self._tag_index.get(t, set()) for t in tags]

        if match_all:
            if not id_sets:
                return []
            result_ids = id_sets[0]
            for s in id_sets[1:]:
                result_ids = result_ids & s
        else:
            result_ids = set()
            for s in id_sets:
                result_ids = result_ids | s

        return [self.store.get(tid) for tid in result_ids
                if self.store.get(tid) is not None]

    def search_by_source(self, source: str) -> List[KnowledgeTile]:
        """Find all tiles from a given source."""
        ids = self._source_index.get(source, set())
        return [self.store.get(tid) for tid in ids if self.store.get(tid) is not None]

    def search_by_domain(self, domain: str) -> List[KnowledgeTile]:
        """Find all tiles in a given domain."""
        ids = self._domain_index.get(domain, set())
        return [self.store.get(tid) for tid in ids if self.store.get(tid) is not None]

    def search_by_confidence(self, min_conf: float = 0.0,
                             max_conf: float = 1.0) -> List[KnowledgeTile]:
        """Find tiles within a confidence range."""
        results = []
        for tile in self.store.get_all():
            if min_conf <= tile.confidence <= max_conf:
                results.append(tile)
        return results

    def search_by_time_range(self, after: float, before: float) -> List[KnowledgeTile]:
        """Find tiles created within a time range (Unix timestamps)."""
        results = []
        for tile in self.store.get_all():
            if after <= tile.created_at <= before:
                results.append(tile)
        return results

    def search_by_prerequisite(self, prereq_id: str) -> List[KnowledgeTile]:
        """Find all tiles that require a specific prerequisite."""
        results = []
        for tile in self.store.get_all():
            if prereq_id in tile.prerequisites:
                results.append(tile)
        return results

    def search_by_id_pattern(self, pattern: str) -> List[KnowledgeTile]:
        """Find tiles whose ID contains the pattern (substring match)."""
        results = []
        for tile in self.store.get_all():
            if pattern in tile.id:
                results.append(tile)
        return results

    def all_tags(self) -> Set[str]:
        """Get all unique tags across all tiles."""
        return set(self._tag_index.keys())

    def all_sources(self) -> Set[str]:
        """Get all unique sources across all tiles."""
        return set(self._source_index.keys())

    def all_domains(self) -> Set[str]:
        """Get all unique domains across all tiles."""
        return set(self._domain_index.keys())

    def stats(self) -> dict:
        """Get index statistics."""
        return {
            "total_tiles": self.store.tile_count(),
            "unique_tags": len(self._tag_index),
            "unique_sources": len(self._source_index),
            "unique_domains": len(self._domain_index),
            "tag_counts": {t: len(ids) for t, ids in self._tag_index.items()},
            "source_counts": {s: len(ids) for s, ids in self._source_index.items()},
        }


# ═══════════════════════════════════════════════════════════════
# TileGraph — DAG of Prerequisites
# ═══════════════════════════════════════════════════════════════

class TileGraph:
    """Directed acyclic graph of tile prerequisite relationships.

    Extracted and adapted from holodeck-studio. Enforces the grammar
    of tile composition. Computes structural properties like depth,
    bottlenecks, gateways, and frontier tiles.

    Raises:
        ValueError: if adding a tile would create a circular dependency.
    """

    def __init__(self) -> None:
        self.tiles: Dict[str, KnowledgeTile] = {}
        self._depth_cache: Dict[str, int] = {}
        self._depth_cache_valid: bool = False

    def add_tile(self, tile: KnowledgeTile) -> bool:
        """Add a tile, checking for cycles. Raises ValueError on cycle."""
        if self._would_create_cycle(tile.id, tile.prerequisites):
            raise ValueError(
                f"Adding tile '{tile.id}' would create a circular dependency"
            )
        self.tiles[tile.id] = tile
        self._depth_cache_valid = False
        return True

    def remove_tile(self, tile_id: str) -> bool:
        """Remove a tile from the graph. Returns True if it existed."""
        if tile_id in self.tiles:
            del self.tiles[tile_id]
            for tile in self.tiles.values():
                if tile_id in tile.prerequisites:
                    tile.prerequisites.remove(tile_id)
            self._depth_cache_valid = False
            return True
        return False

    def _would_create_cycle(self, tile_id: str,
                            prerequisites: List[str]) -> bool:
        """Check if adding a tile with these prerequisites creates a cycle."""
        visited: Set[str] = set()

        def dfs(current: str) -> bool:
            if current == tile_id:
                return True
            if current in visited:
                return False
            visited.add(current)
            tile = self.tiles.get(current)
            if tile:
                for prereq in tile.prerequisites:
                    if dfs(prereq):
                        return True
            return False

        for prereq in prerequisites:
            if dfs(prereq):
                return True
        return False

    def has_cycle(self) -> bool:
        """Check if the current graph contains circular dependencies."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(tid: str) -> bool:
            visited.add(tid)
            rec_stack.add(tid)
            tile = self.tiles.get(tid)
            if tile:
                for prereq in tile.prerequisites:
                    if prereq not in visited:
                        if dfs(prereq):
                            return True
                    elif prereq in rec_stack:
                        return True
            rec_stack.discard(tid)
            return False

        for tid in self.tiles:
            if tid not in visited:
                if dfs(tid):
                    return True
        return False

    def compute_depths(self) -> Dict[str, int]:
        """Compute the depth of every tile (distance from root tiles)."""
        if self._depth_cache_valid:
            return self._depth_cache
        depths: Dict[str, int] = {}

        def get_depth(tid: str, visited: Set[str]) -> int:
            if tid in depths:
                return depths[tid]
            if tid in visited:
                return 0
            visited.add(tid)
            tile = self.tiles.get(tid)
            if not tile or not tile.prerequisites:
                depths[tid] = 0
                return 0
            max_prereq = 0
            for pid in tile.prerequisites:
                max_prereq = max(max_prereq, get_depth(pid, visited.copy()))
            depths[tid] = max_prereq + 1
            return depths[tid]

        for tid in self.tiles:
            if tid not in depths:
                get_depth(tid, set())
        self._depth_cache = depths
        self._depth_cache_valid = True
        return depths

    def compute_frontier(self, acquired: Set[str]) -> List[str]:
        """Tiles one step from being acquirable (0 or 1 missing prereq)."""
        frontier: List[str] = []
        for tid, tile in self.tiles.items():
            if tid in acquired:
                continue
            missing = tile.missing_prerequisites(acquired)
            if len(missing) <= 1:
                frontier.append(tid)
        return frontier

    def immediate_acquirable(self, acquired: Set[str]) -> List[str]:
        """Tiles whose prerequisites are all already acquired."""
        return [
            tid for tid, tile in self.tiles.items()
            if tid not in acquired and not tile.missing_prerequisites(acquired)
        ]

    def find_bottleneck_tiles(self, top_n: int = 10) -> List[dict]:
        """Identify tiles required by many other tiles."""
        downstream_counts: Dict[str, int] = {}

        def count_downstream(tid: str) -> int:
            if tid in downstream_counts:
                return downstream_counts[tid]
            count = sum(
                1 for other in self.tiles.values()
                if self._requires_tile(other, tid, set())
            )
            downstream_counts[tid] = count
            return count

        for tid in self.tiles:
            count_downstream(tid)

        results = sorted(downstream_counts.items(),
                         key=lambda x: x[1], reverse=True)
        return [{"tile_id": tid, "downstream_count": c}
                for tid, c in results[:top_n]]

    def _requires_tile(self, tile: KnowledgeTile, required_id: str,
                       visited: Set[str]) -> bool:
        """Check if a tile transitively requires another tile."""
        if required_id in tile.prerequisites:
            return True
        visited.add(tile.id)
        for pid in tile.prerequisites:
            if pid in visited:
                continue
            ptile = self.tiles.get(pid)
            if ptile and self._requires_tile(ptile, required_id,
                                              visited.copy()):
                return True
        return False

    def to_dict(self) -> dict:
        """Serialize the graph."""
        return {
            "tiles": {tid: t.to_dict() for tid, t in self.tiles.items()},
            "tile_count": len(self.tiles),
            "depths": self.compute_depths(),
            "has_cycle": self.has_cycle(),
        }

    @classmethod
    def from_tile_list(cls, tiles: List[KnowledgeTile]) -> TileGraph:
        """Construct a TileGraph from a list of KnowledgeTile objects."""
        graph = cls()
        for tile in tiles:
            graph.add_tile(tile)
        return graph
