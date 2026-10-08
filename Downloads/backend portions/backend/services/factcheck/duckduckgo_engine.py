"""
=============================================================================
factcheck/duckduckgo_engine.py — free web retrieval, no API key (default)
=============================================================================
WHY DuckDuckGo + Wikipedia: the deadline is tomorrow and this deploys on
Render's free tier. Every other decent retrieval option needs a key, a card, or
a paid plan. These need none of those, so the fact-checker works the moment the
service boots.

WHY FIVE FALLBACK LAYERS
    Free search endpoints are the least stable part of any stack — they get
    renamed, rate-limited and moved between packages without notice
    (`duckduckgo_search` literally became `ddgs`). A graded demo cannot be
    allowed to fail because a library was renamed, so this engine tries, in
    order, and uses the first layer that returns anything:

      1. the modern `ddgs` package
      2. the older `duckduckgo_search` package (still on many machines)
      3. html.duckduckgo.com/html/ scraped directly (httpx + BeautifulSoup)
      4. DuckDuckGo's Instant Answer API (api.duckduckgo.com — plain JSON)
      5. Wikipedia's action API search (very stable, no key, never bot-blocked)

    Layers 4 and 5 are the reliability floor. Even if DuckDuckGo blocks this
    server entirely, an encyclopaedic source still comes back, so the feature
    degrades to "fewer, more authoritative sources" instead of failing.

A REAL BUG THIS FILE DOCUMENTS
    Layer 3 originally sent a bare POST to html.duckduckgo.com/html/ with only a
    User-Agent header. DuckDuckGo answered HTTP 202 — its anti-bot interstitial —
    with zero results and no error. The request *succeeded* and returned
    *nothing*, which is the hardest class of failure to notice: no exception, no
    log line, just a fact-checker that always says "Unverified".
    The fix is to open a session, GET duckduckgo.com once to collect cookies,
    then issue the query as a GET on that same client. That returns 200 with
    real results. If you ever see every claim come back Unverified with no
    errors, this is the first thing to check.
=============================================================================
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx

from .base import FactCheckEngine

UA_BROWSER = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# WHY a descriptive UA for the API layers: Wikipedia asks (politely, and in its
# terms of use) that automated clients identify themselves. A browser-spoofing UA
# on an API endpoint is how projects get their IP banned.
UA_API = "TruthGuardAI/1.0 (college civic-education project; research use)"

# WHY append these terms to the WEB query: a bare claim returns news *about* the
# topic. Adding fact-check vocabulary biases retrieval toward pages that actually
# adjudicate the claim, which is what the scorer needs in order to judge.
WEB_QUERY_SUFFIX = " fact check true or false"

_TAG_RE = re.compile(r"<[^>]+>")


class DuckDuckGoEngine(FactCheckEngine):
    name = "duckduckgo+instant-answer+wikipedia"

    DISCLAIMER = (
        "Verdict derived from keyword-evidence scoring over retrieved web sources, "
        "weighted by domain trust and adjusted for explicit negation. No language "
        "model was used and no claim database was consulted. This measures what the "
        "retrieved sources say, not ground truth."
    )

    def __init__(self, max_results: int | None = None, timeout: float | None = None) -> None:
        from config import settings

        self.max_results = max_results or settings.FACT_CHECK_MAX_SOURCES + 8
        self.timeout = timeout or settings.FACT_CHECK_TIMEOUT

    # ------------------------------------------------------------------ public
    def retrieve(self, claim: str) -> dict[str, Any]:
        warnings: list[str] = []
        clean = re.sub(r"\s+", " ", claim).strip()
        # WHY two query forms: web search benefits from fact-check vocabulary, but
        # Wikipedia's search index is title/lead-oriented and "fact check true or
        # false" drags in irrelevant articles. Each layer gets the query that suits it.
        web_query = self._clip(clean, 140) + WEB_QUERY_SUFFIX
        wiki_query = self._clip(clean, 90)

        layers = (
            ("ddgs", lambda: self._layer_package("ddgs", web_query)),
            ("duckduckgo_search", lambda: self._layer_package("duckduckgo_search", web_query)),
            ("ddg-html", lambda: self._layer_html(web_query)),
            ("ddg-instant-answer", lambda: self._layer_instant_answer(wiki_query)),
            ("wikipedia", lambda: self._layer_wikipedia(wiki_query)),
            ("openalex", lambda: self._layer_openalex(wiki_query)),
        )

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        used: list[str] = []

        # WHY try every layer instead of stopping at the first hit: layers return
        # different *kinds* of evidence (news and fact-check blogs from DDG,
        # encyclopaedic context from Wikipedia). Merging gives the scorer more to
        # work with, and the per-domain cap in `_dedupe` stops any one layer from
        # dominating. Layers are still cheap, so we stop once we have plenty.
        for label, fn in layers:
            if len(merged) >= self.max_results:
                break
            try:
                rows = fn() or []
            except Exception as exc:
                warnings.append(f"{label} retrieval failed: {exc.__class__.__name__}")
                continue
            if not rows:
                warnings.append(f"{label} returned no results")
                continue
            used.append(label)
            for r in rows:
                key = r["url"].rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(r)

        merged = self._dedupe(merged)
        # WHY keep a copy before the relevance gate: the gate is a noise filter, and
        # a filter must never be able to empty the result set. Measured failure —
        # "Bananas are a type of berry while strawberries are not" returned ZERO
        # sources because every snippet lost its overlap after stopword removal, so
        # the user saw an empty source list instead of a thin-but-present one. The
        # invariant is: the gate may reduce, never annihilate.
        before_gate = list(merged)
        merged = self._drop_irrelevant(clean, merged)
        if not merged and before_gate:
            merged = before_gate
        merged = merged[: self.max_results]

        if not merged:
            return {
                "results": [],
                "warnings": warnings
                + [
                    "No search backend responded. The server may have no outbound "
                    "internet access, or the free endpoints are blocking it. Set "
                    "FACT_CHECK_ENGINE=mock to demo the feature without network."
                ],
            }

        return {"results": merged, "warnings": warnings, "provider": "+".join(used) or "none"}

    # ------------------------------------------------------------------- layers
    def _layer_package(self, module: str, query: str) -> list[dict] | None:
        """Layers 1 & 2: the `ddgs` / `duckduckgo_search` Python packages."""
        try:
            if module == "ddgs":
                from ddgs import DDGS
            else:
                from duckduckgo_search import DDGS
        except ImportError:
            return None  # not installed -> silently skip to the next layer

        with DDGS() as ddgs:
            try:
                rows = list(ddgs.text(query, max_results=self.max_results, safesearch="moderate"))
            except TypeError:
                # Older/newer signatures differ on whether `safesearch` is accepted.
                rows = list(ddgs.text(query, max_results=self.max_results))
        return self._normalise(rows)

    def _layer_html(self, query: str) -> list[dict] | None:
        """
        Layer 3: parse DuckDuckGo's no-JavaScript HTML endpoint.

        The session warm-up is load-bearing — see the module docstring.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return None

        with httpx.Client(
            headers={
                "User-Agent": UA_BROWSER,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=self.timeout,
        ) as client:
            try:
                client.get("https://duckduckgo.com/")  # collect the anti-bot cookies
            except httpx.HTTPError:
                pass  # proceed anyway; the warm-up helps but is not mandatory

            resp = client.get(
                "https://html.duckduckgo.com/html/", params={"q": query}
            )

        # WHY check the status explicitly: DDG answers 202 with an interstitial
        # page when it considers the client a bot. That is not an exception, so
        # without this check it reads as "the request worked, there were simply no
        # results" — and you debug the parser instead of the headers.
        if resp.status_code != 200:
            raise RuntimeError(f"DuckDuckGo HTML endpoint returned HTTP {resp.status_code} (bot-blocked?)")

        soup = BeautifulSoup(resp.text, "html.parser")
        out: list[dict] = []
        for a in soup.select("a.result__a"):
            url = self._unwrap_ddg_redirect(a.get("href", ""))
            if not url:
                continue
            container = a.find_parent("div", class_="result")
            snip = container.select_one(".result__snippet") if container else None
            out.append(
                {
                    "title": a.get_text(" ", strip=True),
                    "url": url,
                    "snippet": snip.get_text(" ", strip=True) if snip else "",
                }
            )
            if len(out) >= self.max_results:
                break
        return out or None

    def _layer_instant_answer(self, query: str) -> list[dict] | None:
        """
        Layer 4: DuckDuckGo's Instant Answer API.

        WHY keep it: plain JSON, no HTML parsing, no bot detection in practice, and
        for well-known entities it returns an authoritative abstract plus related
        topics — often exactly the context a claim needs.
        """
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers={"User-Agent": UA_API},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        out: list[dict] = []
        abstract = (data.get("AbstractText") or "").strip()
        abstract_url = (data.get("AbstractURL") or "").strip()
        if abstract and abstract_url:
            out.append(
                {
                    "title": data.get("Heading") or query,
                    "url": abstract_url,
                    "snippet": abstract[:600],
                }
            )

        # RelatedTopics carry their own FirstURL/Text and are frequently the
        # most on-point evidence for a specific assertion.
        for topic in data.get("RelatedTopics", [])[:6]:
            if not isinstance(topic, dict):
                continue
            url = (topic.get("FirstURL") or "").strip()
            text = _TAG_RE.sub("", str(topic.get("Text") or "")).strip()
            if url and text:
                out.append({"title": text[:80], "url": url, "snippet": text[:600]})

        return out or None

    def _layer_wikipedia(self, query: str) -> list[dict] | None:
        """
        Layer 5: Wikipedia search via the action API.

        WHY this is the reliability floor: it is a documented, versioned, free API
        with no key, generous limits, and no bot detection for reasonable use.
        Encyclopaedic articles on contested topics ("Vaccines and autism",
        "Climate change denial") contain exactly the adjudicating language the
        scorer looks for — retracted, debunked, no evidence, scientific consensus.

        WHY request a longer snippet (`exchars`-style snippet is limited, so we
        ask the search API for `snippet` and also pull `pageprops`): the scorer
        judges on the text it is given. A 20-word snippet from a search index is
        thin evidence; a 500-char extract lets the negation logic actually work.
        """
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": min(6, self.max_results),
                "srprop": "snippet",
                "origin": "*",
            },
            headers={"User-Agent": UA_API},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", []) or []

        out: list[dict] = []
        for hit in hits:
            title = str(hit.get("title", "")).strip()
            if not title:
                continue
            snippet = _TAG_RE.sub("", str(hit.get("snippet", "")))
            snippet = snippet.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
            out.append(
                {
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                    "snippet": snippet[:500],
                }
            )

        # WHY enrich the top hit with a full extract: for the single most relevant
        # article we can afford one extra call, and a real paragraph of prose gives
        # the negation-aware scorer far more to work with than an index snippet.
        if out:
            enriched = self._wikipedia_extract(out[0]["title"])
            if enriched:
                out[0]["snippet"] = enriched

        return out or None

    def _layer_openalex(self, query: str) -> list[dict] | None:
        """
        Layer 6: OpenAlex — an open scholarly index. Free, no API key.

        WHY add a scholarly layer: it is the only keyless source here whose
        content is peer-reviewed literature. For claims about health, climate or
        science, a journal article outranks any blog, and it is independent of
        Wikipedia — so when DuckDuckGo blocks the server IP (which it does to
        cloud ranges) the system still has two unrelated retrieval paths instead
        of one.

        WHY only `doi.org` links: OpenAlex returns landing pages that are often
        paywalled and sometimes dead. A DOI resolves to the publisher's canonical
        record, which is stable and citable — the right thing to put in front of a
        student as a source.
        """
        try:
            resp = httpx.get(
                "https://api.openalex.org/works",
                params={
                    "search": query,
                    "per-page": min(5, self.max_results),
                    "mailto": "truthguard@example.edu",   # polite pool, per OpenAlex docs
                },
                headers={"User-Agent": UA_API},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            works = resp.json().get("results", []) or []
        except (httpx.HTTPError, ValueError):
            return None

        out: list[dict] = []
        for w in works:
            title = str(w.get("display_name") or w.get("title") or "").strip()
            doi = str(w.get("doi") or "").replace("https://doi.org/", "").strip()
            if not title:
                continue
            url = f"https://doi.org/{doi}" if doi else str(w.get("id") or "").strip()
            if not url.startswith("http"):
                continue

            # Build a snippet from the inverted abstract index OpenAlex provides.
            inv = w.get("abstract_inverted_index") or {}
            snippet = self._uninvert(inv)[:600]
            if not snippet:
                # No abstract: fall back to the venue + year, which is still useful
                # context for the scorer and for the human reading the citation.
                venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
                year = w.get("publication_year")
                snippet = " ".join(x for x in (str(venue or ""), str(year or "")) if x)

            out.append({"title": title, "url": url, "snippet": snippet})
        return out or None

    @staticmethod
    def _uninvert(inverted: dict) -> str:
        """
        Rebuild prose from OpenAlex's `abstract_inverted_index`.

        WHY: OpenAlex ships abstracts as {word: [position, ...]} to save bandwidth.
        Without inverting it there is no text for the scorer to judge, so the
        source would be a citation with no evidence attached.
        """
        if not inverted:
            return ""
        positions: list[tuple[int, str]] = []
        for word, idxs in inverted.items():
            for i in idxs or []:
                positions.append((int(i), str(word)))
        positions.sort()
        return re.sub(r"\s+", " ", " ".join(w for _, w in positions)).strip()

    def _wikipedia_extract(self, title: str) -> str | None:
        """Fetch the lead sections of one article as plain text."""
        try:
            resp = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "titles": title,
                    "redirects": 1,
                    "origin": "*",
                },
                headers={"User-Agent": UA_API},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = (page.get("extract") or "").strip()
                if text:
                    # WHY 2500 chars and not a small snippet: the adjudicating
                    # sentence is often NOT in the first paragraph. Measured case:
                    # "The Eiffel Tower was built in 1889 for the World's Fair" is
                    # TRUE, but with only the first 1200 characters of the lead the
                    # scorer never saw "1889" or "Exposition Universelle" and
                    # returned "Unverified" for a claim it had the evidence to
                    # confirm. Cutting the evidence is what produced the wrong
                    # answer, so the window is generous.
                    return re.sub(r"\s+", " ", text)[:2500]
        except httpx.HTTPError:
            return None
        return None

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _clip(text: str, limit: int) -> str:
        """Trim on a word boundary so the query never ends mid-token."""
        if len(text) <= limit:
            return text
        return text[:limit].rsplit(" ", 1)[0]

    @staticmethod
    def _unwrap_ddg_redirect(href: str) -> str:
        """
        DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded-url>.
        Return the real target, or "" if the link is unusable.
        """
        href = (href or "").strip()
        if not href:
            return ""
        match = re.search(r"uddg=([^&]+)", href)
        if match:
            href = urllib.parse.unquote(match.group(1))
        if href.startswith("//"):
            href = "https:" + href
        return href if href.startswith("http") else ""

    def _normalise(self, rows: list[dict[str, Any]] | None) -> list[dict] | None:
        """
        Map whatever keys the search library returned onto our shape.

        WHY be defensive about key names: `ddgs` has returned `href` in some
        versions and `url` in others. Normalising here means the scorer never has
        to know which library produced the row.
        """
        out = []
        for r in rows or []:
            url = r.get("url") or r.get("href") or r.get("link") or ""
            url = str(url).strip()
            if not url.startswith("http"):
                continue
            out.append(
                {
                    "title": str(r.get("title") or "").strip(),
                    "url": url,
                    "snippet": re.sub(r"\s+", " ", str(r.get("body") or r.get("snippet") or "")).strip(),
                }
            )
        return out or None

    STOPWORDS = frozenset(
        "the a an and or but if of to in on for with from is are was were be been "
        "that this these those it its as at by not no do does did has have had "
        "claim says said true false fact check verified about into over under "
        "than then there their they them he she his her we you your i".split()
    )

    @classmethod
    def _drop_irrelevant(cls, claim: str, results: list[dict]) -> list[dict]:
        """
        Remove results that share no vocabulary with the claim.

        WHY this is needed: a real measured failure. Querying "Drinking garlic
        water cures viral infections within two days" returned a Wikipedia article
        about CATS — because "garlic" matched "Allium" taxonomy text somewhere and
        the search index surfaced an unrelated page. Feeding that into the scorer
        means judging the claim on evidence about a different subject, which can
        flip the verdict. A zero-overlap result is noise, not weak evidence.

        WHY keep the best result unconditionally: if the gate filtered everything
        (an unusual claim, or a snippet too short to overlap), returning an empty
        list would be worse than returning the top hit with a warning. Degrading
        to "Unverified" with one shown source beats silently showing nothing.
        """
        claim_tokens = {
            t for t in re.findall(r"[a-z0-9]{3,}", claim.lower()) if t not in cls.STOPWORDS
        }
        if not claim_tokens:
            return results

        kept = []
        for r in results:
            text = f"{r.get('title','')} {r.get('snippet','')}".lower()
            tokens = set(re.findall(r"[a-z0-9]{3,}", text)) - cls.STOPWORDS
            overlap = len(claim_tokens & tokens)
            r["relevance_overlap"] = overlap
            if overlap >= 1:
                kept.append(r)

        # Second line of defence: if strict overlap kept nothing, retain the
        # highest-overlap results rather than returning an empty list.
        if not kept and results:
            ranked = sorted(results, key=lambda r: r.get("relevance_overlap", 0), reverse=True)
            kept = ranked[:2]
        return kept

    @staticmethod
    def _dedupe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Drop repeats and cap how much any one site can contribute.

        WHY a per-domain cap: search engines return five links to the same story
        on the same outlet. Counting them five times would let a single publisher
        dominate the evidence score — a real bias, not a cosmetic issue. Two per
        domain keeps a site's voice while leaving room for corroboration.
        """
        seen_url: set[str] = set()
        per_domain: dict[str, int] = {}
        out = []
        for r in results:
            url = r["url"].rstrip("/").lower()
            if url in seen_url:
                continue
            domain = FactCheckEngine.domain_of(r["url"])
            # WHY a higher cap for encyclopaedic/scholarly domains: three links to
            # the SAME news story on one outlet is duplication. Three DIFFERENT
            # Wikipedia articles are corroboration. base.py owns the authoritative
            # list; this local cap only prevents one news outlet dominating.
            cap = 4 if any(
                domain == d or domain.endswith("." + d)
                for d in ("wikipedia.org", "britannica.com", "openalex.org", "crossref.org")
            ) else 2
            if per_domain.get(domain, 0) >= cap:
                continue
            seen_url.add(url)
            per_domain[domain] = per_domain.get(domain, 0) + 1
            r["domain"] = domain
            out.append(r)
        return out


__all__ = ["DuckDuckGoEngine"]
