#!/usr/bin/env python3
"""
Tests for Knowledge Agent — Knowledge Tiles, Trust Fusion, Query, Wiki
=======================================================================

Comprehensive tests covering all core modules:
- knowledge_tiles: KnowledgeTile, TileStore, TileIndex, TileVersion, TileGraph
- tile_trust_fusion: TrustFusionEngine, ConflictResolver, FusionAuditTrail
- tile_query: TileQueryEngine, QueryParser, all query node types
- wiki_database: WikiDatabase, WikiPage, versioning, backlinks

Run: cd /home/z/my-project/fleet/knowledge-agent && python -m pytest tests/ -v
"""

import sys
import os
import json
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_tiles import (
    KnowledgeTile,
    TileDomain,
    TileStore,
    TileIndex,
    TileVersion,
    TileGraph,
)
from tile_trust_fusion import (
    TrustFusionEngine,
    ConflictResolver,
    ConflictStrategy,
    TileTrustConfig,
    FusionAuditTrail,
    FusionEventType,
)
from tile_query import (
    TileQueryEngine,
    QueryParser,
    TagQuery,
    SourceQuery,
    ConfidenceQuery,
    DomainQuery,
    BoolQuery,
    IdQuery,
    ProximityQuery,
    AggregateQueryNode,
    TimeRangeQuery,
    PrerequisiteQuery,
    WildcardQuery,
)
from wiki_database import (
    WikiDatabase,
    WikiPage,
    WikiPageVersion,
    TileWikiLink,
)


# ═══════════════════════════════════════════════════════════════
# Test Helpers
# ═══════════════════════════════════════════════════════════════

def make_tile(
    tid: str = "test_tile",
    name: str = "Test Tile",
    domain: TileDomain = TileDomain.CODE,
    tags: list = None,
    source: str = "test",
    confidence: float = 0.9,
    prerequisites: list = None,
    expires_at: float = 0.0,
) -> KnowledgeTile:
    """Create a test tile with sensible defaults."""
    return KnowledgeTile(
        id=tid,
        name=name,
        domain=domain,
        tags=tags or ["test"],
        source=source,
        confidence=confidence,
        prerequisites=prerequisites or [],
        expires_at=expires_at,
    )


def make_store_with_tiles() -> TileStore:
    """Create a store with a variety of test tiles."""
    store = TileStore()
    tiles = [
        make_tile("t1", "Python Basics", TileDomain.CODE,
                  ["python", "beginner"], "wiki", 0.95),
        make_tile("t2", "Auth Basics", TileDomain.TRUST,
                  ["auth", "security"], "wiki", 0.9),
        make_tile("t3", "API Design", TileDomain.CODE,
                  ["api", "python"], "docs", 0.85),
        make_tile("t4", "Team Skills", TileDomain.SOCIAL,
                  ["teamwork"], "internal", 0.8),
        make_tile("t5", "Creativity", TileDomain.CREATIVE,
                  ["creative"], "external", 0.7),
        make_tile("t6", "Docker Basics", TileDomain.INFRASTRUCTURE,
                  ["docker", "devops"], "wiki", 0.9),
    ]
    for t in tiles:
        store.put(t)
    return store


# ═══════════════════════════════════════════════════════════════
# KnowledgeTile Tests
# ═══════════════════════════════════════════════════════════════

class TestKnowledgeTile:
    """Tests for the KnowledgeTile class."""

    def test_create_tile(self):
        """Basic tile creation."""
        tile = make_tile("auth", "Authentication")
        assert tile.id == "auth"
        assert tile.name == "Authentication"
        assert tile.domain == TileDomain.CODE
        assert tile.tags == ["test"]
        assert tile.confidence == 0.9

    def test_tile_serialization_roundtrip(self):
        """Tile to_dict/from_dict preserves all fields."""
        tile = make_tile("x", "X Tile", TileDomain.TRUST,
                         ["a", "b"], "src", 0.75, ["prereq1"])
        data = tile.to_dict()
        restored = KnowledgeTile.from_dict(data)
        assert restored.id == tile.id
        assert restored.name == tile.name
        assert restored.domain == tile.domain
        assert restored.tags == tile.tags
        assert restored.source == tile.source
        assert restored.confidence == tile.confidence
        assert restored.prerequisites == tile.prerequisites

    def test_prerequisites(self):
        """Prerequisite checking."""
        tile = make_tile("advanced", "Advanced", prerequisites=["basic"])
        assert not tile.has_prerequisites(set())
        assert tile.has_prerequisites({"basic"})
        assert tile.missing_prerequisites({"basic"}) == []
        assert tile.missing_prerequisites(set()) == ["basic"]

    def test_domain_compatibility(self):
        """Cross-domain pairs score higher."""
        t1 = make_tile("a", domain=TileDomain.CODE)
        t2 = make_tile("b", domain=TileDomain.TRUST)
        t3 = make_tile("c", domain=TileDomain.CODE)
        assert t1.domain_compatibility(t2) == 1.0
        assert t1.domain_compatibility(t3) == 0.5

    def test_expiry(self):
        """Expired tiles return is_expired=True."""
        tile = make_tile("exp", expires_at=time.time() - 10)
        assert tile.is_expired()
        tile2 = make_tile("notexp", expires_at=time.time() + 3600)
        assert not tile2.is_expired()
        tile3 = make_tile("noexp", expires_at=0)
        assert not tile3.is_expired()

    def test_clone(self):
        """Clone creates a deep copy."""
        tile = make_tile("orig", tags=["a"])
        clone = tile.clone()
        clone.tags.append("b")
        assert "b" not in tile.tags


# ═══════════════════════════════════════════════════════════════
# TileStore Tests
# ═══════════════════════════════════════════════════════════════

class TestTileStore:
    """Tests for the TileStore class."""

    def test_put_and_get(self):
        """Basic put/get cycle."""
        store = TileStore()
        tile = make_tile("a", "Alpha")
        store.put(tile)
        result = store.get("a")
        assert result is not None
        assert result.id == "a"
        assert result.name == "Alpha"

    def test_get_nonexistent(self):
        """Getting a missing tile returns None."""
        store = TileStore()
        assert store.get("nonexistent") is None

    def test_update_creates_version(self):
        """Updating a tile creates a new version."""
        store = TileStore()
        t1 = make_tile("v", "Version 1")
        store.put(t1)
        assert t1.version == 0

        t2 = make_tile("v", "Version 2")
        store.put(t2, editor="test", note="Updated")
        assert t2.version == 1

        history = store.get_version_history("v")
        assert len(history) == 2
        assert history[0].version == 0
        assert history[1].version == 1
        assert history[1].parent_version == 0

    def test_restore_version(self):
        """Restoring a version creates a new version with old content."""
        store = TileStore()
        t1 = make_tile("r", "Original")
        store.put(t1)

        t2 = make_tile("r", "Modified")
        store.put(t2)

        restored = store.restore_version("r", 0)
        assert restored is not None
        assert restored.content if hasattr(restored, 'content') else restored.name == "Original"
        assert restored.version == 2

    def test_delete(self):
        """Deleting a tile removes it."""
        store = TileStore()
        store.put(make_tile("d", "Delete Me"))
        assert store.delete("d") is True
        assert store.get("d") is None
        assert store.delete("d") is False

    def test_file_persistence(self):
        """Save and load from file."""
        store = TileStore()
        store.put(make_tile("p", "Persistent"))
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            store.save_to_file(path)
            store2 = TileStore()
            store2.load_from_file(path)
            assert store2.get("p") is not None
            assert store2.get("p").name == "Persistent"
        finally:
            os.unlink(path)

    def test_load_tiles_from_json(self):
        """Load tiles from a tile-definition JSON file."""
        store = TileStore()
        data = [
            {"id": "j1", "name": "JSON Tile 1", "tags": ["json"]},
            {"id": "j2", "name": "JSON Tile 2", "domain": "social"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            ids = store.load_tiles_from_json(path)
            assert "j1" in ids
            assert "j2" in ids
            assert store.get("j1") is not None
            assert store.get("j1").tags == ["json"]
            assert store.get("j2").domain == TileDomain.SOCIAL
        finally:
            os.unlink(path)

    def test_expired_tiles_filtered(self):
        """Expired tiles are filtered from get_all."""
        store = TileStore()
        store.put(make_tile("fresh", "Fresh"))
        expired = make_tile("stale", "Stale", expires_at=time.time() - 1)
        store.put(expired)
        assert len(store.get_all()) == 1
        assert store.get_all()[0].id == "fresh"
        assert len(store.get_all(include_expired=True)) == 2


# ═══════════════════════════════════════════════════════════════
# TileIndex Tests
# ═══════════════════════════════════════════════════════════════

class TestTileIndex:
    """Tests for the TileIndex class."""

    def test_tag_search(self):
        """Search by single tag."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_tag("python")
        assert len(results) == 2

    def test_multi_tag_search_all(self):
        """Search requiring all tags."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_tags(["python", "beginner"], match_all=True)
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_multi_tag_search_any(self):
        """Search matching any tag."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_tags(["python", "docker"], match_all=False)
        assert len(results) == 3  # t1, t3, t6

    def test_source_search(self):
        """Search by source."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_source("wiki")
        assert len(results) == 3

    def test_domain_search(self):
        """Search by domain."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_domain("code")
        assert len(results) == 2

    def test_confidence_search(self):
        """Search by confidence range."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        results = index.search_by_confidence(0.9, 1.0)
        assert len(results) == 3
        for t in results:
            assert 0.9 <= t.confidence <= 1.0

    def test_stats(self):
        """Index statistics."""
        store = make_store_with_tiles()
        index = TileIndex(store)
        stats = index.stats()
        assert stats["total_tiles"] == 6
        assert stats["unique_sources"] == 4


# ═══════════════════════════════════════════════════════════════
# TileGraph Tests
# ═══════════════════════════════════════════════════════════════

class TestTileGraph:
    """Tests for the TileGraph class."""

    def test_add_and_cycle_check(self):
        """Adding tiles without cycles works."""
        graph = TileGraph()
        graph.add_tile(make_tile("a"))
        graph.add_tile(make_tile("b", prerequisites=["a"]))
        assert not graph.has_cycle()

    def test_cycle_detection(self):
        """Adding a cycle raises ValueError."""
        graph = TileGraph()
        graph.add_tile(make_tile("a", prerequisites=["b"]))
        graph.add_tile(make_tile("b", prerequisites=["c"]))
        try:
            graph.add_tile(make_tile("c", prerequisites=["a"]))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_depth_computation(self):
        """Depth computation for linear chain."""
        graph = TileGraph()
        graph.add_tile(make_tile("root"))
        graph.add_tile(make_tile("mid", prerequisites=["root"]))
        graph.add_tile(make_tile("leaf", prerequisites=["mid"]))
        depths = graph.compute_depths()
        assert depths["root"] == 0
        assert depths["mid"] == 1
        assert depths["leaf"] == 2

    def test_frontier(self):
        """Frontier tiles have 0 or 1 missing prereq."""
        graph = TileGraph()
        graph.add_tile(make_tile("a"))
        graph.add_tile(make_tile("b"))
        graph.add_tile(make_tile("c", prerequisites=["a", "b"]))
        frontier = graph.compute_frontier({"a"})
        assert "c" in frontier  # missing only b
        assert "b" in frontier  # no prereqs


# ═══════════════════════════════════════════════════════════════
# TrustFusionEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestTrustFusion:
    """Tests for the TrustFusionEngine."""

    def test_fuse_no_conflicts(self):
        """Fusing tiles from different sources without conflicts."""
        engine = TrustFusionEngine()
        src_a = [make_tile("x", "Tile X", source="source_a")]
        src_b = [make_tile("y", "Tile Y", source="source_b")]
        fused, resolutions, conflicts = engine.fuse_tiles({
            "source_a": src_a, "source_b": src_b,
        })
        assert len(fused) == 2
        assert len(conflicts) == 0

    def test_fuse_with_conflict(self):
        """Fusing same tile ID from different sources triggers conflict."""
        engine = TrustFusionEngine()
        src_a = [make_tile("x", "X from A", source="source_a",
                           confidence=0.9)]
        src_b = [make_tile("x", "X from B", source="source_b",
                           confidence=0.7)]
        fused, resolutions, conflicts = engine.fuse_tiles({
            "source_a": src_a, "source_b": src_b,
        })
        assert len(fused) == 1
        assert len(conflicts) == 1
        assert len(resolutions) == 1
        # Highest confidence wins
        assert fused[0].source == "source_a"

    def test_conflict_strategy_most_recent(self):
        """MOST_RECENT strategy picks the most recently updated tile."""
        resolver = ConflictResolver(
            default_strategy=ConflictStrategy.MOST_RECENT,
        )
        engine = TrustFusionEngine(resolver=resolver)

        older = make_tile("x", "Old", source="a", confidence=0.9)
        older.updated_at = 1000.0

        newer = make_tile("x", "New", source="b", confidence=0.5)
        newer.updated_at = 2000.0

        fused, _, _ = engine.fuse_tiles({"a": [older], "b": [newer]})
        assert fused[0].source == "b"

    def test_trust_weighted_aggregate(self):
        """Trust-weighted average of confidence."""
        engine = TrustFusionEngine()
        engine.resolver.set_source_trust("trusted", 1.0)
        engine.resolver.set_source_trust("untrusted", 0.2)

        tiles = [
            make_tile("a", confidence=1.0, source="trusted"),
            make_tile("b", confidence=0.5, source="untrusted"),
        ]
        avg = engine.trust_weighted_aggregate(tiles, "confidence")
        # Weighted: (1.0*1.0 + 0.5*0.2) / (1.0+0.2) = 1.1/1.2 ≈ 0.917
        assert 0.9 < avg < 0.92

    def test_audit_trail_integrity(self):
        """Fusion operations are recorded in the audit trail."""
        engine = TrustFusionEngine()
        engine.fuse_tiles({
            "a": [make_tile("x", source="a")],
            "b": [make_tile("y", source="b")],
        })
        assert engine.audit.entry_count() > 0
        verification = engine.audit.verify_chain()
        assert verification["valid"] is True

    def test_trust_gate_check(self):
        """Trust gate check grants/denies based on trust score."""
        engine = TrustFusionEngine()
        result = engine.check_trust_gate("some_tile", 0.5)
        assert result["granted"] is True  # default gate is 0.3

        result2 = engine.check_trust_gate("some_tile", 0.1)
        assert result2["granted"] is False

    def test_source_reputation(self):
        """Source reputation tracks fusion outcomes."""
        engine = TrustFusionEngine()
        engine.fuse_tiles({
            "a": [make_tile("x", "X", source="a", confidence=0.9)],
            "b": [make_tile("x", "X", source="b", confidence=0.5)],
        })
        rep = engine.get_source_reputation("a")
        assert rep["conflict_wins"] == 1
        assert rep["win_rate"] == 1.0

    def test_fleet_summary(self):
        """Fleet summary includes all components."""
        engine = TrustFusionEngine()
        summary = engine.fleet_summary()
        assert "total_sources" in summary
        assert "audit_entries" in summary
        assert "config" in summary


# ═══════════════════════════════════════════════════════════════
# TileQueryEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestTileQuery:
    """Tests for the TileQueryEngine and QueryParser."""

    def setup_method(self):
        """Create a fresh store/index for each test."""
        self.store = make_store_with_tiles()
        self.index = TileIndex(self.store)
        self.engine = TileQueryEngine(self.store, self.index)
        self.parser = QueryParser()

    def test_tag_query(self):
        """Tag query finds matching tiles."""
        result = self.engine.execute("tag:python")
        assert len(result.tiles) == 2

    def test_source_query(self):
        """Source query finds matching tiles."""
        result = self.engine.execute("source:wiki")
        assert len(result.tiles) == 3

    def test_domain_query(self):
        """Domain query finds matching tiles."""
        result = self.engine.execute("domain:code")
        assert len(result.tiles) == 2

    def test_confidence_gt(self):
        """Confidence greater-than query."""
        result = self.engine.execute("confidence:>0.85")
        assert len(result.tiles) == 4

    def test_confidence_range(self):
        """Confidence range query."""
        result = self.engine.execute("confidence:0.8-0.9")
        # t2=0.9, t3=0.85, t4=0.8, t6=0.9 => 4 tiles
        assert len(result.tiles) == 4

    def test_id_query(self):
        """ID pattern query."""
        result = self.engine.execute("id:t1")
        assert len(result.tiles) == 1
        assert result.tiles[0].id == "t1"

    def test_and_query(self):
        """AND query requires both conditions."""
        result = self.engine.execute("AND(tag:python, source:wiki)")
        assert len(result.tiles) == 1
        assert result.tiles[0].id == "t1"

    def test_or_query(self):
        """OR query matches either condition."""
        result = self.engine.execute("OR(tag:auth, tag:docker)")
        assert len(result.tiles) == 2

    def test_not_query(self):
        """NOT query excludes matching tiles."""
        result = self.engine.execute("NOT(tag:python)")
        assert len(result.tiles) == 4  # 6 total - 2 python

    def test_aggregate_count(self):
        """Count aggregate."""
        result = self.engine.execute("AGG(count, *)")
        assert result.aggregate is not None
        assert result.aggregate.value == 6

    def test_aggregate_avg_confidence(self):
        """Average confidence aggregate."""
        result = self.engine.execute("AGG(avg_confidence, *)")
        assert result.aggregate is not None
        avg = result.aggregate.value
        assert 0.8 < avg < 0.9

    def test_aggregate_top_sources(self):
        """Top sources aggregate."""
        result = self.engine.execute("AGG(top_sources, *)")
        assert result.aggregate is not None
        sources = result.aggregate.value
        assert len(sources) == 4

    def test_aggregate_domain_breakdown(self):
        """Domain breakdown aggregate."""
        result = self.engine.execute("AGG(domain_breakdown, *)")
        assert result.aggregate is not None
        domains = result.aggregate.value
        domain_names = [d["domain"] for d in domains]
        assert "code" in domain_names

    def test_fallback_tag_search(self):
        """Unrecognized expression falls back to tag search."""
        result = self.engine.execute("python")
        assert len(result.tiles) == 2

    def test_prereq_query(self):
        """Prerequisite query finds tiles requiring a specific prereq."""
        store = TileStore()
        store.put(make_tile("a"))
        store.put(make_tile("b", prerequisites=["a"]))
        store.put(make_tile("c", prerequisites=["a"]))
        index = TileIndex(store)
        engine = TileQueryEngine(store, index)
        result = engine.execute("prereq:a")
        assert len(result.tiles) == 2

    def test_proximity_search(self):
        """Proximity search finds related tiles."""
        result = self.engine.execute("near:t1")
        # t3 shares "python" tag and same domain
        assert len(result.tiles) > 0

    def test_execution_time_recorded(self):
        """Query result includes execution time."""
        result = self.engine.execute("tag:python")
        assert result.execution_time_ms >= 0


# ═══════════════════════════════════════════════════════════════
# WikiDatabase Tests
# ═══════════════════════════════════════════════════════════════

class TestWikiDatabase:
    """Tests for the WikiDatabase class."""

    def test_create_page(self):
        """Creating a wiki page."""
        wiki = WikiDatabase()
        page = wiki.create_page("Test", "Hello world")
        assert page.topic == "Test"
        assert page.content == "Hello world"
        assert page.version == 0

    def test_create_duplicate_page_fails(self):
        """Creating a duplicate page raises ValueError."""
        wiki = WikiDatabase()
        wiki.create_page("Test", "Content")
        try:
            wiki.create_page("Test", "Other")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_edit_page(self):
        """Editing a page creates a new version."""
        wiki = WikiDatabase()
        wiki.create_page("Test", "V0")
        updated = wiki.edit_page("Test", "V1", editor="user")
        assert updated.version == 1
        assert updated.content == "V1"

    def test_edit_nonexistent_page_fails(self):
        """Editing a nonexistent page raises ValueError."""
        wiki = WikiDatabase()
        try:
            wiki.edit_page("Nope", "content")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_page_history(self):
        """History records all versions."""
        wiki = WikiDatabase()
        wiki.create_page("H", "v0")
        wiki.edit_page("H", "v1")
        wiki.edit_page("H", "v2")
        history = wiki.get_history("H")
        assert len(history) == 3
        assert history[0].version == 0
        assert history[2].version == 2

    def test_restore_version(self):
        """Restoring a version creates new version with old content."""
        wiki = WikiDatabase()
        wiki.create_page("R", "original")
        wiki.edit_page("R", "modified")
        restored = wiki.restore_version("R", 0)
        assert restored.content == "original"
        assert restored.version == 2

    def test_backlinks(self):
        """Backlinks are computed from [[page:...]] syntax."""
        wiki = WikiDatabase()
        wiki.create_page("Alpha", "Links to [[page:Beta]]")
        wiki.create_page("Beta", "Content here")
        backlinks = wiki.get_backlinks("Beta")
        assert "Alpha" in backlinks

    def test_tile_references(self):
        """Tile references are extracted from [[tile:...]] syntax."""
        wiki = WikiDatabase()
        wiki.create_page("Auth", "See [[tile:basic_auth]] and [[tile:rest_api]]")
        refs = wiki.get_pages_for_tile("basic_auth")
        assert len(refs) == 1
        assert refs[0].page_topic == "Auth"

    def test_manual_tile_link(self):
        """Manually linking a tile to a page."""
        wiki = WikiDatabase()
        wiki.create_page("Code", "Some code content")
        wiki.link_tile_to_page("my_tile", "Code", link_type="example")
        refs = wiki.get_pages_for_tile("my_tile")
        assert len(refs) == 1
        assert refs[0].link_type == "example"

    def test_delete_page(self):
        """Deleting a page cleans up backlinks and references."""
        wiki = WikiDatabase()
        wiki.create_page("A", "Links to [[page:B]]")
        wiki.create_page("B", "Content")
        assert wiki.delete_page("A") is True
        assert wiki.get_page("A") is None
        assert "A" not in wiki.get_backlinks("B")
        assert not wiki.delete_page("A")  # already deleted

    def test_search_pages(self):
        """Search finds pages by topic or content."""
        wiki = WikiDatabase()
        wiki.create_page("Python Guide", "Learn Python programming")
        wiki.create_page("JavaScript", "Web development with JS")
        results = wiki.search_pages("python")
        assert len(results) == 1
        assert results[0].topic == "Python Guide"

    def test_list_topics(self):
        """List all page topics."""
        wiki = WikiDatabase()
        wiki.create_page("A", "")
        wiki.create_page("B", "")
        wiki.create_page("C", "")
        assert wiki.list_topics() == ["A", "B", "C"]

    def test_file_persistence(self):
        """Save and load wiki from file."""
        wiki = WikiDatabase()
        wiki.create_page("Persist", "Test [[tile:my_tile]]")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            wiki.save_to_file(path)
            wiki2 = WikiDatabase()
            wiki2.load_from_file(path)
            assert wiki2.get_page("Persist") is not None
            refs = wiki2.get_pages_for_tile("my_tile")
            assert len(refs) == 1
        finally:
            os.unlink(path)

    def test_edit_updates_backlinks(self):
        """Editing a page updates backlink index."""
        wiki = WikiDatabase()
        wiki.create_page("A", "Links to [[page:B]]")
        wiki.create_page("B", "Content")
        assert "A" in wiki.get_backlinks("B")

        # Remove the link
        wiki.edit_page("A", "No more links")
        assert "A" not in wiki.get_backlinks("B")


# ═══════════════════════════════════════════════════════════════
# Run Tests
# ═══════════════════════════════════════════════════════════════

def run_all_tests() -> bool:
    """Run all test classes and report results."""
    import traceback

    test_classes = [
        TestKnowledgeTile,
        TestTileStore,
        TestTileIndex,
        TestTileGraph,
        TestTrustFusion,
        TestTileQuery,
        TestWikiDatabase,
    ]

    passed = 0
    failed = 0
    errors: list = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in methods:
            full_name = f"{cls.__name__}.{method_name}"
            try:
                # Run setup if it exists
                if hasattr(instance, "setup_method"):
                    instance.setup_method()
                getattr(instance, method_name)()
                passed += 1
                print(f"  PASS  {full_name}")
            except Exception as e:
                failed += 1
                errors.append((full_name, str(e)))
                print(f"  FAIL  {full_name}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, "
          f"{passed + failed} total")
    if errors:
        print(f"\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
