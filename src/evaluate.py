"""
AI evaluation logic with caching, rate limiting, and API calls.
"""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, date
from typing import Optional

from dotenv import load_dotenv

from src.models import (
    Evaluation, ProposalType, Recommendation,
    CACHE_DIR, DAILY_COSTS_PATH,
    load_evaluations, save_evaluation
)

load_dotenv()

# Named prompt templates for experimentation
PROMPT_TEMPLATES = {
    "baseline": """You are a proxy voting advisor helping institutional investors evaluate shareholder proposals. Your role is to provide objective analysis to help fiduciaries make informed voting decisions.

Read the following shareholder proposal and provide your analysis in the following format:

SUMMARY: [2-3 sentence summary of what the proposal asks the company to do]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences explaining your recommendation, considering factors like: impact on shareholder value, governance implications, implementation feasibility, and alignment with fiduciary duty]

---

PROPOSAL:

{proposal_text}""",

    "fiduciary": """You are a proxy voting advisor for large institutional investors with fiduciary duties to maximize long-term shareholder value. Your primary obligation is to your clients' financial interests.

When evaluating proposals, prioritize:
1. Quantifiable impact on shareholder returns
2. Cost-benefit analysis of implementation
3. Track record of similar proposals at other companies
4. Management's stated objections and their validity

Provide your analysis in this format:

SUMMARY: [2-3 sentence summary of what the proposal asks]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences focused on financial materiality and shareholder value impact]

---

PROPOSAL:

{proposal_text}""",

    "conservative": """You are a proxy voting advisor who generally supports management unless there is clear evidence of governance failures or value destruction. You believe boards and management teams are typically better positioned than shareholders to make operational decisions.

Your default position is to support management recommendations unless:
- There is evidence of significant governance failures
- The proposal addresses a clear, documented problem
- Implementation costs are minimal and benefits are concrete

Provide your analysis in this format:

SUMMARY: [2-3 sentence summary of what the proposal asks]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences explaining your recommendation, with particular attention to why departure from management's position is or is not warranted]

---

PROPOSAL:

{proposal_text}""",

    "iss_style": """You are a proxy voting advisor following ISS (Institutional Shareholder Services) methodology. ISS generally supports shareholder proposals that:
- Enhance board accountability and independence
- Improve transparency and disclosure
- Align executive pay with performance
- Address material environmental and social risks

ISS generally opposes proposals that:
- Are overly prescriptive about business operations
- Duplicate existing practices or disclosures
- Would impose unreasonable costs or burdens

Provide your analysis in this format:

SUMMARY: [2-3 sentence summary of what the proposal asks]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences explaining your recommendation based on ISS-style governance principles]

---

PROPOSAL:

{proposal_text}""",

    "iss_detailed": """You are a proxy voting advisor applying ISS (Institutional Shareholder Services) benchmark policy guidelines. Apply these specific policies:

PROXY ACCESS PROPOSALS:
- SUPPORT proxy access with 3% ownership / 3-year holding / up to 25% of board
- OPPOSE proposals that lower thresholds below 3% or reduce holding periods below 3 years
- OPPOSE removing aggregation limits if current limits are reasonable (20+ shareholders)
- If a company already has proxy access meeting these standards, OPPOSE changes

CLIMATE & ENVIRONMENTAL:
- SUPPORT requests for disclosure of climate risks, emissions data, or transition plans
- OPPOSE proposals that dictate specific operational changes or emissions targets
- OPPOSE proposals requesting companies exit business lines or cease operations

POLITICAL SPENDING & LOBBYING:
- SUPPORT disclosure of political contributions and lobbying expenditures
- SUPPORT reports on alignment between political spending and stated values
- OPPOSE proposals that would prohibit all political activity

EXECUTIVE COMPENSATION:
- SUPPORT say-on-pay when pay is reasonably aligned with performance
- SUPPORT clawback policies for misconduct
- OPPOSE proposals that are overly prescriptive about pay structure

SOCIAL & WORKFORCE PROPOSALS:
- OPPOSE proposals focused on wage levels, living wage analyses, or pay equity reports (these are operational matters for management)
- OPPOSE proposals that are primarily ideological rather than addressing material business risks
- SUPPORT diversity disclosure when focused on board/management composition

TAX TRANSPARENCY:
- Generally OPPOSE country-by-country tax reporting proposals (overly burdensome, competitively sensitive)
- May support basic tax policy disclosure

BOARD DIVERSITY:
- SUPPORT requests for diversity disclosure
- SUPPORT policies promoting diverse boards
- OPPOSE rigid quotas

When in doubt, ask: Does this proposal address a material governance issue, or is it primarily social/political advocacy? ISS supports governance reforms but is skeptical of proposals that substitute shareholder judgment for management on operational matters.

Provide your analysis in this format:

SUMMARY: [2-3 sentence summary of what the proposal asks]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences explaining your recommendation, citing the specific ISS policy that applies]

---

PROPOSAL:

{proposal_text}""",

    "skeptical": """You are a proxy voting advisor who is skeptical of shareholder proposals, particularly those related to environmental, social, and political issues. You believe:
- Companies should focus on their core business operations
- Many ESG proposals impose costs without clear shareholder benefits
- Disclosure requests can become burdensome compliance exercises
- Shareholders should defer to management on most operational matters

Only support proposals where there is clear, direct financial benefit to shareholders.

Provide your analysis in this format:

SUMMARY: [2-3 sentence summary of what the proposal asks]

RECOMMENDATION: [FOR or AGAINST or ABSTAIN]

RATIONALE: [3-5 sentences explaining your recommendation, focusing on whether the proposal serves concrete shareholder financial interests]

---

PROPOSAL:

{proposal_text}"""
}

# Default prompt for backward compatibility
PROMPT_TEMPLATE = PROMPT_TEMPLATES["baseline"]


def get_prompt_template(prompt_name: str) -> str:
    """Get a prompt template by name."""
    if prompt_name not in PROMPT_TEMPLATES:
        available = ", ".join(PROMPT_TEMPLATES.keys())
        raise ValueError(f"Unknown prompt: {prompt_name}. Available: {available}")
    return PROMPT_TEMPLATES[prompt_name]


def list_available_prompts() -> list[str]:
    """List all available prompt template names."""
    return list(PROMPT_TEMPLATES.keys())


def get_prompt_hash(proposal_text: str, model: str, prompt_name: str = "baseline") -> str:
    """Generate a hash of the prompt for cache key."""
    template = get_prompt_template(prompt_name)
    content = f"{template}{proposal_text}{model}{prompt_name}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_ai_response(raw_response: str) -> dict:
    """
    Extract structured fields from AI response.
    Returns {"summary": str, "recommendation": str, "rationale": str}
    """
    result = {
        "summary": "",
        "recommendation": "ABSTAIN",
        "rationale": ""
    }

    # Extract SUMMARY
    summary_match = re.search(r"SUMMARY:\s*(.+?)(?=RECOMMENDATION:|$)", raw_response, re.DOTALL | re.IGNORECASE)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()

    # Extract RECOMMENDATION
    rec_match = re.search(r"RECOMMENDATION:\s*(FOR|AGAINST|ABSTAIN)", raw_response, re.IGNORECASE)
    if rec_match:
        result["recommendation"] = rec_match.group(1).upper()

    # Extract RATIONALE
    rationale_match = re.search(r"RATIONALE:\s*(.+?)$", raw_response, re.DOTALL | re.IGNORECASE)
    if rationale_match:
        result["rationale"] = rationale_match.group(1).strip()

    return result


def get_cached_evaluation(
    proposal_id: str,
    proposal_type: ProposalType,
    model: str,
    prompt_name: str,
    prompt_hash: str
) -> Optional[Evaluation]:
    """Check if we have a cached evaluation for this exact configuration."""
    evaluations = load_evaluations()
    for e in evaluations:
        if (e.proposal_id == proposal_id and
            e.proposal_type == proposal_type and
            e.model == model and
            e.prompt_name == prompt_name and
            e.prompt_hash == prompt_hash):
            return e
    return None


def get_cached_evaluation_by_text(
    proposal_text: str,
    model: str,
    prompt_name: str = "baseline"
) -> Optional[Evaluation]:
    """Check cache by text hash (for custom submissions)."""
    prompt_hash = get_prompt_hash(proposal_text, model, prompt_name)
    evaluations = load_evaluations()
    for e in evaluations:
        if e.prompt_hash == prompt_hash and e.model == model and e.prompt_name == prompt_name:
            return e
    return None


# Cost tracking

def load_daily_costs() -> dict:
    """Load daily cost tracking data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not DAILY_COSTS_PATH.exists():
        return {}
    with open(DAILY_COSTS_PATH, "r") as f:
        return json.load(f)


def save_daily_costs(costs: dict) -> None:
    """Save daily cost tracking data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DAILY_COSTS_PATH, "w") as f:
        json.dump(costs, f, indent=2)


def get_today_spend_cents() -> float:
    """Get total spend for today in cents."""
    costs = load_daily_costs()
    today = date.today().isoformat()
    return costs.get(today, 0.0)


def add_cost(cost_cents: float) -> None:
    """Add cost to today's total."""
    costs = load_daily_costs()
    today = date.today().isoformat()
    costs[today] = costs.get(today, 0.0) + cost_cents
    save_daily_costs(costs)


def check_daily_budget() -> tuple[bool, str]:
    """Check if daily budget is exceeded."""
    budget_cents = float(os.getenv("DAILY_BUDGET_CENTS", "500"))
    spent = get_today_spend_cents()
    if spent >= budget_cents:
        return False, f"Daily budget exceeded (${spent/100:.2f} of ${budget_cents/100:.2f})"
    return True, ""


# Session rate limiting (for interactive tool)

_session_counts: dict[str, int] = {}
MAX_SESSION_EVALUATIONS = 10


def check_rate_limit(session_id: str) -> tuple[bool, str]:
    """
    Check if this session can make another custom evaluation.
    Returns (allowed: bool, reason: str if not allowed)
    """
    # Check daily budget first
    budget_ok, budget_reason = check_daily_budget()
    if not budget_ok:
        return False, budget_reason

    # Check session limit
    count = _session_counts.get(session_id, 0)
    if count >= MAX_SESSION_EVALUATIONS:
        return False, f"Session limit reached ({MAX_SESSION_EVALUATIONS} evaluations)"

    return True, ""


def increment_session_count(session_id: str) -> None:
    """Increment the evaluation count for a session."""
    _session_counts[session_id] = _session_counts.get(session_id, 0) + 1


def get_session_remaining(session_id: str) -> int:
    """Get remaining evaluations for a session."""
    return MAX_SESSION_EVALUATIONS - _session_counts.get(session_id, 0)


# API calls

def call_claude(proposal_text: str, prompt_name: str = "baseline") -> tuple[str, float]:
    """
    Call Claude API for evaluation.
    Returns (response_text, cost_cents)
    """
    import anthropic

    client = anthropic.Anthropic()
    template = get_prompt_template(prompt_name)
    prompt = template.format(proposal_text=proposal_text)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = message.content[0].text

    # Estimate cost (Claude Sonnet: $3/M input, $15/M output)
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    cost_cents = (input_tokens * 0.3 / 1000) + (output_tokens * 1.5 / 1000)

    return response_text, cost_cents


def call_openai(proposal_text: str, prompt_name: str = "baseline") -> tuple[str, float]:
    """
    Call OpenAI GPT-4o API for evaluation.
    Returns (response_text, cost_cents)
    """
    from openai import OpenAI

    client = OpenAI()
    template = get_prompt_template(prompt_name)
    prompt = template.format(proposal_text=proposal_text)

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = response.choices[0].message.content

    # Estimate cost (GPT-4o: $2.5/M input, $10/M output)
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    cost_cents = (input_tokens * 0.25 / 1000) + (output_tokens * 1.0 / 1000)

    return response_text, cost_cents


def evaluate_proposal(
    proposal_text: str,
    proposal_id: str,
    proposal_type: ProposalType,
    model: str = "claude-sonnet",
    prompt_name: str = "baseline",
    use_cache: bool = True,
    session_id: Optional[str] = None
) -> Evaluation:
    """
    Send proposal to AI for evaluation.

    1. Check cache first (hash of proposal_text + model + prompt)
    2. If not cached, call API
    3. Parse response to extract summary, recommendation, rationale
    4. Save to cache
    5. Track cost

    Returns Evaluation object.
    """
    prompt_hash = get_prompt_hash(proposal_text, model, prompt_name)

    # Check cache
    if use_cache:
        cached = get_cached_evaluation(proposal_id, proposal_type, model, prompt_name, prompt_hash)
        if cached:
            print(f"  [cache hit] {proposal_id}")
            return cached

    # Check rate limits for interactive sessions
    if session_id:
        allowed, reason = check_rate_limit(session_id)
        if not allowed:
            raise RuntimeError(f"Rate limited: {reason}")

    print(f"  [api call] {proposal_id} with {model}/{prompt_name}...")

    # Call API
    if model == "claude-sonnet":
        raw_response, cost_cents = call_claude(proposal_text, prompt_name)
    elif model == "gpt-4o":
        raw_response, cost_cents = call_openai(proposal_text, prompt_name)
    else:
        raise ValueError(f"Unknown model: {model}")

    # Parse response
    parsed = parse_ai_response(raw_response)

    # Create evaluation
    evaluation = Evaluation(
        id=f"eval-{uuid.uuid4().hex[:8]}",
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        model=model,
        prompt_name=prompt_name,
        prompt_hash=prompt_hash,
        summary=parsed["summary"],
        recommendation=Recommendation(parsed["recommendation"]),
        rationale=parsed["rationale"],
        raw_response=raw_response,
        timestamp=datetime.now(),
        cost_cents=cost_cents
    )

    # Save to cache and track cost
    save_evaluation(evaluation)
    add_cost(cost_cents)

    if session_id:
        increment_session_count(session_id)

    return evaluation


def evaluate_custom_text(
    proposal_text: str,
    model: str = "claude-sonnet",
    prompt_name: str = "baseline",
    session_id: Optional[str] = None
) -> Evaluation:
    """
    Evaluate a custom (user-submitted) proposal text.
    Uses text hash as the proposal_id.
    """
    text_hash = hashlib.sha256(proposal_text.encode()).hexdigest()[:12]
    proposal_id = f"custom-{text_hash}"

    # Check cache by text
    cached = get_cached_evaluation_by_text(proposal_text, model, prompt_name)
    if cached:
        print(f"  [cache hit] custom text")
        return cached

    return evaluate_proposal(
        proposal_text=proposal_text,
        proposal_id=proposal_id,
        proposal_type=ProposalType.ORIGINAL,
        model=model,
        prompt_name=prompt_name,
        use_cache=True,
        session_id=session_id
    )
