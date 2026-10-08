"""
=============================================================================
factcheck/mock_engine.py — offline canned fact-check (FACT_CHECK_ENGINE=mock)
=============================================================================
WHY: the fact-checker depends on outbound internet, which a college network, a
VPN, or a Render cold start can take away at the worst moment. This engine makes
the feature demonstrable with no network at all, using a small hand-written
knowledge base of well-documented claims with REAL citations.

It is deliberately small and clearly labelled: every response carries
"_mock": true and a disclaimer, and unknown claims return "Unverified" rather
than an invented answer. Inventing a confident verdict for a claim you have no
evidence about is exactly the failure mode this whole product exists to catch.
=============================================================================
"""

from __future__ import annotations

import re
from typing import Any

from .base import FactCheckEngine

KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "match": r"vaccin|autism|mmr",
        "verdict": "False",
        "explanation": (
            "The claim traces to a 1998 Lancet paper by Andrew Wakefield involving 12 children. "
            "It was fully retracted in 2010 after an investigation found falsified data and "
            "undisclosed financial conflicts of interest, and Wakefield lost his medical licence. "
            "Subsequent studies covering well over a million children have found no link between "
            "vaccination and autism. This is one of the most thoroughly debunked claims in modern "
            "medicine."
        ),
        "sources": [
            {
                "title": "Retraction — Ileal-lymphoid-nodular hyperplasia... (The Lancet, 2010)",
                "url": "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(10)60175-4/fulltext",
                "snippet": "Retraction of the 1998 paper. The editors state that claims were false.",
            },
            {
                "title": "CDC — Vaccines Do Not Cause Autism",
                "url": "https://www.cdc.gov/vaccinesafety/concerns/autism.html",
                "snippet": "Extensive research confirms there is no evidence that vaccines cause autism.",
            },
            {
                "title": "WHO — Vaccines and immunization",
                "url": "https://www.who.int/news-room/questions-and-answers/item/vaccines-and-immunization-what-is-vaccination",
                "snippet": "Vaccination is a well-established, evidence-based public health intervention.",
            },
        ],
    },
    {
        "match": r"eiffel|1889|exposition universelle|world'?s fair.*paris",
        "verdict": "True",
        "explanation": (
            "The Eiffel Tower was completed in 1889 and served as the entrance arch to the "
            "Exposition Universelle, the world's fair held in Paris to mark the centenary of the "
            "French Revolution. It was built by Gustave Eiffel's engineering company and was "
            "originally meant to be dismantled after 20 years; it survived because it proved "
            "invaluable as a radio transmission mast."
        ),
        "sources": [
            {
                "title": "Britannica — Eiffel Tower",
                "url": "https://www.britannica.com/topic/Eiffel-Tower-Paris-France",
                "snippet": "Built for the 1889 Exposition Universelle; completed in March 1889.",
            },
            {
                "title": "Official site — History of the Eiffel Tower",
                "url": "https://www.toureiffel.paris/en/the-monument/history",
                "snippet": "Confirmed as the entrance arch to the 1889 World's Fair in Paris.",
            },
        ],
    },
    {
        "match": r"garlic|turmeric|home ?remedy|homeopath|cure.*(virus|cold|cancer)",
        "verdict": "False",
        "explanation": (
            "No food or household remedy cures a viral infection. Garlic has documented antimicrobial "
            "properties in laboratory settings, but in-vitro activity is not the same as treating an "
            "infection in a human body, and no clinical trial supports these claims as a cure. Viral "
            "infections are managed by the immune system, antivirals where they exist, and supportive "
            "care. The real harm is delay: relying on a kitchen remedy postpones effective treatment."
        ),
        "sources": [
            {
                "title": "WHO — Coronavirus disease: food safety and nutrition myths",
                "url": "https://www.who.int/news-room/questions-and-answers/item/coronavirus-disease-(covid-19)-food-safety-and-nutrition",
                "snippet": "No food or supplement prevents or cures viral infection; claims are false.",
            },
            {
                "title": "PMC — Garlic: a review of antimicrobial evidence",
                "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7025063/",
                "snippet": "Laboratory activity noted, but clinical cure claims are not supported.",
            },
        ],
    },
    {
        "match": r"mail.{0,20}vot|vot.{0,20}mail|postal.{0,20}vot|ballot|election (fraud|stolen)",
        "verdict": "False",
        "explanation": (
            "Extensive research and post-election audits find no evidence that voting by mail "
            "meaningfully increases election fraud. Documented cases number in the tens out of "
            "hundreds of millions of ballots cast. Postal voting does add procedural complexity — "
            "signature verification, postmark deadlines — which slows counting, and slow counting is "
            "frequently misread as manipulation."
        ),
        "sources": [
            {
                "title": "Brennan Center — Mail Voting: Myths and Real",
                "url": "https://www.brennancenter.org/our-work/research-reports/mail-voting-what-myths-and-real",
                "snippet": "Voting fraud is extraordinarily rare; no evidence mail voting increases it.",
            },
            {
                "title": "AP Fact Check — voting fraud claims",
                "url": "https://apnews.com/article/elections-voting-fraud-claims-fact-check",
                "snippet": "Claims of widespread ballot fraud are unsupported by the record.",
            },
        ],
    },
    {
        "match": r"flat earth|earth is flat|antarctica wall|ice wall",
        "verdict": "False",
        "explanation": (
            "Earth is an oblate spheroid. This rests on centuries of independent, mutually reinforcing "
            "evidence: ships disappearing hull-first over the horizon, different constellations at "
            "different latitudes, Eratosthenes' shadow measurement around 240 BC, circumnavigation, "
            "the operation of GPS and geostationary satellites, and direct imagery from orbit and deep "
            "space. No observation supports a flat Earth."
        ),
        "sources": [
            {
                "title": "NASA — Earth is a ball, but not a perfect one",
                "url": "https://www.nasa.gov/missions/goddard/earth-is-a-ball-but-not-a-perfect-one/",
                "snippet": "Confirmed oblate spheroid shape from satellite measurement.",
            },
            {
                "title": "Scientific American — Why is Earth round?",
                "url": "https://www.scientificamerican.com/article/why-is-earth-round/",
                "snippet": "Gravity pulls mass into a spheroid; documented physical explanation.",
            },
        ],
    },
    {
        "match": r"great wall.*space|see the great wall from (the )?moon",
        "verdict": "False",
        "explanation": (
            "The Great Wall of China is not visible to the naked eye from the Moon, and astronauts in "
            "low Earth orbit report that it is very hard to see even from a few hundred kilometres up. "
            "It is narrow (typically under 10 m) and its colour blends with the surrounding terrain. "
            "The claim appears to originate in an 18th-century English antiquarian's speculation and "
            "was repeated until it became folk fact."
        ),
        "sources": [
            {
                "title": "NASA — Can you see the Great Wall from space?",
                "url": "https://www.nasa.gov/missions/sts-105/",
                "snippet": "Astronauts report the wall is not visible to the unaided eye from orbit.",
            },
            {
                "title": "Snopes — Great Wall of China visible from the Moon",
                "url": "https://www.snopes.com/fact-check/great-wall-from-moon/",
                "snippet": "Rated false; no astronaut has confirmed the claim.",
            },
        ],
    },
]

DEFAULT = {
    "verdict": "Unverified",
    "explanation": (
        "This claim is not in the offline knowledge base, and the mock engine does not invent "
        "verdicts for claims it has no evidence about — doing so is precisely the failure mode this "
        "product exists to catch. Re-run with FACT_CHECK_ENGINE=duckduckgo (and internet access) "
        "for a real retrieval, or check the primary sources directly."
    ),
    "sources": [
        {
            "title": "Snopes",
            "url": "https://www.snopes.com/",
            "snippet": "General fact-check reference.",
        },
        {
            "title": "Full Fact",
            "url": "https://fullfact.org/",
            "snippet": "UK independent fact-checking charity.",
        },
        {
            "title": "Alt News (India)",
            "url": "https://www.altnews.in/",
            "snippet": "Indian fact-checking site.",
        },
    ],
}


class MockEngine(FactCheckEngine):
    name = "mock-knowledge-base"

    DISCLAIMER = (
        "MOCK ENGINE: this verdict came from a small hard-coded knowledge base of well-documented "
        "claims, not from live retrieval. It is for offline interface demonstration only."
    )

    def retrieve(self, claim: str) -> dict[str, Any]:
        low = claim.lower()
        for entry in KNOWLEDGE_BASE:
            if re.search(entry["match"], low):
                return {
                    "explanation_override": entry["explanation"],
                    "verdict_override": entry["verdict"],
                    "results": entry["sources"],
                    "warnings": [],
                }
        return {
            "explanation_override": DEFAULT["explanation"],
            "verdict_override": DEFAULT["verdict"],
            "results": DEFAULT["sources"],
            "warnings": ["Claim not present in the offline knowledge base."],
        }


__all__ = ["MockEngine", "KNOWLEDGE_BASE"]
