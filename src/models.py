"""
Pydantic models for Proposal, AdversarialVariant, and Evaluation.
Includes utility functions for loading and saving data.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Data paths
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
PROPOSALS_PATH = DATA_DIR / "proposals.json"
VARIANTS_PATH = DATA_DIR / "variants.json"
EVALUATIONS_PATH = CACHE_DIR / "evaluations.json"
DAILY_COSTS_PATH = CACHE_DIR / "daily_costs.json"


class Category(str, Enum):
    CLIMATE = "climate"
    EXECUTIVE_COMP = "executive_comp"
    BOARD_DIVERSITY = "board_diversity"
    GOVERNANCE = "governance"
    POLITICAL_SPENDING = "political_spending"


class Recommendation(str, Enum):
    FOR = "FOR"
    AGAINST = "AGAINST"
    ABSTAIN = "ABSTAIN"


class AttackType(str, Enum):
    FRAMING = "framing"
    BURIED_LEDE = "buried_lede"
    INSTRUCTION_INJECTION = "instruction_injection"


class ProposalType(str, Enum):
    ORIGINAL = "original"
    VARIANT = "variant"


class Proposal(BaseModel):
    """A shareholder proposal from SEC filings."""
    id: str
    title: str
    text: str
    category: Category
    company: Optional[str] = None
    ticker: Optional[str] = None
    year: int
    iss_recommendation: Optional[Recommendation] = None
    glass_lewis_recommendation: Optional[Recommendation] = None
    vote_result_pct: Optional[float] = Field(default=None, ge=0, le=100)
    source_url: str

    @field_validator("iss_recommendation", "glass_lewis_recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v.upper()
        return v


class AdversarialVariant(BaseModel):
    """An adversarial modification of a proposal."""
    id: str
    original_proposal_id: str
    attack_type: AttackType
    text: str
    description: str
    changes_substance: bool = False

    @field_validator("changes_substance")
    @classmethod
    def substance_must_be_false(cls, v):
        if v:
            raise ValueError("changes_substance must be False for valid adversarial variants")
        return v


class Evaluation(BaseModel):
    """AI evaluation of a proposal."""
    id: str
    proposal_id: str
    proposal_type: ProposalType
    model: str
    prompt_name: str = "baseline"  # Which prompt template was used
    prompt_hash: str
    summary: str
    recommendation: Recommendation
    rationale: str
    raw_response: str
    timestamp: datetime
    cost_cents: float = 0.0

    @field_validator("recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v


class EvaluationRequest(BaseModel):
    """Input model for new evaluation requests."""
    proposal_text: str = Field(..., max_length=5000)
    model: str = "claude-sonnet"


# Utility functions

def load_proposals() -> list[Proposal]:
    """Load all proposals from data/proposals.json."""
    if not PROPOSALS_PATH.exists():
        return []
    with open(PROPOSALS_PATH, "r") as f:
        data = json.load(f)
    return [Proposal(**p) for p in data]


def load_variants() -> list[AdversarialVariant]:
    """Load all adversarial variants from data/variants.json."""
    if not VARIANTS_PATH.exists():
        return []
    with open(VARIANTS_PATH, "r") as f:
        data = json.load(f)
    return [AdversarialVariant(**v) for v in data]


def load_evaluations() -> list[Evaluation]:
    """Load all cached evaluations from cache/evaluations.json."""
    if not EVALUATIONS_PATH.exists():
        return []
    with open(EVALUATIONS_PATH, "r") as f:
        data = json.load(f)
    return [Evaluation(**e) for e in data]


def save_evaluation(evaluation: Evaluation) -> None:
    """Save a new evaluation to cache/evaluations.json."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    evaluations = load_evaluations()

    # Check if evaluation already exists (by id)
    existing_ids = {e.id for e in evaluations}
    if evaluation.id not in existing_ids:
        evaluations.append(evaluation)
    else:
        # Update existing
        evaluations = [e if e.id != evaluation.id else evaluation for e in evaluations]

    with open(EVALUATIONS_PATH, "w") as f:
        json.dump([e.model_dump(mode="json") for e in evaluations], f, indent=2, default=str)


def get_variant_for_proposal(proposal_id: str) -> Optional[AdversarialVariant]:
    """Get the adversarial variant for a given proposal ID."""
    variants = load_variants()
    for v in variants:
        if v.original_proposal_id == proposal_id:
            return v
    return None


def get_proposal_by_id(proposal_id: str) -> Optional[Proposal]:
    """Get a proposal by its ID."""
    proposals = load_proposals()
    for p in proposals:
        if p.id == proposal_id:
            return p
    return None


def get_evaluation_for_proposal(
    proposal_id: str,
    proposal_type: ProposalType,
    model: str,
    prompt_name: str = "baseline"
) -> Optional[Evaluation]:
    """Get cached evaluation for a proposal/variant, model, and prompt combination."""
    evaluations = load_evaluations()
    for e in evaluations:
        if (e.proposal_id == proposal_id and
            e.proposal_type == proposal_type and
            e.model == model and
            e.prompt_name == prompt_name):
            return e
    return None


def get_available_prompts() -> list[str]:
    """Get list of prompt names that have cached evaluations."""
    evaluations = load_evaluations()
    return sorted(set(e.prompt_name for e in evaluations))
