#!/usr/bin/env python3
"""
Tile Trust Fusion — Trust-Aware Tile Merging Engine
=====================================================

Extracted from holodeck-studio tile_trust_fusion.py and adapted for
standalone use. Merges tiles from multiple sources using trust-weighted
aggregation, resolves conflicts, and maintains a full fusion audit trail.

Architecture:
    TileTrustConfig      — fusion settings (weights, thresholds, decay)
    TrustFusionEngine    — merge tiles from multiple sources
    ConflictResolution   — strategies for handling tile conflicts
    FusionAuditEntry     — individual audit records with SHA-256 trail hash
    FusionAuditTrail     — chained audit log for tamper-evidence

Design principles:
1. Tiles from trusted sources are weighted higher in merges
2. Conflicts are resolved by configurable strategies
3. Every fusion operation is cryptographically auditable
4. Trust can decay over time, requiring re-verification
5. Source reputation accumulates from fusion outcomes
"""

from __future__ import annotations

import hashlib
import json
import time
import copy
import math
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

from knowledge_tiles import KnowledgeTile, TileDomain


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

DEFAULT_TRUST_WEIGHT: float = 1.0
DEFAULT_DECAY_RATE: float = 0.95
TRUST_DIMENSIONS: List[str] = [
    "competence", "reliability", "honesty", "generosity", "reciprocity",
]

DEFAULT_DOMAIN_TRUST_MAP: Dict[str, Dict[str, float]] = {
    "code": {"competence": 1.0, "reliability": 0.5},
    "social": {"generosity": 0.8, "honesty": 0.5, "reciprocity": 0.3},
    "trust": {"honesty": 1.0, "reciprocity": 0.7},
    "creative": {"competence": 0.6, "generosity": 0.5},
    "infrastructure": {"reliability": 1.0, "competence": 0.7},
}


# ═══════════════════════════════════════════════════════════════
# Conflict Resolution Strategies
# ═══════════════════════════════════════════════════════════════

class ConflictStrategy(str, Enum):
    """Strategies for resolving tile conflicts during fusion."""
    HIGHEST_CONFIDENCE = "highest_confidence"
    HIGHEST_TRUST = "highest_trust"
    MOST_RECENT = "most_recent"
    MERGE_TAGS = "merge_tags"
    MANUAL = "manual"


@dataclass
class ConflictResolution:
    """Result of resolving a conflict between two or more tiles.

    Attributes:
        tile_id: The tile ID that had the conflict.
        strategy: The strategy used.
        winner_source: The source that won the conflict.
        merged_tile: The resulting merged tile.
        conflicts_found: List of fields that differed.
    """
    tile_id: str
    strategy: str
    winner_source: str
    merged_tile: KnowledgeTile
    conflicts_found: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "strategy": self.strategy,
            "winner_source": self.winner_source,
            "merged_tile": self.merged_tile.to_dict(),
            "conflicts_found": self.conflicts_found,
        }


class ConflictResolver:
    """Resolves conflicts between tiles from different sources.

    Provides multiple strategies for handling disagreements when
    fusing tiles. Each strategy selects a winner or merges fields.

    Attributes:
        source_trust: Dict of source_name -> trust_score (0.0-1.0).
        default_strategy: The strategy to use when not specified.
    """

    def __init__(
        self,
        source_trust: Optional[Dict[str, float]] = None,
        default_strategy: ConflictStrategy = ConflictStrategy.HIGHEST_CONFIDENCE,
    ) -> None:
        self.source_trust: Dict[str, float] = source_trust or {}
        self.default_strategy = default_strategy

    def set_source_trust(self, source: str, trust: float) -> None:
        """Set the trust score for a source."""
        self.source_trust[source] = max(0.0, min(1.0, trust))

    def get_source_trust(self, source: str) -> float:
        """Get the trust score for a source (0.0 if unknown)."""
        return self.source_trust.get(source, 0.3)

    def resolve(
        self,
        candidates: List[KnowledgeTile],
        strategy: Optional[ConflictStrategy] = None,
    ) -> ConflictResolution:
        """Resolve a conflict between candidate tiles.

        Args:
            candidates: List of competing tiles (same ID, different data).
            strategy: Override strategy. Uses default if None.

        Returns:
            A ConflictResolution with the merged result.
        """
        strat = strategy or self.default_strategy

        if not candidates:
            raise ValueError("No candidates to resolve")
        if len(candidates) == 1:
            return ConflictResolution(
                tile_id=candidates[0].id,
                strategy=strat.value,
                winner_source=candidates[0].source,
                merged_tile=candidates[0].clone(),
            )

        # Detect conflicting fields
        conflicts = self._detect_conflicts(candidates)

        if strat == ConflictStrategy.HIGHEST_CONFIDENCE:
            winner = max(candidates, key=lambda t: t.confidence)
        elif strat == ConflictStrategy.HIGHEST_TRUST:
            winner = max(
                candidates,
                key=lambda t: self.get_source_trust(t.source),
            )
        elif strat == ConflictStrategy.MOST_RECENT:
            winner = max(candidates, key=lambda t: t.updated_at)
        elif strat == ConflictStrategy.MERGE_TAGS:
            winner = self._merge_tags(candidates)
        elif strat == ConflictStrategy.MANUAL:
            # Manual: pick highest confidence but flag for review
            winner = max(candidates, key=lambda t: t.confidence)
        else:
            winner = candidates[0]

        return ConflictResolution(
            tile_id=winner.id,
            strategy=strat.value,
            winner_source=winner.source,
            merged_tile=winner.clone(),
            conflicts_found=conflicts,
        )

    def _detect_conflicts(self, candidates: List[KnowledgeTile]) -> List[str]:
        """Detect which fields differ across candidate tiles."""
        if len(candidates) < 2:
            return []
        conflicts: List[str] = []
        base = candidates[0]
        for tile in candidates[1:]:
            if tile.name != base.name:
                conflicts.append("name")
            if tile.description != base.description:
                conflicts.append("description")
            if tile.domain != base.domain:
                conflicts.append("domain")
            if tile.confidence != base.confidence:
                conflicts.append("confidence")
            if tile.source != base.source:
                conflicts.append("source")
            if set(tile.tags) != set(base.tags):
                conflicts.append("tags")
        return list(set(conflicts))

    def _merge_tags(self, candidates: List[KnowledgeTile]) -> KnowledgeTile:
        """Merge tags from all candidates, pick highest-confidence base."""
        best = max(candidates, key=lambda t: t.confidence)
        all_tags: Set[str] = set()
        for t in candidates:
            all_tags.update(t.tags)
        merged = best.clone()
        merged.tags = sorted(all_tags)
        return merged

    def to_dict(self) -> dict:
        """Serialize the resolver state."""
        return {
            "source_trust": dict(self.source_trust),
            "default_strategy": self.default_strategy.value,
        }


# ═══════════════════════════════════════════════════════════════
# Fusion Audit Trail
# ═══════════════════════════════════════════════════════════════

class FusionEventType(str, Enum):
    """Types of audit events in the fusion engine."""
    TILES_FUSED = "tiles_fused"
    CONFLICT_RESOLVED = "conflict_resolved"
    SOURCE_TRUST_UPDATED = "source_trust_updated"
    TILE_MERGED = "tile_merged"
    FUSION_ROLLBACK = "fusion_rollback"
    AUDIT_VERIFIED = "audit_verified"


@dataclass
class FusionAuditEntry:
    """A single audit record for a fusion operation.

    Uses SHA-256 hash chaining for tamper-evidence, adapted from
    holodeck-studio's TileTrustAuditEntry.

    Attributes:
        event_type: The type of fusion event.
        source: The data source involved.
        tile_ids: Tile IDs affected.
        timestamp: Unix timestamp.
        context: Human-readable context.
        previous_hash: Hash of preceding entry (chain linkage).
        hash: SHA-256 hash of this entry.
        metadata: Additional key-value metadata.
    """
    event_type: str
    source: str = ""
    tile_ids: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    context: str = ""
    previous_hash: str = ""
    hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry."""
        content = json.dumps({
            "event_type": self.event_type,
            "source": self.source,
            "tile_ids": sorted(self.tile_ids),
            "timestamp": self.timestamp,
            "context": self.context,
            "previous_hash": self.previous_hash,
            "metadata": {k: v for k, v in sorted(self.metadata.items())},
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, previous_hash: str = "") -> str:
        """Seal this entry by computing its hash with chain linkage."""
        self.previous_hash = previous_hash
        self.hash = self.compute_hash()
        return self.hash

    def verify(self, previous_hash: str = "") -> bool:
        """Verify the integrity of this entry."""
        if self.hash != self.compute_hash():
            return False
        if previous_hash and self.previous_hash != previous_hash:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "tile_ids": self.tile_ids,
            "timestamp": self.timestamp,
            "context": self.context,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> FusionAuditEntry:
        return cls(
            event_type=data.get("event_type", ""),
            source=data.get("source", ""),
            tile_ids=data.get("tile_ids", []),
            timestamp=data.get("timestamp", time.time()),
            context=data.get("context", ""),
            previous_hash=data.get("previous_hash", ""),
            hash=data.get("hash", ""),
            metadata=data.get("metadata", {}),
        )


class FusionAuditTrail:
    """SHA-256 chained audit trail for all fusion operations.

    Provides tamper-evident logging with chain verification.
    """

    def __init__(self) -> None:
        self.entries: List[FusionAuditEntry] = []

    def append(self, entry: FusionAuditEntry) -> FusionAuditEntry:
        """Append an entry, sealing it with the chain hash."""
        prev = self.entries[-1].hash if self.entries else ""
        entry.seal(prev)
        self.entries.append(entry)
        return entry

    def create_entry(
        self,
        event_type: str,
        source: str = "",
        tile_ids: Optional[List[str]] = None,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FusionAuditEntry:
        """Create, seal, and append a new audit entry."""
        entry = FusionAuditEntry(
            event_type=event_type,
            source=source,
            tile_ids=tile_ids or [],
            context=context,
            metadata=metadata or {},
        )
        return self.append(entry)

    def verify_chain(self) -> dict:
        """Verify the integrity of the entire audit chain.

        Returns:
            Dict with 'valid' (bool), 'entry_count', and 'issues' list.
        """
        if not self.entries:
            return {"valid": True, "entry_count": 0, "issues": []}

        issues: List[str] = []
        prev_hash = ""
        for i, entry in enumerate(self.entries):
            if entry.previous_hash != prev_hash:
                issues.append(f"Entry {i}: hash chain broken")
            if not entry.verify():
                issues.append(f"Entry {i}: hash verification failed")
            prev_hash = entry.hash

        return {
            "valid": len(issues) == 0,
            "entry_count": len(self.entries),
            "issues": issues,
        }

    def get_entries(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query audit entries with optional filters."""
        filtered = self.entries
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if source:
            filtered = [e for e in filtered if e.source == source]
        filtered = filtered[-limit:]
        filtered.reverse()
        return [e.to_dict() for e in filtered]

    def entry_count(self) -> int:
        """Total number of audit entries."""
        return len(self.entries)

    def to_dict(self) -> dict:
        """Serialize the audit trail."""
        return {
            "entry_count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }


# ═══════════════════════════════════════════════════════════════
# TileTrustConfig — Fusion Settings
# ═══════════════════════════════════════════════════════════════

@dataclass
class TileTrustConfig:
    """Configuration for the trust fusion engine.

    Attributes:
        trust_gain_per_tile: Base trust gain when a tile is completed.
        trust_gate_default: Default minimum trust to access any tile.
        trust_gate_overrides: Per-tile trust thresholds.
        decay_rate: Daily exponential decay rate.
        domain_trust_map: Domain-to-trust-dimension mapping.
        propagation_factor: Trust propagation through social connections.
        max_tile_trust_bonus: Cap on trust bonus per chain.
    """
    trust_gain_per_tile: float = 0.05
    trust_gate_default: float = 0.3
    trust_gate_overrides: Dict[str, float] = field(default_factory=dict)
    decay_rate: float = DEFAULT_DECAY_RATE
    domain_trust_map: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {k: dict(v)
                                 for k, v in DEFAULT_DOMAIN_TRUST_MAP.items()}
    )
    propagation_factor: float = 0.5
    max_tile_trust_bonus: float = 0.3

    def get_trust_gate(self, tile_id: str) -> float:
        """Get the trust gate threshold for a tile."""
        return self.trust_gate_overrides.get(tile_id, self.trust_gate_default)

    def get_tile_trust_weights(self, tile_id: str,
                                tile_domain: str) -> Dict[str, float]:
        """Compute trust dimension weights for completing a tile."""
        base = dict(self.domain_trust_map.get(tile_domain, {}))
        return base

    def to_dict(self) -> dict:
        return {
            "trust_gain_per_tile": self.trust_gain_per_tile,
            "trust_gate_default": self.trust_gate_default,
            "trust_gate_overrides": dict(self.trust_gate_overrides),
            "decay_rate": self.decay_rate,
            "domain_trust_map": {k: dict(v)
                                 for k, v in self.domain_trust_map.items()},
            "propagation_factor": self.propagation_factor,
            "max_tile_trust_bonus": self.max_tile_trust_bonus,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TileTrustConfig:
        return cls(
            trust_gain_per_tile=data.get("trust_gain_per_tile", 0.05),
            trust_gate_default=data.get("trust_gate_default", 0.3),
            trust_gate_overrides=data.get("trust_gate_overrides", {}),
            decay_rate=data.get("decay_rate", DEFAULT_DECAY_RATE),
            domain_trust_map=data.get("domain_trust_map",
                                       DEFAULT_DOMAIN_TRUST_MAP),
            propagation_factor=data.get("propagation_factor", 0.5),
            max_tile_trust_bonus=data.get("max_tile_trust_bonus", 0.3),
        )


# ═══════════════════════════════════════════════════════════════
# TrustFusionEngine — Main Fusion Engine
# ═══════════════════════════════════════════════════════════════

class TrustFusionEngine:
    """Main engine for trust-aware tile fusion.

    Merges tiles from multiple sources, resolves conflicts using
    configurable strategies, and maintains a cryptographic audit trail.

    Attributes:
        config: Fusion configuration.
        resolver: Conflict resolution engine.
        audit: Fusion audit trail.
        source_profiles: Per-source trust tracking.
    """

    def __init__(
        self,
        config: Optional[TileTrustConfig] = None,
        resolver: Optional[ConflictResolver] = None,
    ) -> None:
        self.config = config or TileTrustConfig()
        self.resolver = resolver or ConflictResolver()
        self.audit = FusionAuditTrail()
        self.source_profiles: Dict[str, Dict[str, float]] = {}

    def compute_tile_trust_gain(self, tile_id: str,
                                domain: str) -> Dict[str, float]:
        """Compute trust dimension gains for completing a tile.

        Uses the config's domain-trust map. Base gain is
        trust_gain_per_tile multiplied by each dimension's weight.

        Args:
            tile_id: The tile being completed.
            domain: The tile's domain string.

        Returns:
            Dict of trust_dimension -> delta gained.
        """
        weights = self.config.get_tile_trust_weights(tile_id, domain)
        gains: Dict[str, float] = {}
        for dim, weight in weights.items():
            gains[dim] = round(self.config.trust_gain_per_tile * weight, 8)
        return gains

    def fuse_tiles(
        self,
        sources: Dict[str, List[KnowledgeTile]],
        strategy: Optional[ConflictStrategy] = None,
    ) -> Tuple[List[KnowledgeTile], List[ConflictResolution], List[str]]:
        """Fuse tiles from multiple sources into a unified set.

        Args:
            sources: Dict of source_name -> list of tiles from that source.
            strategy: Override conflict strategy.

        Returns:
            Tuple of:
                - List of fused KnowledgeTile (no duplicates).
                - List of ConflictResolution records.
                - List of tile IDs that had conflicts.
        """
        all_tiles: Dict[str, List[KnowledgeTile]] = {}
        resolutions: List[ConflictResolution] = []
        conflict_ids: List[str] = []
        fused: List[KnowledgeTile] = []

        # Group tiles by ID
        for source, tiles in sources.items():
            for tile in tiles:
                if tile.id not in all_tiles:
                    all_tiles[tile.id] = []
                all_tiles[tile.id].append(tile)

        # Resolve or accept each group
        for tile_id, candidates in all_tiles.items():
            if len(candidates) == 1:
                merged = candidates[0].clone()
            else:
                resolution = self.resolver.resolve(candidates, strategy)
                resolutions.append(resolution)
                conflict_ids.append(tile_id)
                merged = resolution.merged_tile

                # Update source trust based on conflict outcome
                for c in candidates:
                    if c.source not in self.source_profiles:
                        self.source_profiles[c.source] = {
                            "fusions": 0, "wins": 0,
                        }
                    self.source_profiles[c.source]["fusions"] += 1
                    if c.source == resolution.winner_source:
                        self.source_profiles[c.source]["wins"] += 1

                self.audit.create_entry(
                    event_type=FusionEventType.CONFLICT_RESOLVED.value,
                    source=",".join(c.source for c in candidates),
                    tile_ids=[tile_id],
                    context=f"Resolved via {resolution.strategy}, "
                            f"winner={resolution.winner_source}",
                    metadata={
                        "strategy": resolution.strategy,
                        "winner": resolution.winner_source,
                        "conflicts": resolution.conflicts_found,
                    },
                )
            fused.append(merged)

        # Log the fusion operation
        all_ids = [t.id for t in fused]
        self.audit.create_entry(
            event_type=FusionEventType.TILES_FUSED.value,
            source=",".join(sources.keys()),
            tile_ids=all_ids,
            context=f"Fused {len(fused)} tiles from "
                    f"{len(sources)} sources, "
                    f"{len(conflict_ids)} conflicts",
            metadata={
                "source_count": len(sources),
                "tile_count": len(fused),
                "conflict_count": len(conflict_ids),
            },
        )

        return fused, resolutions, conflict_ids

    def trust_weighted_aggregate(
        self,
        tiles: List[KnowledgeTile],
        field: str,
    ) -> float:
        """Compute trust-weighted average of a numeric tile field.

        Args:
            tiles: List of tiles to aggregate.
            field: The numeric field to average (e.g., 'confidence').

        Returns:
            Trust-weighted average value.
        """
        if not tiles:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for tile in tiles:
            weight = self.resolver.get_source_trust(tile.source)
            try:
                value = float(getattr(tile, field, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            weighted_sum += value * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def check_trust_gate(
        self,
        tile_id: str,
        agent_trust: float,
    ) -> dict:
        """Check whether a trust score meets a tile's access threshold.

        Args:
            tile_id: The tile being requested.
            agent_trust: The agent's current trust score.

        Returns:
            Dict with 'granted', 'required', 'actual', 'tile_id'.
        """
        threshold = self.config.get_trust_gate(tile_id)
        granted = agent_trust >= threshold

        self.audit.create_entry(
            event_type="trust_gate_check",
            tile_ids=[tile_id],
            context=f"Gate check: {threshold:.2f} required, "
                    f"{agent_trust:.2f} actual, "
                    f"{'GRANTED' if granted else 'DENIED'}",
            metadata={
                "granted": granted,
                "threshold": threshold,
                "actual": agent_trust,
            },
        )

        return {
            "granted": granted,
            "required": threshold,
            "actual": agent_trust,
            "tile_id": tile_id,
        }

    def update_source_trust(self, source: str, delta: float) -> float:
        """Update a source's trust score by a delta.

        Args:
            source: The source name.
            delta: Change in trust (-1.0 to +1.0).

        Returns:
            New trust score.
        """
        current = self.resolver.get_source_trust(source)
        new_trust = max(0.0, min(1.0, current + delta))
        self.resolver.set_source_trust(source, new_trust)

        self.audit.create_entry(
            event_type=FusionEventType.SOURCE_TRUST_UPDATED.value,
            source=source,
            context=f"Trust updated: {current:.3f} -> {new_trust:.3f} "
                    f"(delta={delta:+.3f})",
            metadata={"old_trust": current, "new_trust": new_trust,
                      "delta": delta},
        )

        return new_trust

    def get_source_reputation(self, source: str) -> dict:
        """Get reputation statistics for a source."""
        profile = self.source_profiles.get(source, {})
        fusions = profile.get("fusions", 0)
        wins = profile.get("wins", 0)
        win_rate = wins / fusions if fusions > 0 else 0.0
        trust = self.resolver.get_source_trust(source)
        return {
            "source": source,
            "trust_score": round(trust, 4),
            "total_fusions": fusions,
            "conflict_wins": wins,
            "win_rate": round(win_rate, 4),
        }

    def fleet_summary(self) -> dict:
        """Generate a fleet-wide fusion summary."""
        source_reps = {}
        for source in self.source_profiles:
            source_reps[source] = self.get_source_reputation(source)

        # Add sources from resolver that may not have profiles
        for source in self.resolver.source_trust:
            if source not in source_reps:
                source_reps[source] = self.get_source_reputation(source)

        return {
            "total_sources": len(source_reps),
            "source_reputations": source_reps,
            "audit_entries": self.audit.entry_count(),
            "config": self.config.to_dict(),
            "audit_valid": self.audit.verify_chain()["valid"],
        }

    def to_dict(self) -> dict:
        """Serialize the fusion engine state."""
        return {
            "config": self.config.to_dict(),
            "resolver": self.resolver.to_dict(),
            "source_profiles": dict(self.source_profiles),
            "audit": self.audit.to_dict(),
        }
