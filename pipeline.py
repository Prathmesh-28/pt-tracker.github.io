"""Search-backed extraction pipeline.

Two calls per task instead of one:
  1. research()  - a web-search turn that reports findings as prose
  2. extract()   - a no-tools turn constrained by a JSON schema

The split is what removes the regex parsing. Structured outputs guarantee the
extraction response is schema-valid JSON, so there is nothing to slice.
"""

from __future__ import annotations

import json
from typing import Literal, Sequence, Type, TypeVar

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5"

# Research turns run long and produce long output. Stream them so a big
# max_tokens cannot trip the HTTP timeout.
RESEARCH_MAX_TOKENS = 32_000
EXTRACT_MAX_TOKENS = 16_000

# Credentials resolve from ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / an
# `ant auth login` profile. Never hardcode a key.
client = anthropic.Anthropic()

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------
# Schemas. Structured outputs need an object at the root, so a task that wants
# a JSON array declares a one-field wrapper and you emit that field.
# --------------------------------------------------------------------------

class Role(BaseModel):
    title: str
    company: str
    location: str
    pay: str = Field(description='Rupee LPA range, or exactly "Not listed"')
    note: str = Field(description="One sentence on fit or deadline")
    url: str


class Roles(BaseModel):
    roles: list[Role]


class FundedCompany(BaseModel):
    company: str
    round: str = Field(description='e.g. "Series B, $40M"')
    date: str
    investors: str
    sector: str
    city: str
    hiring: str = Field(description='Functions hiring, or "unknown"')
    careers_url: str
    source_url: str


class FundedCompanies(BaseModel):
    companies: list[FundedCompany]


class HeadlineFinding(BaseModel):
    n: int
    company: str | None
    round: str | None
    investors: list[str]


class HeadlineFindings(BaseModel):
    findings: list[HeadlineFinding]


class CareersTiming(BaseModel):
    program: str
    status: Literal["open", "opens_later", "closed", "not_announced"]
    opens: str | None = Field(description="ISO date or null")
    closes: str | None = Field(description="ISO date or null")
    locations: list[str]
    eligibility: str
    confidence: Literal["high", "medium", "low"]
    quote: str = Field(description="Sentence the dates came from, under 15 words")
    checked_url: str


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------

def research(
    prompt: str,
    *,
    max_searches: int = 25,
    max_resumes: int = 5,
    effort: str = "high",
    allowed_domains: Sequence[str] | None = None,
) -> str:
    """Run a web-search turn to completion and return its prose findings.

    A search turn can stop with stop_reason "pause_turn" when the server-side
    tool hits an iteration limit. That is not an error and not the end of the
    answer - you re-send the conversation to continue it. Treating a paused
    turn as finished silently truncates the result.
    """
    tool: dict = {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": max_searches,
    }
    if allowed_domains:
        tool["allowed_domains"] = list(allowed_domains)

    messages: list[dict] = [{"role": "user", "content": prompt}]

    for attempt in range(max_resumes + 1):
        with client.messages.stream(
            model=MODEL,
            max_tokens=RESEARCH_MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            tools=[tool],
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "pause_turn":
            break
    else:
        raise RuntimeError(
            f"search turn still paused after {max_resumes} resumes; "
            "raise max_resumes or narrow the prompt"
        )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "research turn hit max_tokens - the findings are truncated. "
            "Raise RESEARCH_MAX_TOKENS or split the prompt."
        )
    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "category", None)
        raise RuntimeError(f"model declined the request (category: {detail})")

    return "\n".join(b.text for b in response.content if b.type == "text")


def extract(notes: str, schema: Type[T], instruction: str) -> T:
    """Turn prose findings into a schema-valid object. No tools, no parsing."""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=EXTRACT_MAX_TOKENS,
        output_format=schema,
        messages=[
            {
                "role": "user",
                "content": (
                    f"{instruction}\n\n"
                    "Use only what the notes below support. Do not add entries "
                    "the notes do not mention, and do not invent URLs or pay "
                    "figures.\n\n"
                    f"<notes>\n{notes}\n</notes>"
                ),
            }
        ],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "extraction hit max_tokens - the JSON is truncated. "
            "Raise EXTRACT_MAX_TOKENS or extract in batches."
        )
    return response.parsed_output


def fetch_page(prompt: str, *, max_fetches: int = 5) -> str:
    """Read specific URLs already named in the prompt.

    Web fetch only retrieves URLs that appear in the conversation, so the URL
    has to be in the prompt text - it will not go looking for one.
    """
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for _ in range(6):
        with client.messages.stream(
            model=MODEL,
            max_tokens=RESEARCH_MAX_TOKENS,
            thinking={"type": "adaptive"},
            tools=[
                {
                    "type": "web_fetch_20260209",
                    "name": "web_fetch",
                    "max_uses": max_fetches,
                }
            ],
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "pause_turn":
            break

    return "\n".join(b.text for b in response.content if b.type == "text")


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

def find_roles(
    *,
    role_families: Sequence[str],
    country: str = "India",
    cities: Sequence[str] = (),
    batch_years: Sequence[str] = ("2026", "2027"),
    max_years_experience: int = 1,
    degree: str = "engineering",
    as_of: str,
) -> list[dict]:
    """Filters are arguments, not literals in the prompt."""
    reject_at = max_years_experience + 1
    city_line = f" Focus on {', '.join(cities)}." if cities else ""

    notes = research(
        f"Today is {as_of}. Find currently open job postings in {country} for a "
        f"{'/'.join(batch_years)} {degree} graduate with 0-{max_years_experience} "
        f"years of experience.{city_line}\n\n"
        f"Role families: {'; '.join(role_families)}.\n\n"
        f"Reject anything requiring {reject_at}+ years, anything outside "
        f"{country}, and anything closed or expired. Search each family and "
        "each major job board separately rather than running one broad query. "
        "For every role, report the title, company, location, the experience "
        "line verbatim, the stated pay if any, and the exact URL you saw. "
        "Never write a URL you did not actually see in a result.\n\n"
        "Report what you found as notes. Do not format it as JSON."
    )

    result = extract(
        notes,
        Roles,
        f"List every role in the notes that is open in {country} and accepts "
        f"0-{max_years_experience} years of experience. Drop the rest. "
        'Set pay to exactly "Not listed" when the notes give no figure.',
    )
    return [r.model_dump() for r in result.roles]


def find_funded_companies(*, as_of: str, days: int = 60) -> list[dict]:
    notes = research(
        f"Today is {as_of}. Find Indian startups that announced a funding round "
        f"in the last {days} days and are now hiring. Prefer Series A and later, "
        "and prefer companies hiring generalist, growth, strategy, business or "
        "product roles rather than only engineers.\n\n"
        "For each, report the company, the round and amount, the announcement "
        "date, the investors, the sector, the city, which functions they are "
        "hiring for, their careers page, and the news source. Report what you "
        "found as notes. Do not format it as JSON."
    )
    result = extract(
        notes,
        FundedCompanies,
        f"List every company in the notes whose round was announced within "
        f"{days} days of {as_of}. Use \"unknown\" for hiring when the notes do "
        "not say.",
    )
    return [c.model_dump() for c in result.companies]


def classify_headlines(headlines: Sequence[str]) -> list[dict]:
    """Pure extraction - no search, so this is a single call."""
    numbered = "\n".join(f"{i}. {h}" for i, h in enumerate(headlines, 1))
    result = extract(
        numbered,
        HeadlineFindings,
        "For each headline, identify the company that RECEIVED the funding - "
        "not the investor, not the sector descriptor. Return null for company "
        "when the headline is not a funding round: an IPO, acquisition, stake "
        "sale, layoff, appointment, or fund launch. Return one finding per "
        "headline, in order, with n matching the headline number.",
    )
    return [f.model_dump() for f in result.findings]


def careers_timing(careers_url: str, *, as_of: str) -> dict:
    notes = fetch_page(
        f"Today is {as_of}. Read {careers_url} and report only what it says "
        "about application timing: the programme name, whether applications "
        "are open, the opening and closing dates, the locations, and the "
        "eligibility. Quote the sentence the dates come from. If the page "
        "states no dates, say so. Never infer dates from previous years."
    )
    result = extract(
        notes,
        CareersTiming,
        f'Fill the schema from the notes. checked_url is "{careers_url}". If '
        'the notes report no dates on the page, set status to "not_announced" '
        "and both dates to null. Never infer a date from a previous year.",
    )
    return result.model_dump()


if __name__ == "__main__":
    print(json.dumps(classify_headlines(["Example raises $40M Series B led by Accel"]), indent=2))
