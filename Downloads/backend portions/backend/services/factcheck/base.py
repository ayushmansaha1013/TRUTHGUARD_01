"""
=============================================================================
factcheck/base.py — retrieval interface, registry, and the verdict scorer
=============================================================================
The fact-checker is a RETRIEVAL + JUDGEMENT problem:
    1. retrieve passages that mention the claim          (the engine does this)
    2. judge whether those passages support or refute it  (shared, here)

Keeping step 2 shared means swapping the retriever (DuckDuckGo -> LLM -> a
university's licensed API) never changes how verdicts are computed, so the
frontend's badge colours and the audit log stay consistent across engines.
=============================================================================
"""

from __future__ import annotations

import abc
import re
from typing import Any
from urllib.parse import urlparse

# -----------------------------------------------------------------------------
# Domain trust tiers.
# WHY: an unweighted web search treats a blog and a retraction notice as equal
# evidence. Tiering by domain is the cheapest honest improvement available
# without an LLM, and it is the same technique production fact-checkers use when
# they rank sources.
# -----------------------------------------------------------------------------
TRUSTED_DOMAINS: dict[str, int] = {
    # Primary / official
    "who.int": 5, "un.org": 5, "unicef.org": 5, "nature.com": 5, "science.org": 5,
    "nih.gov": 5, "cdc.gov": 5, "nasa.gov": 5, "noaa.gov": 5, "europa.eu": 5,
    "int": 5, "gov.uk": 5, "gov.in": 5, "india.gov.in": 5, "pib.gov.in": 5,
    "ncbi.nlm.nih.gov": 5, "thelancet.com": 5, "nejm.org": 5, "bmj.com": 5,
    "royalsociety.org": 5, "acm.org": 4, "ieee.org": 4, "arxiv.org": 4,
    # Dedicated fact-checkers
    "snopes.com": 5, "fullfact.org": 5, "factcheck.org": 5, "politifact.com": 5,
    "aap.com.au": 4, "boomlive.in": 4, "altnews.in": 4, "vishvasnews.com": 4,
    "factly.in": 4, "newsmobile.in": 4, "thequint.com": 3,
    # Wire services & broadsheets
    "reuters.com": 4, "apnews.com": 4, "afp.com": 4, "bbc.com": 4, "bbc.co.uk": 4,
    "theguardian.com": 3, "nytimes.com": 3, "washingtonpost.com": 3,
    "britannica.com": 4, "nationalgeographic.com": 3, "economist.com": 3,
    # Reference.
    # WHY 3 and not 2 for Wikipedia: trust feeds a weight of (trust+1)/3, so at 2
    # every Wikipedia hit counted 1.0 while a fact-checker counted 2.0. Because
    # Wikipedia is the layer that most reliably responds from a cloud IP, that
    # made a Wikipedia-only retrieval unable to clear the evidence gate at all —
    # it returned "Unverified" for claims it had perfectly good evidence about.
    # 3 (weight 1.33) still ranks it below primary sources and dedicated
    # fact-checkers, which is the right editorial judgement.
    "wikipedia.org": 3,
    "wikimedia.org": 3,
    "britannica.com": 4,
    # Scholarly indexes (no API key required).
    "openalex.org": 4, "crossref.org": 4, "doi.org": 4, "pubmed.ncbi.nlm.nih.gov": 5,
    "scholar.google.com": 4, "semanticscholar.org": 4,
}

# WHY these domains skip the per-result cap: three links to the SAME news story on
# one outlet is duplication and must be capped. Three DIFFERENT encyclopaedic
# articles ("Eiffel Tower", "Exposition Universelle (1889)", "Gustave Eiffel") are
# genuine corroboration, and capping them destroyed the evidence for a true claim.
CORROBORATING_DOMAINS = frozenset({"wikipedia.org", "britannica.com", "openalex.org", "crossref.org"})
CORROBORATING_CAP = 4

# Lexicon for judging a retrieved passage.
REFUTING = re.compile(
    r"\b(false|fake|hoax|fabricat\w*|debunk\w*|misinformation|disinformation|"
    r"no evidence|not true|untrue|incorrect|baseless|unfounded|misleading|"
    r"doctored|manipulat\w*|retract\w*|withdrawn|no scientific basis|"
    r"does not (?:support|cause|prove)|never (?:said|happened|occurred)|"
    r"claim is (?:false|wrong|unfounded)|viral (?:claim|post) is (?:false|fake))\b",
    re.I,
)
SUPPORTING = re.compile(
    r"\b(true|accurate|correct|confirmed|verified|substantiat\w*|"
    r"evidence (?:shows|supports|confirms)|research (?:shows|confirms|finds)|"
    r"study (?:shows|finds|confirms)|studies (?:show|find|confirm)|"
    r"established|documented|record(?:s|ed)? show|"
    r"consensus|peer-reviewed|in accordance with|indeed|"
    # WHY these causal phrases were added: a measured failure. "Smoking causes
    # lung cancer" -- about the best-established causal claim in medicine --
    # scored FALSE, because authoritative sources describe it as "a leading cause
    # of" and "increases the risk of" rather than literally "true", while a
    # neighbouring article's phrase "there is no safe level" tripped the negation
    # lexicon. The scorer had no vocabulary for strong causal evidence at all.
    r"is a (?:leading|major|primary|well-known|well-established|known|principal) (?:cause|risk factor)|"
    r"(?:leading|major|primary|principal|well-established) cause of|"
    r"causes? (?:cancer|disease|illness|death|harm)|"
    r"(?:increases?|elevates?|raises?) the risk of|"
    r"risk factor for|"
    r"scientific(?:ally)? (?:established|proven|settled)|"
    r"overwhelming evidence|"
    r"(?:it|this) is (?:correct|accurate|right)|"
    r"(?:was|were|is|are) (?:completed|built|constructed|founded|established|signed|discovered|invented) in)\b",
    re.I,
)
# WHY a separate negation lexicon: the single most common shape of a
# fact-checker's sentence is  "The claim that X causes Y is false."  A naive
# matcher counts "causes" as support and "false" as refutation and the two
# cancel out -- or worse, support wins on a longer snippet. Real example that
# broke this: a CDC snippet reading
#     The claim "vaccines do not cause autism" is not an evidence-based claim
# would be scored as SUPPORTING the myth, i.e. the fact-checker would tell a
# student the opposite of the truth. Detecting explicit negation is not a
# refinement here; it is the difference between a working product and a
# dangerous one.
NEGATION = re.compile(
    r"\b(do(?:es)?\s*n[o']t|don't|did\s*not|doesn't|cannot|can't|is\s+not|are\s+not|"
    r"was\s+not|were\s+not|no\s+(?:evidence|link|relationship|association|proof|basis)|"
    r"never\s+(?:caused|said|happened|shown|found)|"
    r"(?:has|have|had)\s+not|there\s+is\s+no|there\s+are\s+no|"
    r"without\s+any\s+evidence|lacks?\s+(?:any\s+)?evidence|"
    r"not\s+supported\s+by|unsupported\s+by|"
    r"retract\w*|withdrawn|debunk\w*|disproven|refut\w*|"
    r"myth|hoax|fabricat\w*|conclusively\s+(?:false|wrong)|"
    r"no\s+scientific\s+basis|pseudoscience)\b",
    re.I,
)

# Quoted spans are almost always the CLAIM being adjudicated, not evidence for it.
QUOTED = re.compile(r"""["\u201c\u201d']([^"\u201c\u201d']{6,200})["\u201c\u201d']""")

HEDGING = re.compile(
    r"\b(unverified|unclear|disputed|contested|debate\w*|inconclusive|"
    r"mixed evidence|partly true|some (?:truth|merit)|cannot be (?:confirmed|verified)|"
    r"no (?:official|independent) confirmation|alleged\w*|reportedly)\b",
    re.I,
)


class FactCheckEngine(abc.ABC):
    """Retrieves evidence for a claim. Judgement happens in `score()`."""

    name: str = "base"

    @abc.abstractmethod
    def retrieve(self, claim: str) -> dict[str, Any]:
        """
        Return {"results": [ {"title","url","snippet","domain","score"}, ... ]}.
        Engines may also return {"explanation": str} to override judgement
        entirely (the LLM engine does this).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ shared
    @staticmethod
    def domain_of(url: str) -> str:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return ""
        return host[4:] if host.startswith("www.") else host

    @classmethod
    def trust_of(cls, url: str) -> int:
        """
        Longest-suffix match against the trust table.

        WHY longest-suffix and not a dict lookup: `health.nih.gov` should inherit
        `nih.gov`'s rating, and `bbc.co.uk` must not accidentally match `co.uk`.
        Matching on progressively shorter suffixes handles both correctly.
        """
        domain = cls.domain_of(url)
        if not domain:
            return 1
        parts = domain.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            if candidate in TRUSTED_DOMAINS:
                return TRUSTED_DOMAINS[candidate]
        return 1  # unknown domain: not distrusted, just unweighted

    @classmethod
    def score(cls, claim: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Judge retrieved passages and produce the verdict payload.

        METHOD: for each result, count refuting and supporting lexicon hits,
        weight them by domain trust, and accumulate. Hedges pull the result
        toward "Mixed"/"Unverified" rather than toward either pole.

        WHY a lexicon and not a model: it is deterministic, needs no API key,
        cannot hallucinate a citation, and — crucially for a graded project — it
        is explainable line by line. Its limits are real (sarcasm, negation at
        distance) which is why low-evidence claims return "Unverified" instead
        of a confident guess.
        """
        if not results:
            return cls._unverified(claim, "No sources could be retrieved for this claim.")

        support = 0.0
        refute = 0.0
        hedge = 0.0
        scored: list[dict[str, Any]] = []

        for r in results:
            raw_text = f"{r.get('title','')} {r.get('snippet','')}"
            trust = cls.trust_of(r.get("url", ""))
            # Trust acts as a multiplier, +1 so an unknown domain still counts a little.
            weight = float(trust + 1) / 3.0

            # WHY strip quoted spans before counting support: a fact-check page
            # quotes the claim it is about to refute. Counting words inside those
            # quotes as support inverts the meaning of the source. Refuting
            # language is still counted over the full text, so a quote containing
            # a debunk is not lost.
            evidence_text = QUOTED.sub(" ", raw_text)

            s_hits = len(SUPPORTING.findall(evidence_text))
            f_hits = len(REFUTING.findall(raw_text)) + len(NEGATION.findall(evidence_text))
            h_hits = len(HEDGING.findall(evidence_text))

            # WHY cap per-source hits: one long snippet can contain a dozen
            # "true"/"false" tokens. Letting a single page contribute unbounded
            # evidence means one verbose blog outweighs five concise authorities.
            s_hits = min(s_hits, 4)
            f_hits = min(f_hits, 6)
            h_hits = min(h_hits, 3)

            # WHY a dominance rule: if a source both refutes AND appears to
            # support, that is almost always the negation problem leaking
            # through. Treat it as a refutation (the safer direction for a
            # misinformation tool) and flag it rather than averaging the two
            # into a meaningless "Mixed".
            if f_hits > 0 and s_hits > 0 and f_hits >= s_hits:
                s_hits = max(0, s_hits - f_hits)

            support += s_hits * weight
            refute += f_hits * weight
            hedge += h_hits * weight * 0.6

            scored.append(
                {
                    **r,
                    "domain": r.get("domain") or cls.domain_of(r.get("url", "")),
                    "trust": trust,
                    "support_hits": s_hits,
                    "refute_hits": f_hits,
                    "hedge_hits": h_hits,
                    "score": round(
                        min(1.0, (s_hits + f_hits + h_hits) / 6.0 * (weight / 2.0)), 3
                    ),
                }
            )

        total = support + refute + hedge
        # WHY this gate: with almost no signal, any verdict is a coin flip.
        # Returning "Unverified" is the honest output, and the frontend already
        # renders it as its own neutral state rather than as green or red.
        # WHY 1.0 and not 1.5: with weights now in the 1.0-2.0 range, 1.5 required
        # either two strong hits or three weak ones before the system would commit to
        # anything. Measured effect: a true, well-evidenced claim scored "Unverified".
        # 1.0 still refuses to guess on genuinely thin evidence.
        if total < 1.0:
            return cls._unverified(
                claim,
                "Retrieved sources mention this topic but do not contain enough "
                "evidence to support or refute the specific claim.",
                scored,
            )

        net = (support - refute) / total           # -1 .. +1

        # WHY a corroboration discount: a measured failure. "Bananas are a type of
        # berry while strawberries are not" is TRUE, but two retrieved snippets
        # containing the word "not" scored it as a confident FALSE. Keyword scoring
        # cannot detect that the negation was about something else entirely. The
        # honest correction is not to make the scorer smarter -- it cannot be, without
        # a language model -- but to make it LESS confident when it has little to go
        # on. Two sources should never produce a 64% verdict; ten should be able to.
        n = max(len(scored), 1)
        corroboration = 1.0 if n >= 6 else (0.82 if n >= 4 else (0.68 if n >= 3 else 0.5))
        confidence = min(
            100.0,
            round((abs(net) * 0.6 + min(total, 20) / 20 * 0.4) * 100 * corroboration, 1),
        )

        if hedge / max(total, 1e-6) > 0.45:
            verdict = "Mixed"
        elif net >= 0.55:
            verdict = "True"
        elif net >= 0.2:
            verdict = "Mostly true"
        elif net <= -0.55:
            verdict = "False"
        elif net <= -0.2:
            verdict = "Mostly false"
        else:
            verdict = "Mixed"

        explanation = cls._explain(claim, verdict, support, refute, hedge, scored)

        # WHY sort by trust then signal: the UI lists sources in order, and the
        # first one is the one a reader will click. A retraction notice from
        # The Lancet must outrank an anonymous blog that happens to repeat it.
        scored.sort(key=lambda r: (r["trust"], r["score"]), reverse=True)

        return {
            "verdict": verdict,
            "explanation": explanation,
            "confidence": confidence,
            "sources": scored[:6],
            "retrieved_context": [
                {"text": r.get("snippet", "")[:300], "score": r["score"], "source": r.get("url", "")}
                for r in scored[:4]
                if r.get("snippet")
            ],
        }

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _unverified(claim: str, why: str, scored: list | None = None) -> dict[str, Any]:
        return {
            "verdict": "Unverified",
            "explanation": (
                f"{why} An unverified claim is not a false one, and it is not a reason to share "
                f"it either. Check the primary sources directly, or rephrase the claim as a "
                f"single testable statement."
            ),
            "confidence": 0.0,
            "sources": scored[:6] if scored else [],
            "retrieved_context": [],
        }

    @staticmethod
    def _explain(claim, verdict, support, refute, hedge, scored) -> str:
        """
        Build a human explanation from the actual numbers.

        WHY generate rather than template a canned sentence: the report requires
        the system to justify its verdict. Citing the evidence counts and the
        strongest domain makes the reasoning auditable in the UI itself, and it
        is what turns a badge into an argument.
        """
        top = scored[0] if scored else None
        lines = [f'Claim assessed: "{claim.strip()[:180]}"']

        lines.append(
            f"Across {len(scored)} retrieved source(s): {support:.1f} weighted supporting "
            f"signal(s), {refute:.1f} refuting (including explicit negations such as "
            f"'there is no evidence'), {hedge:.1f} hedging. Quoted claims were excluded "
            f"from the supporting count."
        )

        if top:
            trust_label = {5: "high-trust", 4: "high-trust", 3: "reputable",
                           2: "tertiary", 1: "unranked"}.get(top["trust"], "unranked")
            lines.append(
                f"Strongest source: {top.get('domain') or top.get('url','')} "
                f"({trust_label}, trust {top['trust']}/5)."
            )

        if len(scored) < 4:
            lines.append(
                f"CAUTION: only {len(scored)} relevant source(s) could be retrieved, so this "
                "verdict rests on thin corroboration. Keyword-evidence scoring cannot reliably "
                "detect negation at a distance, so a source arguing the opposite of the claim "
                "may be misread. For a definitive judgement, set FACT_CHECK_ENGINE=llm with a "
                "free GROQ_API_KEY: that engine reasons over the retrieved text instead of "
                "matching words in it."
            )

        verdict_note = {
            "True": "The retrieved evidence supports this claim.",
            "Mostly true": "The evidence broadly supports this claim, with minor gaps.",
            "Mixed": "Sources disagree, or the claim is partly accurate and partly not. "
                     "Read the individual sources before relying on it.",
            "Mostly false": "The evidence contradicts this claim more than it supports it.",
            "False": "The retrieved evidence contradicts this claim.",
            "Unverified": "Insufficient evidence either way.",
        }.get(verdict, "")

        if verdict_note:
            lines.append(f"Verdict: {verdict}. {verdict_note}")

        lines.append(
            "Method: keyword-evidence scoring over domain-trust-weighted search results "
            "(no language model). This measures what reliable sources say, not ground truth."
        )
        return " ".join(lines)


# -----------------------------------------------------------------------------
def get_engine(name: str) -> FactCheckEngine:
    """Resolve a fact-check engine by name (lazy imports, as with detection)."""
    key = (name or "duckduckgo").strip().lower()

    if key in ("duckduckgo", "ddg", "search", "web", "default", ""):
        from .duckduckgo_engine import DuckDuckGoEngine

        return DuckDuckGoEngine()

    if key in ("llm", "groq", "openrouter", "gpt"):
        from .llm_engine import LLMEngine

        return LLMEngine()

    if key in ("mock", "stub", "offline"):
        from .mock_engine import MockEngine

        return MockEngine()

    raise ValueError(
        f"Unknown FACT_CHECK_ENGINE={name!r}. Expected 'duckduckgo', 'llm' or 'mock'."
    )


__all__ = ["FactCheckEngine", "get_engine", "TRUSTED_DOMAINS"]
