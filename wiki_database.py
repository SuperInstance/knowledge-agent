#!/usr/bin/env python3
"""
Wiki Database — Versioned Knowledge Base with Tile Cross-Referencing
====================================================================

Provides a wiki-like knowledge base where topics are composed from
knowledge tiles. Supports versioning, edit history, automatic backlinks,
and page/tile cross-referencing.

Architecture:
    WikiPage           — a single wiki page with versioned content
    WikiPageVersion    — immutable snapshot of a page version
    WikiDatabase       — the full wiki with CRUD, history, and backlinks
    TileWikiLink       — cross-reference between a tile and a wiki page

Design principles:
1. Every page edit creates an immutable version snapshot
2. Pages can reference tiles; tiles can link back to pages
3. Backlinks are computed automatically from page content
4. Edit history is preserved for full auditability
5. Pages support arbitrary metadata for extensibility
"""

from __future__ import annotations

import re
import json
import time
import hashlib
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# WikiPageVersion — Immutable Page Snapshot
# ═══════════════════════════════════════════════════════════════

@dataclass
class WikiPageVersion:
    """An immutable snapshot of a wiki page at a point in time.

    Attributes:
        version: Version number.
        content_hash: SHA-256 hash of the content.
        content: The page content at this version.
        timestamp: When this version was created.
        editor: Who made this edit.
        note: Edit summary / change note.
        parent_version: Version number of predecessor.
        linked_tile_ids: Tile IDs referenced in this version's content.
        backlinks: Page topics linked from this version's content.
    """
    version: int
    content_hash: str
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    editor: str = "system"
    note: str = ""
    parent_version: Optional[int] = None
    linked_tile_ids: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of page content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "content_hash": self.content_hash,
            "content": self.content,
            "timestamp": self.timestamp,
            "editor": self.editor,
            "note": self.note,
            "parent_version": self.parent_version,
            "linked_tile_ids": self.linked_tile_ids,
            "backlinks": self.backlinks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WikiPageVersion:
        return cls(
            version=data["version"],
            content_hash=data["content_hash"],
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            editor=data.get("editor", "system"),
            note=data.get("note", ""),
            parent_version=data.get("parent_version"),
            linked_tile_ids=data.get("linked_tile_ids", []),
            backlinks=data.get("backlinks", []),
        )


# ═══════════════════════════════════════════════════════════════
# WikiPage — Versioned Wiki Page
# ═══════════════════════════════════════════════════════════════

@dataclass
class WikiPage:
    """A wiki page with versioned content and tile references.

    Attributes:
        topic: The page topic / title (unique identifier).
        content: Current page content.
        created_at: When the page was first created.
        updated_at: When the page was last edited.
        version: Current version number.
        history: List of all versions.
        linked_tile_ids: Tile IDs referenced in current content.
        metadata: Arbitrary key-value metadata.
    """
    topic: str
    content: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 0
    history: List[WikiPageVersion] = field(default_factory=list)
    linked_tile_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "linked_tile_ids": self.linked_tile_ids,
            "metadata": dict(self.metadata),
            "history_count": len(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WikiPage:
        page = cls(
            topic=data["topic"],
            content=data.get("content", ""),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            version=data.get("version", 0),
            linked_tile_ids=data.get("linked_tile_ids", []),
            metadata=data.get("metadata", {}),
        )
        for vdata in data.get("history", []):
            page.history.append(WikiPageVersion.from_dict(vdata))
        return page


# ═══════════════════════════════════════════════════════════════
# TileWikiLink — Cross-Reference
# ═══════════════════════════════════════════════════════════════

@dataclass
class TileWikiLink:
    """A cross-reference between a tile and a wiki page.

    Attributes:
        tile_id: The knowledge tile ID.
        page_topic: The wiki page topic.
        link_type: How the tile relates to the page.
        context: Description of the relationship.
    """
    tile_id: str
    page_topic: str
    link_type: str = "reference"  # reference, prerequisite, example, derived
    context: str = ""

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "page_topic": self.page_topic,
            "link_type": self.link_type,
            "context": self.context,
        }


# ═══════════════════════════════════════════════════════════════
# WikiDatabase — The Full Wiki
# ═══════════════════════════════════════════════════════════════

# Pattern to detect tile references in wiki content: [[tile:id]]
TILE_REF_PATTERN = re.compile(r"\[\[tile:(\w[\w\-]*)\]\]")
# Pattern to detect page backlinks in wiki content: [[page:Topic]]
PAGE_LINK_PATTERN = re.compile(r"\[\[page:([\w\s\-]+)\]\]")


class WikiDatabase:
    """Versioned knowledge base with tile cross-referencing.

    Manages wiki pages with full edit history, automatic backlinks,
    and bidirectional tile/page linking.

    Attributes:
        pages: Dict of topic -> WikiPage.
        cross_refs: Dict of tile_id -> list of TileWikiLink.
        backlink_index: Dict of topic -> set of topics linking to it.
    """

    def __init__(self) -> None:
        self.pages: Dict[str, WikiPage] = {}
        self.cross_refs: Dict[str, List[TileWikiLink]] = {}
        self.backlink_index: Dict[str, Set[str]] = {}

    # ─── Page CRUD ──────────────────────────────────────────

    def create_page(self, topic: str, content: str = "",
                    editor: str = "system",
                    note: str = "Initial creation") -> WikiPage:
        """Create a new wiki page.

        Args:
            topic: The page topic/title.
            content: Initial page content.
            editor: Who is creating the page.
            note: Edit summary.

        Returns:
            The created WikiPage.

        Raises:
            ValueError: If a page with this topic already exists.
        """
        if topic in self.pages:
            raise ValueError(f"Page '{topic}' already exists")

        now = time.time()
        content_hash = WikiPageVersion.compute_hash(content)

        # Extract tile references and page links
        tile_ids = self._extract_tile_refs(content)
        page_links = self._extract_page_links(content)

        version = WikiPageVersion(
            version=0,
            content_hash=content_hash,
            content=content,
            timestamp=now,
            editor=editor,
            note=note,
            linked_tile_ids=tile_ids,
            backlinks=page_links,
        )

        page = WikiPage(
            topic=topic,
            content=content,
            created_at=now,
            updated_at=now,
            version=0,
            history=[version],
            linked_tile_ids=tile_ids,
        )

        self.pages[topic] = page

        # Update backlink index
        for linked_topic in page_links:
            if linked_topic not in self.backlink_index:
                self.backlink_index[linked_topic] = set()
            self.backlink_index[linked_topic].add(topic)

        # Update tile cross-references
        for tid in tile_ids:
            if tid not in self.cross_refs:
                self.cross_refs[tid] = []
            self.cross_refs[tid].append(TileWikiLink(
                tile_id=tid,
                page_topic=topic,
                link_type="reference",
                context=f"Referenced in page '{topic}'",
            ))

        return page

    def get_page(self, topic: str) -> Optional[WikiPage]:
        """Get a wiki page by topic. Returns None if not found."""
        return self.pages.get(topic)

    def edit_page(self, topic: str, content: str,
                  editor: str = "system",
                  note: str = "") -> WikiPage:
        """Edit an existing wiki page, creating a new version.

        Args:
            topic: The page to edit.
            content: New content.
            editor: Who is editing.
            note: Edit summary.

        Returns:
            The updated WikiPage.

        Raises:
            ValueError: If the page does not exist.
        """
        page = self.pages.get(topic)
        if page is None:
            raise ValueError(f"Page '{topic}' not found")

        now = time.time()
        content_hash = WikiPageVersion.compute_hash(content)

        # Extract tile references and page links from new content
        new_tile_ids = self._extract_tile_refs(content)
        new_page_links = self._extract_page_links(content)

        version = WikiPageVersion(
            version=page.version + 1,
            content_hash=content_hash,
            content=content,
            timestamp=now,
            editor=editor,
            note=note or f"Edited to version {page.version + 1}",
            parent_version=page.version,
            linked_tile_ids=new_tile_ids,
            backlinks=new_page_links,
        )

        # Remove old backlinks
        old_links = self._extract_page_links(page.content)
        for old_topic in old_links:
            if old_topic in self.backlink_index:
                self.backlink_index[old_topic].discard(topic)

        # Remove old tile cross-references
        for old_tid in page.linked_tile_ids:
            if old_tid in self.cross_refs:
                self.cross_refs[old_tid] = [
                    r for r in self.cross_refs[old_tid]
                    if r.page_topic != topic
                ]
                if not self.cross_refs[old_tid]:
                    del self.cross_refs[old_tid]

        # Update page
        page.content = content
        page.updated_at = now
        page.version = version.version
        page.linked_tile_ids = new_tile_ids
        page.history.append(version)

        # Add new backlinks
        for linked_topic in new_page_links:
            if linked_topic not in self.backlink_index:
                self.backlink_index[linked_topic] = set()
            self.backlink_index[linked_topic].add(topic)

        # Add new tile cross-references
        for tid in new_tile_ids:
            if tid not in self.cross_refs:
                self.cross_refs[tid] = []
            self.cross_refs[tid].append(TileWikiLink(
                tile_id=tid,
                page_topic=topic,
                link_type="reference",
                context=f"Referenced in page '{topic}'",
            ))

        return page

    def delete_page(self, topic: str) -> bool:
        """Delete a wiki page. Returns True if it existed."""
        page = self.pages.get(topic)
        if page is None:
            return False

        # Clean up backlinks
        for linked_topic in self._extract_page_links(page.content):
            if linked_topic in self.backlink_index:
                self.backlink_index[linked_topic].discard(topic)

        # Clean up tile cross-references
        for tid in page.linked_tile_ids:
            if tid in self.cross_refs:
                self.cross_refs[tid] = [
                    r for r in self.cross_refs[tid]
                    if r.page_topic != topic
                ]

        # Clean up backlink index entries pointing to this topic
        if topic in self.backlink_index:
            del self.backlink_index[topic]

        del self.pages[topic]
        return True

    # ─── History & Versioning ────────────────────────────────

    def get_history(self, topic: str) -> List[WikiPageVersion]:
        """Get the full edit history for a page."""
        page = self.pages.get(topic)
        if page is None:
            return []
        return list(page.history)

    def get_version(self, topic: str,
                    version_num: int) -> Optional[WikiPageVersion]:
        """Get a specific version of a page."""
        page = self.pages.get(topic)
        if page is None:
            return None
        for v in page.history:
            if v.version == version_num:
                return v
        return None

    def restore_version(self, topic: str,
                        version_num: int) -> WikiPage:
        """Restore a page to a specific version's content.

        Creates a new version with the old content.
        """
        v = self.get_version(topic, version_num)
        if v is None:
            raise ValueError(
                f"Version {version_num} not found for page '{topic}'"
            )
        return self.edit_page(
            topic, v.content,
            editor="system",
            note=f"Restored from version {version_num}",
        )

    # ─── Backlinks ──────────────────────────────────────────

    def get_backlinks(self, topic: str) -> List[str]:
        """Get all pages that link to the given topic.

        Returns:
            List of topic strings that reference this topic.
        """
        return sorted(self.backlink_index.get(topic, set()))

    # ─── Tile Cross-Referencing ──────────────────────────────

    def get_pages_for_tile(self, tile_id: str) -> List[TileWikiLink]:
        """Get all wiki pages that reference a tile."""
        return list(self.cross_refs.get(tile_id, []))

    def get_all_cross_refs(self) -> Dict[str, List[TileWikiLink]]:
        """Get all tile-to-page cross-references."""
        return {tid: list(refs) for tid, refs in self.cross_refs.items()}

    def link_tile_to_page(self, tile_id: str, page_topic: str,
                          link_type: str = "reference",
                          context: str = "") -> TileWikiLink:
        """Manually create a cross-reference between a tile and a page.

        Args:
            tile_id: The knowledge tile ID.
            page_topic: The wiki page topic.
            link_type: Type of link (reference, prerequisite, etc.).
            context: Description of the relationship.

        Returns:
            The created TileWikiLink.
        """
        link = TileWikiLink(
            tile_id=tile_id,
            page_topic=page_topic,
            link_type=link_type,
            context=context,
        )
        if tile_id not in self.cross_refs:
            self.cross_refs[tile_id] = []
        self.cross_refs[tile_id].append(link)

        # Also update the page's linked_tile_ids if it exists
        page = self.pages.get(page_topic)
        if page and tile_id not in page.linked_tile_ids:
            page.linked_tile_ids.append(tile_id)

        return link

    # ─── Search ──────────────────────────────────────────────

    def search_pages(self, query: str) -> List[WikiPage]:
        """Search pages by topic name or content (case-insensitive substring).

        Args:
            query: The search string.

        Returns:
            Matching pages.
        """
        query_lower = query.lower()
        results = []
        for page in self.pages.values():
            if query_lower in page.topic.lower():
                results.append(page)
            elif query_lower in page.content.lower():
                results.append(page)
        return results

    def list_topics(self) -> List[str]:
        """List all page topics."""
        return sorted(self.pages.keys())

    def page_count(self) -> int:
        """Total number of pages."""
        return len(self.pages)

    # ─── Content Helpers ─────────────────────────────────────

    @staticmethod
    def _extract_tile_refs(content: str) -> List[str]:
        """Extract tile IDs from wiki content using [[tile:id]] syntax."""
        return TILE_REF_PATTERN.findall(content)

    @staticmethod
    def _extract_page_links(content: str) -> List[str]:
        """Extract page links from wiki content using [[page:Topic]] syntax."""
        return PAGE_LINK_PATTERN.findall(content)

    # ─── Persistence ─────────────────────────────────────────

    def save_to_file(self, path: str) -> None:
        """Persist the wiki to a JSON file."""
        data = {
            "pages": {topic: page.to_dict()
                      for topic, page in self.pages.items()},
            "cross_refs": {
                tid: [r.to_dict() for r in refs]
                for tid, refs in self.cross_refs.items()
            },
            "backlink_index": {
                topic: sorted(links)
                for topic, links in self.backlink_index.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_from_file(self, path: str) -> None:
        """Load the wiki from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.pages.clear()
        self.cross_refs.clear()
        self.backlink_index.clear()

        for topic, pdata in data.get("pages", {}).items():
            self.pages[topic] = WikiPage.from_dict(pdata)

        for tid, refs in data.get("cross_refs", {}).items():
            self.cross_refs[tid] = [TileWikiLink(**r) for r in refs]

        for topic, links in data.get("backlink_index", {}).items():
            self.backlink_index[topic] = set(links)

    def to_dict(self) -> dict:
        """Serialize the wiki database."""
        return {
            "page_count": len(self.pages),
            "topics": self.list_topics(),
            "cross_ref_count": sum(
                len(refs) for refs in self.cross_refs.values()
            ),
            "pages": {topic: page.to_dict()
                      for topic, page in self.pages.items()},
        }
