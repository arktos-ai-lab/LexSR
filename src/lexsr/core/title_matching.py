"""
Fuzzy title matching for resolving a raw law reference (e.g. "de
Arbeidswet 1963", "Grondwet") to a real Work in the store.

Needed because canonical/abbreviation-derived slugs (e.g. "grondwet-1987"
from the citation resolver's abbreviation registry) frequently don't match
the filename-derived work IDs that real scraped/OCR'd documents get
(e.g. "grondwet-met-mvt-4fb9cced"). Originally written for amendment
base-law resolution (consolidation/engine.py); the citation extractor
needs the exact same matching for the exact same reason, so it lives here
as a shared utility instead of being duplicated.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .models import Work

_STOP_WORDS = re.compile(r'\b(?:de|het|van|der|den|een|the)\b', re.I)

# A very short normalized string (OCR noise, a stray single letter) is a
# substring of almost everything, so require a minimum length before
# trusting either direction of the containment check.
MIN_SUBSTRING_LEN = 4


def normalize_title_ref(raw: str) -> str:
    """Normalize a law reference/title for fuzzy matching."""
    s = _STOP_WORDS.sub('', raw).strip()
    return re.sub(r'\s+', ' ', s.lower())


def resolve_work_by_title(
    raw_ref: str, works: List[Work]
) -> Optional[Work]:
    """
    Resolve a raw law reference to a Work by fuzzy title matching.

    Strategy (in order):
    1. Exact title match
    2. Normalized title (strip stop words)
    3. Substring: normalized ref <-> normalized title (length-guarded)
    4. Year + keyword match

    `works` is a pre-fetched list (e.g. from store.list_works()) rather
    than a store, so callers doing many lookups (citation extraction over
    thousands of fragments) can fetch it once instead of re-querying per
    call.
    """
    norm_ref = normalize_title_ref(raw_ref)

    for work in works:
        if work.title.strip().lower() == raw_ref.strip().lower():
            return work
        if normalize_title_ref(work.title) == norm_ref:
            return work

    if len(norm_ref) >= MIN_SUBSTRING_LEN:
        for work in works:
            norm_title = normalize_title_ref(work.title)
            if len(norm_title) < MIN_SUBSTRING_LEN:
                continue
            if norm_ref in norm_title or norm_title in norm_ref:
                return work

    year_m = re.search(r'\b(\d{4})\b', raw_ref)
    if year_m:
        year = year_m.group(1)
        words = [w for w in norm_ref.split() if len(w) > 3]
        for work in works:
            if year in work.title:
                norm_t = normalize_title_ref(work.title)
                if any(w in norm_t for w in words):
                    return work

    return None
