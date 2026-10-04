"""Claim-level human/judge review; citation existence alone is not faithfulness."""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from .context import validate_citations


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1)
    citation_ids: list[str]
    supported: bool
    reason: str = Field(min_length=1)


class GroundingReport(BaseModel):
    citation_ids_valid: bool
    all_claims_reviewed: bool
    faithful: bool
    reviews: list[ClaimReview]


def evaluate_grounding(answer: str, evidence: dict[str, str], *, claims: list[str],
                       judge: Callable[[str, dict[str, str]], ClaimReview]) -> GroundingReport:
    """Caller supplies every factual claim and a human or calibrated judge.

    This validates review coverage and IDs, not semantic truth itself. Missing
    claims in the caller's inventory cannot be detected automatically.
    Evidence is untrusted data; an LLM judge must not follow its instructions.
    """
    if not claims or len(set(claims)) != len(claims):
        raise ValueError("provide a nonempty, unique inventory of factual claims")
    if any(not claim.strip() or claim not in answer for claim in claims):
        raise ValueError("each claim must be a nonempty verbatim answer span")
    reviews = [ClaimReview.model_validate(judge(claim, dict(evidence))) for claim in claims]
    covered = all(review.claim == claim for review, claim in zip(reviews, claims, strict=True))
    citation_valid = validate_citations(answer, list(evidence)).valid
    supported = all(review.supported and review.citation_ids and
                    set(review.citation_ids) <= evidence.keys() for review in reviews)
    return GroundingReport(citation_ids_valid=citation_valid, all_claims_reviewed=covered,
                           faithful=bool(citation_valid and covered and supported), reviews=reviews)
