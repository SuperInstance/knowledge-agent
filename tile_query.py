#!/usr/bin/env python3
"""
Tile Query Language — Expressive Search for Knowledge Tiles
===========================================================

Provides a flexible query DSL for searching and aggregating knowledge tiles.
Supports boolean operators, proximity search, and aggregate queries.

Architecture:
    QueryParser       — parses query expression strings into AST nodes
    QueryNode         — abstract base for query AST nodes
    TagQuery          — match tiles by tag
    SourceQuery       — match tiles by source
    ConfidenceQuery   — match tiles by confidence range
    TimeRangeQuery    — match tiles by creation time range
    DomainQuery       — match tiles by domain
    IdQuery           — match tiles by ID pattern
    BoolQuery         — AND / OR / NOT combinators
    ProximityQuery    — find tiles related to a seed tile
    AggregateQuery    — count, avg, top-sources over results
    TileQueryEngine   — executes queries against a TileStore + TileIndex
"""

from __future__ import annotations

import re
import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)
from dataclasses import dataclass, field
from enum import Enum

from knowledge_tiles import KnowledgeTile, TileStore, TileIndex


# ═══════════════════════════════════════════════════════════════
# Query AST Nodes
# ═══════════════════════════════════════════════════════════════

class QueryNode:
    """Abstract base class for query AST nodes."""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        """Execute this query node against the store/index."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


@dataclass
class TagQuery(QueryNode):
    """Match tiles that have a specific tag."""
    tag: str = ""
    match_all: bool = False

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        if self.match_all:
            return index.search_by_tags([self.tag], match_all=True)
        return index.search_by_tag(self.tag)

    def __repr__(self) -> str:
        return f"TagQuery(tag={self.tag!r})"


@dataclass
class SourceQuery(QueryNode):
    """Match tiles from a specific source."""
    source: str = ""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_source(self.source)

    def __repr__(self) -> str:
        return f"SourceQuery(source={self.source!r})"


@dataclass
class ConfidenceQuery(QueryNode):
    """Match tiles within a confidence range."""
    min_conf: float = 0.0
    max_conf: float = 1.0

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_confidence(self.min_conf, self.max_conf)

    def __repr__(self) -> str:
        return f"ConfidenceQuery(min={self.min_conf}, max={self.max_conf})"


@dataclass
class TimeRangeQuery(QueryNode):
    """Match tiles created within a time range (Unix timestamps)."""
    after: float = 0.0
    before: float = float("inf")

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_time_range(self.after, self.before)

    def __repr__(self) -> str:
        return f"TimeRangeQuery(after={self.after}, before={self.before})"


@dataclass
class DomainQuery(QueryNode):
    """Match tiles in a specific domain."""
    domain: str = ""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_domain(self.domain)

    def __repr__(self) -> str:
        return f"DomainQuery(domain={self.domain!r})"


@dataclass
class IdQuery(QueryNode):
    """Match tiles whose ID contains a pattern (substring match)."""
    pattern: str = ""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_id_pattern(self.pattern)

    def __repr__(self) -> str:
        return f"IdQuery(pattern={self.pattern!r})"


@dataclass
class BoolQuery(QueryNode):
    """Boolean combinator: AND, OR, NOT over child queries."""
    operator: str = "AND"  # AND, OR, NOT
    children: List[QueryNode] = field(default_factory=list)

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        if not self.children:
            return []

        if self.operator == "AND":
            result_ids: Optional[Set[str]] = None
            for child in self.children:
                child_tiles = child.execute(store, index)
                child_ids = {t.id for t in child_tiles}
                if result_ids is None:
                    result_ids = child_ids
                else:
                    result_ids = result_ids & child_ids
            if result_ids is None:
                return []
            return [t for t in child_tiles if t.id in result_ids]

        elif self.operator == "OR":
            all_tiles: Dict[str, KnowledgeTile] = {}
            for child in self.children:
                for tile in child.execute(store, index):
                    all_tiles[tile.id] = tile
            return list(all_tiles.values())

        elif self.operator == "NOT":
            if len(self.children) != 1:
                return []
            exclude_ids = {t.id for t in self.children[0].execute(store, index)}
            return [t for t in store.get_all() if t.id not in exclude_ids]

        return []

    def __repr__(self) -> str:
        return f"BoolQuery({self.operator}, {len(self.children)} children)"


@dataclass
class PrerequisiteQuery(QueryNode):
    """Match tiles that require a specific prerequisite."""
    prereq_id: str = ""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return index.search_by_prerequisite(self.prereq_id)

    def __repr__(self) -> str:
        return f"PrerequisiteQuery(prereq={self.prereq_id!r})"


@dataclass
class WildcardQuery(QueryNode):
    """Match all tiles (wildcard)."""

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        return store.get_all()

    def __repr__(self) -> str:
        return "WildcardQuery(*)"


@dataclass
class ProximityQuery(QueryNode):
    """Find tiles related to a seed tile.

    Relatedness is computed via shared tags, same domain, and
    prerequisite relationships (both directions).

    Attributes:
        seed_id: The seed tile's ID.
        max_results: Maximum number of related tiles to return.
        tag_weight: Weight for shared-tag similarity.
        domain_weight: Weight for same-domain bonus.
        prereq_weight: Weight for prerequisite linkage.
    """
    seed_id: str = ""
    max_results: int = 10
    tag_weight: float = 0.4
    domain_weight: float = 0.3
    prereq_weight: float = 0.3

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        seed = store.get(self.seed_id)
        if seed is None:
            return []

        all_tiles = store.get_all()
        scored: List[Tuple[float, KnowledgeTile]] = []

        for tile in all_tiles:
            if tile.id == self.seed_id:
                continue

            score = 0.0

            # Shared tags
            seed_tags = set(seed.tags)
            tile_tags = set(tile.tags)
            if seed_tags and tile_tags:
                shared = seed_tags & tile_tags
                total = seed_tags | tile_tags
                score += (len(shared) / len(total)) * self.tag_weight

            # Same domain
            if tile.domain == seed.domain:
                score += self.domain_weight

            # Prerequisite linkage (bidirectional)
            if self.seed_id in tile.prerequisites:
                score += self.prereq_weight
            if tile.id in seed.prerequisites:
                score += self.prereq_weight

            if score > 0:
                scored.append((score, tile))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [tile for _, tile in scored[:self.max_results]]

    def __repr__(self) -> str:
        return f"ProximityQuery(seed={self.seed_id!r})"


# ═══════════════════════════════════════════════════════════════
# Aggregate Query Results
# ═══════════════════════════════════════════════════════════════

class AggregateFunction(str, Enum):
    """Supported aggregate functions."""
    COUNT = "count"
    AVG_CONFIDENCE = "avg_confidence"
    TOP_SOURCES = "top_sources"
    TAG_BREAKDOWN = "tag_breakdown"
    DOMAIN_BREAKDOWN = "domain_breakdown"


@dataclass
class AggregateResult:
    """Result of an aggregate query.

    Attributes:
        function: The aggregate function used.
        value: The computed value (type varies by function).
        raw_tiles: The tiles that were aggregated.
    """
    function: str
    value: Any = None
    raw_tiles: List[KnowledgeTile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "value": self.value,
            "tile_count": len(self.raw_tiles),
        }


# ═══════════════════════════════════════════════════════════════
# Query Parser
# ═══════════════════════════════════════════════════════════════

class QueryParser:
    """Parses query expression strings into QueryNode AST.

    Supported syntax:
        tag:python                    — tiles with tag "python"
        source:wikipedia              — tiles from source "wikipedia"
        domain:code                   — tiles in domain "code"
        confidence:>0.8              — tiles with confidence > 0.8
        confidence:<0.3              — tiles with confidence < 0.3
        confidence:0.5-0.9           — tiles with confidence in [0.5, 0.9]
        after:1700000000             — tiles created after timestamp
        before:1700000000            — tiles created before timestamp
        id:auth                       — tiles with "auth" in their ID
        prereq:basic_auth             — tiles requiring "basic_auth"
        near:tile_id                  — tiles related to seed tile
        AND(tag:python, source:wiki)  — boolean AND
        OR(tag:python, tag:rust)     — boolean OR
        NOT(tag:deprecated)           — boolean NOT
        AGG(count, tag:python)        — aggregate query
        AGG(avg_confidence, domain:code)
        AGG(top_sources, tag:python)
        AGG(tag_breakdown, *)
    """

    def parse(self, expression: str) -> QueryNode:
        """Parse a query expression into a QueryNode AST.

        Args:
            expression: The query expression string.

        Returns:
            A QueryNode ready for execution.

        Raises:
            ValueError: If the expression cannot be parsed.
        """
        expression = expression.strip()

        # Check for aggregate queries
        agg_match = re.match(r"^AGG\((\w+),\s*(.+)\)$", expression, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1)
            inner_expr = agg_match.group(2).strip()
            # Wrap in a special aggregate marker
            return AggregateQueryNode(
                function=func_name,
                inner=self.parse(inner_expr),
            )

        # Check for boolean operators
        and_match = re.match(r"^AND\((.+)\)$", expression)
        if and_match:
            children = self._split_args(and_match.group(1))
            return BoolQuery(operator="AND",
                             children=[self.parse(c) for c in children])

        or_match = re.match(r"^OR\((.+)\)$", expression)
        if or_match:
            children = self._split_args(or_match.group(1))
            return BoolQuery(operator="OR",
                             children=[self.parse(c) for c in children])

        not_match = re.match(r"^NOT\((.+)\)$", expression)
        if not_match:
            child = self.parse(not_match.group(1).strip())
            return BoolQuery(operator="NOT", children=[child])

        # Field-specific queries
        tag_match = re.match(r"^tag:(.+)$", expression)
        if tag_match:
            return TagQuery(tag=tag_match.group(1).strip())

        source_match = re.match(r"^source:(.+)$", expression)
        if source_match:
            return SourceQuery(source=source_match.group(1).strip())

        domain_match = re.match(r"^domain:(.+)$", expression)
        if domain_match:
            return DomainQuery(domain=domain_match.group(1).strip())

        conf_match = re.match(r"^confidence:(.+)$", expression)
        if conf_match:
            return self._parse_confidence(conf_match.group(1).strip())

        after_match = re.match(r"^after:(.+)$", expression)
        if after_match:
            ts = float(after_match.group(1).strip())
            return TimeRangeQuery(after=ts, before=float("inf"))

        before_match = re.match(r"^before:(.+)$", expression)
        if before_match:
            ts = float(before_match.group(1).strip())
            return TimeRangeQuery(after=0.0, before=ts)

        id_match = re.match(r"^id:(.+)$", expression)
        if id_match:
            return IdQuery(pattern=id_match.group(1).strip())

        prereq_match = re.match(r"^prereq:(.+)$", expression)
        if prereq_match:
            return PrerequisiteQuery(prereq_id=prereq_match.group(1).strip())

        near_match = re.match(r"^near:(.+)$", expression)
        if near_match:
            return ProximityQuery(seed_id=near_match.group(1).strip())

        # Fallback: treat as tag search (wildcard * = all tiles)
        if expression.strip() == "*":
            return WildcardQuery()
        return TagQuery(tag=expression)

    def _parse_confidence(self, spec: str) -> ConfidenceQuery:
        """Parse a confidence specification like '>0.8', '<0.3', or '0.5-0.9'."""
        gt_match = re.match(r"^>(\d*\.?\d+)$", spec)
        if gt_match:
            return ConfidenceQuery(min_conf=float(gt_match.group(1)),
                                  max_conf=1.0)

        lt_match = re.match(r"^<(\d*\.?\d+)$", spec)
        if lt_match:
            return ConfidenceQuery(min_conf=0.0,
                                  max_conf=float(lt_match.group(1)))

        range_match = re.match(r"^(\d*\.?\d+)\s*-\s*(\d*\.?\d+)$", spec)
        if range_match:
            return ConfidenceQuery(
                min_conf=float(range_match.group(1)),
                max_conf=float(range_match.group(2)),
            )

        # Exact match
        try:
            val = float(spec)
            return ConfidenceQuery(min_conf=val, max_conf=val)
        except ValueError:
            return ConfidenceQuery()

    def _split_args(self, args_str: str) -> List[str]:
        """Split comma-separated arguments, respecting nested parentheses."""
        args: List[str] = []
        depth = 0
        current = ""
        for ch in args_str:
            if ch == "(" :
                depth += 1
                current += ch
            elif ch == ")":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            args.append(current.strip())
        return args


@dataclass
class AggregateQueryNode(QueryNode):
    """Wraps an inner query with an aggregate function."""
    function: str = "count"
    inner: QueryNode = field(default_factory=TagQuery)

    def execute(self, store: TileStore, index: TileIndex) -> List[KnowledgeTile]:
        # Aggregate queries return the raw tiles; aggregation is done
        # by the TileQueryEngine
        return self.inner.execute(store, index)

    def __repr__(self) -> str:
        return f"AggregateQueryNode(function={self.function!r})"


# ═══════════════════════════════════════════════════════════════
# TileQueryEngine — Execute Queries
# ═══════════════════════════════════════════════════════════════

@dataclass
class QueryResult:
    """Result of executing a query.

    Attributes:
        tiles: The matching tiles.
        aggregate: Optional aggregate result.
        query_expression: The original query string.
        execution_time_ms: How long the query took.
    """
    tiles: List[KnowledgeTile] = field(default_factory=list)
    aggregate: Optional[AggregateResult] = None
    query_expression: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict:
        result: dict = {
            "query": self.query_expression,
            "tile_count": len(self.tiles),
            "tiles": [t.to_dict() for t in self.tiles],
            "execution_time_ms": round(self.execution_time_ms, 2),
        }
        if self.aggregate:
            result["aggregate"] = self.aggregate.to_dict()
        return result


class TileQueryEngine:
    """Executes tile queries against a TileStore and TileIndex.

    Supports parsed AST queries, string expressions, and aggregate queries.

    Attributes:
        store: The tile store to query against.
        index: The tile index for fast lookup.
        parser: The query expression parser.
    """

    def __init__(self, store: TileStore, index: TileIndex) -> None:
        self.store = store
        self.index = index
        self.parser = QueryParser()

    def execute(self, query: str) -> QueryResult:
        """Execute a query expression string.

        Args:
            query: The query expression.

        Returns:
            A QueryResult with matching tiles and optional aggregates.
        """
        start = time.time()
        ast = self.parser.parse(query)

        # Check for aggregate queries
        if isinstance(ast, AggregateQueryNode):
            tiles = ast.inner.execute(self.store, self.index)
            agg = self._compute_aggregate(ast.function, tiles)
            elapsed = (time.time() - start) * 1000
            return QueryResult(
                tiles=tiles,
                aggregate=agg,
                query_expression=query,
                execution_time_ms=elapsed,
            )

        tiles = ast.execute(self.store, self.index)
        elapsed = (time.time() - start) * 1000
        return QueryResult(
            tiles=tiles,
            query_expression=query,
            execution_time_ms=elapsed,
        )

    def execute_ast(self, node: QueryNode) -> QueryResult:
        """Execute a pre-parsed QueryNode AST."""
        start = time.time()
        tiles = node.execute(self.store, self.index)
        elapsed = (time.time() - start) * 1000
        return QueryResult(tiles=tiles, execution_time_ms=elapsed)

    def find_related(self, tile_id: str,
                     max_results: int = 10) -> List[KnowledgeTile]:
        """Find tiles related to a seed tile using proximity search."""
        query = ProximityQuery(seed_id=tile_id, max_results=max_results)
        return query.execute(self.store, self.index)

    def _compute_aggregate(self, function: str,
                           tiles: List[KnowledgeTile]) -> AggregateResult:
        """Compute an aggregate function over query results."""
        func_lower = function.lower()

        if func_lower == "count":
            return AggregateResult(
                function=function,
                value=len(tiles),
                raw_tiles=tiles,
            )

        elif func_lower == "avg_confidence":
            if not tiles:
                return AggregateResult(function=function, value=0.0,
                                      raw_tiles=tiles)
            avg = sum(t.confidence for t in tiles) / len(tiles)
            return AggregateResult(
                function=function,
                value=round(avg, 4),
                raw_tiles=tiles,
            )

        elif func_lower == "top_sources":
            source_counts: Dict[str, int] = {}
            for t in tiles:
                source_counts[t.source] = source_counts.get(t.source, 0) + 1
            sorted_sources = sorted(source_counts.items(),
                                    key=lambda x: x[1], reverse=True)
            return AggregateResult(
                function=function,
                value=[{"source": s, "count": c}
                       for s, c in sorted_sources],
                raw_tiles=tiles,
            )

        elif func_lower == "tag_breakdown":
            tag_counts: Dict[str, int] = {}
            for t in tiles:
                for tag in t.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            sorted_tags = sorted(tag_counts.items(),
                                 key=lambda x: x[1], reverse=True)
            return AggregateResult(
                function=function,
                value=[{"tag": t, "count": c}
                       for t, c in sorted_tags],
                raw_tiles=tiles,
            )

        elif func_lower == "domain_breakdown":
            domain_counts: Dict[str, int] = {}
            for t in tiles:
                d = t.domain.value
                domain_counts[d] = domain_counts.get(d, 0) + 1
            sorted_domains = sorted(domain_counts.items(),
                                    key=lambda x: x[1], reverse=True)
            return AggregateResult(
                function=function,
                value=[{"domain": d, "count": c}
                       for d, c in sorted_domains],
                raw_tiles=tiles,
            )

        return AggregateResult(function=function, value=None, raw_tiles=tiles)
