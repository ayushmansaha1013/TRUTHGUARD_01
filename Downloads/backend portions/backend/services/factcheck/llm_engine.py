"""
=============================================================================
factcheck/llm_engine.py — retrieval-augmented judgement via a free LLM (opt-in)
=============================================================================
WHY THIS IS NOT THE DEFAULT
    It needs an API key. A default that requires a secret cannot be graded by
    someone else cloning the repo. So the free, keyless DuckDuckGo engine is the
    default and this is the upgrade path:

        FACT_CHECK_ENGINE=llm
        GROQ_API_KEY=gsk_...            # free at console.groq.com

WHY RETRIEVAL FIRST, THEN THE MODEL
    Asking an LLM "is this claim true?" invites a confident hallucination, and a
    fabricated citation in a fact-checking product is the worst possible failure.
    Instead we retrieve real sources first, hand the model ONLY those passages,
    and force it to cite by index. Any URL it returns that is not in the
    retrieved set is discarded before the response is built — the model cannot
    smuggle a citation into the UI.

WHY GROQ
    A genuinely free tier with no card, and llama-3.3-70b is fast enough that the
    "Analyzing sources..." animation covers the latency instead of hiding a
    timeout.
=============================================================================
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .base import FactCheckEngine
from .duckduckgo_engine import DuckDuckGoEngine

ALLOWED_VERDICTS = {"True", "Mostly true", "Mixed", "Unverified", "Mostly false", "False"}

SYSTEM_PROMPT = """You are the judgement layer of TruthGuard AI, a misinformation
detection tool for civic education. You are given a CLAIM and a numbered list of
RETRIEVED SOURCES. Decide the verdict using ONLY those sources.

Rules:
1. Never use your own memory as evidence. If the sources do not settle the claim,
   the verdict MUST be "Unverified".
2. Cite by source number only, e.g. [1][3]. Do not invent URLs.
3. Distinguish "a source reports X" from "X is true". Note who is claiming what.
4. Prefer high-trust domains when sources conflict, and say so explicitly.
5. Be concise: 3-6 sentences. No preamble, no markdown headings.

Reply with STRICT JSON only, no code fences:
{
  "verdict": "True|Mostly true|Mixed|Unverified|Mostly false|False",
  "explanation": "...",
  "confidence": 0-100,
  "cited": [1, 3]
}"""


class LLMEngine(FactCheckEngine):
    name = "llm-rag"

    DISCLAIMER = (
        "Verdict produced by a language model reasoning over retrieved web sources "
        "(retrieval-augmented). Sources are real and were fetched at request time; "
        "the reasoning is the model's. Citations outside the retrieved set are "
        "rejected automatically."
    )

    def __init__(self) -> None:
        from config import settings

        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.url = settings.GROQ_URL
        self.timeout = settings.FACT_CHECK_TIMEOUT
        self.retriever = DuckDuckGoEngine()

    # ------------------------------------------------------------------ public
    def retrieve(self, claim: str) -> dict[str, Any]:
        """Retrieve, then judge. Returns an override payload for the router."""
        warnings: list[str] = []

        fetched = self.retriever.retrieve(claim)
        results = fetched.get("results", [])
        warnings.extend(fetched.get("warnings", []))

        if not results:
            # WHY not call the LLM anyway: with no sources the model would answer
            # from memory, which is the exact hallucination path this design exists
            # to prevent. Fall back to the shared scorer's honest "Unverified".
            return {
                "results": [],
                "warnings": warnings + ["No sources retrieved; LLM judgement skipped."],
            }

        if not self.api_key:
            warnings.append(
                "FACT_CHECK_ENGINE=llm but GROQ_API_KEY is empty — falling back to "
                "keyword-evidence scoring over the retrieved sources."
            )
            return {"results": results, "warnings": warnings}

        judged = self._judge(claim, results)
        if judged is None:
            warnings.append("LLM judgement failed or returned invalid JSON; fell back to scoring.")
            return {"results": results, "warnings": warnings}

        verdict, explanation, confidence, cited = judged

        # WHY filter citations: this is the anti-hallucination gate. Only URLs
        # that were actually retrieved may reach the UI.
        allowed = {results[i - 1]["url"] for i in cited if 1 <= i <= len(results)}
        sources = [r for r in results if r["url"] in allowed] or results[:4]

        # Surface the retrieved index inside the explanation so [1] is meaningful.
        numbered = "\n".join(f"[{i}] {r['url']}" for i, r in enumerate(results, 1))
        explanation = f"{explanation}\n\nSource index used:\n{numbered}"

        return {
            "verdict_override": verdict,
            "explanation_override": explanation,
            "confidence_override": confidence,
            "results": sources,
            "warnings": warnings,
            "provider": f"groq:{self.model}",
        }

    # ------------------------------------------------------------------ private
    def _judge(self, claim: str, results: list[dict]) -> tuple | None:
        numbered = "\n\n".join(
            f"[{i}] {r.get('title','')}\n    URL: {r.get('url','')}\n    DOMAIN TRUST: "
            f"{self.trust_of(r.get('url',''))}/5\n    TEXT: {r.get('snippet','')[:600]}"
            for i, r in enumerate(results[:8], 1)
        )

        payload = {
            "model": self.model,
            "temperature": 0.0,      # WHY 0: a verdict must be reproducible
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CLAIM: {claim}\n\nRETRIEVED SOURCES:\n{numbered}"},
            ],
        }

        try:
            resp = httpx.post(
                self.url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[factcheck] LLM call failed: {exc.__class__.__name__}: {exc}", flush=True)
            return None

        data = self._parse_json(content)
        if not data:
            return None

        verdict = str(data.get("verdict", "")).strip()
        # WHY validate against the allow-list: the model can return "FALSE" or
        # "Debunked". The frontend's badge colours and the audit log both switch
        # on exact strings, so anything unrecognised must be coerced, not passed
        # through to render as an unstyled badge.
        if verdict not in ALLOWED_VERDICTS:
            verdict = self._coerce_verdict(verdict)

        try:
            confidence = max(0.0, min(100.0, float(data.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0

        cited = [int(x) for x in data.get("cited", []) if isinstance(x, (int, float)) or str(x).isdigit()]
        explanation = re.sub(r"\s+", " ", str(data.get("explanation", ""))).strip()

        if not explanation:
            return None

        return verdict, explanation, confidence, cited

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Tolerate code fences and leading prose around the JSON object."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _coerce_verdict(raw: str) -> str:
        low = raw.lower()
        if any(k in low for k in ("false", "debunk", "wrong", "fake", "hoax")):
            return "False"
        if "mostly true" in low or "partly true" in low:
            return "Mostly true"
        if "mostly false" in low or "partly false" in low:
            return "Mostly false"
        if "mixed" in low or "unclear" in low or "both" in low:
            return "Mixed"
        if "true" in low or "accurate" in low or "correct" in low or "supported" in low:
            return "True"
        return "Unverified"


__all__ = ["LLMEngine"]
