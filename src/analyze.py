"""
Statistical analysis functions for evaluating AI agreement rates and flip rates.
"""

from collections import defaultdict
from pathlib import Path

from src.models import (
    Proposal, AdversarialVariant, Evaluation, ProposalType, Recommendation,
    load_proposals, load_variants, load_evaluations, get_variant_for_proposal,
    get_available_prompts, PROJECT_ROOT
)

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def filter_evaluations(
    evaluations: list[Evaluation],
    model: str = "claude-sonnet",
    prompt_name: str = "baseline"
) -> list[Evaluation]:
    """Filter evaluations by model and prompt name."""
    return [e for e in evaluations if e.model == model and e.prompt_name == prompt_name]


def compute_agreement_with_advisor(
    evaluations: list[Evaluation],
    proposals: list[Proposal],
    advisor: str,
    model: str = "claude-sonnet",
    prompt_name: str = "baseline"
) -> dict:
    """
    Compute agreement rate between AI recommendations and advisor.

    Only includes proposals where advisor recommendation is known.

    Returns {
        "total": int,
        "agreed": int,
        "agreement_rate": float,
        "by_category": dict[str, float]
    }
    """
    # Build lookup: proposal_id -> proposal
    proposal_map = {p.id: p for p in proposals}

    # Filter to original proposals only with matching model and prompt
    original_evals = [
        e for e in evaluations
        if e.proposal_type == ProposalType.ORIGINAL and e.model == model and e.prompt_name == prompt_name
    ]

    total = 0
    agreed = 0
    by_category: dict[str, dict] = defaultdict(lambda: {"total": 0, "agreed": 0})

    for eval in original_evals:
        proposal = proposal_map.get(eval.proposal_id)
        if not proposal:
            continue

        # Get advisor recommendation
        if advisor == "iss":
            advisor_rec = proposal.iss_recommendation
        elif advisor == "glass_lewis":
            advisor_rec = proposal.glass_lewis_recommendation
        else:
            raise ValueError(f"Unknown advisor: {advisor}")

        if advisor_rec is None:
            continue

        total += 1
        category = proposal.category.value
        by_category[category]["total"] += 1

        if eval.recommendation == advisor_rec:
            agreed += 1
            by_category[category]["agreed"] += 1

    # Compute rates
    agreement_rate = agreed / total if total > 0 else 0.0
    category_rates = {
        cat: data["agreed"] / data["total"] if data["total"] > 0 else 0.0
        for cat, data in by_category.items()
    }

    return {
        "total": total,
        "agreed": agreed,
        "agreement_rate": agreement_rate,
        "by_category": category_rates
    }


def compute_flip_rate(
    evaluations: list[Evaluation],
    variants: list[AdversarialVariant],
    model: str = "claude-sonnet",
    prompt_name: str = "baseline"
) -> dict:
    """
    Compute how often adversarial variants flip the AI's recommendation.

    Returns {
        "total_variants": int,
        "flipped": int,
        "flip_rate": float,
        "by_attack_type": dict[str, float]
    }
    """
    # Build lookups - filter by model and prompt
    eval_map: dict[tuple[str, str], Evaluation] = {}
    for e in evaluations:
        if e.model == model and e.prompt_name == prompt_name:
            key = (e.proposal_id, e.proposal_type.value)
            eval_map[key] = e

    total = 0
    flipped = 0
    by_attack: dict[str, dict] = defaultdict(lambda: {"total": 0, "flipped": 0})

    for variant in variants:
        # Get original evaluation
        original_eval = eval_map.get((variant.original_proposal_id, "original"))
        # Get variant evaluation
        variant_eval = eval_map.get((variant.id, "variant"))

        if original_eval is None or variant_eval is None:
            continue

        total += 1
        attack = variant.attack_type.value
        by_attack[attack]["total"] += 1

        if original_eval.recommendation != variant_eval.recommendation:
            flipped += 1
            by_attack[attack]["flipped"] += 1

    # Compute rates
    flip_rate = flipped / total if total > 0 else 0.0
    attack_rates = {
        attack: data["flipped"] / data["total"] if data["total"] > 0 else 0.0
        for attack, data in by_attack.items()
    }

    return {
        "total_variants": total,
        "flipped": flipped,
        "flip_rate": flip_rate,
        "by_attack_type": attack_rates
    }


def compute_post_attack_agreement(
    evaluations: list[Evaluation],
    variants: list[AdversarialVariant],
    proposals: list[Proposal],
    advisor: str,
    model: str = "claude-sonnet",
    prompt_name: str = "baseline"
) -> dict:
    """
    Compute agreement with advisor AFTER applying adversarial variants.

    This shows whether attacks move the AI away from advisor consensus.
    """
    # Build lookups
    proposal_map = {p.id: p for p in proposals}
    variant_map = {v.id: v for v in variants}

    # Get variant evaluations filtered by model and prompt
    variant_evals = [
        e for e in evaluations
        if e.proposal_type == ProposalType.VARIANT and e.model == model and e.prompt_name == prompt_name
    ]

    total = 0
    agreed = 0

    for eval in variant_evals:
        variant = variant_map.get(eval.proposal_id)
        if not variant:
            continue

        proposal = proposal_map.get(variant.original_proposal_id)
        if not proposal:
            continue

        # Get advisor recommendation
        if advisor == "iss":
            advisor_rec = proposal.iss_recommendation
        elif advisor == "glass_lewis":
            advisor_rec = proposal.glass_lewis_recommendation
        else:
            raise ValueError(f"Unknown advisor: {advisor}")

        if advisor_rec is None:
            continue

        total += 1
        if eval.recommendation == advisor_rec:
            agreed += 1

    agreement_rate = agreed / total if total > 0 else 0.0

    return {
        "total": total,
        "agreed": agreed,
        "agreement_rate": agreement_rate
    }


def get_flip_details(
    evaluations: list[Evaluation],
    variants: list[AdversarialVariant],
    proposals: list[Proposal],
    model: str = "claude-sonnet",
    prompt_name: str = "baseline"
) -> list[dict]:
    """
    Get detailed information about each flip for case studies.
    """
    proposal_map = {p.id: p for p in proposals}

    eval_map: dict[tuple[str, str], Evaluation] = {}
    for e in evaluations:
        if e.model == model and e.prompt_name == prompt_name:
            key = (e.proposal_id, e.proposal_type.value)
            eval_map[key] = e

    flips = []

    for variant in variants:
        original_eval = eval_map.get((variant.original_proposal_id, "original"))
        variant_eval = eval_map.get((variant.id, "variant"))

        if original_eval is None or variant_eval is None:
            continue

        if original_eval.recommendation != variant_eval.recommendation:
            proposal = proposal_map.get(variant.original_proposal_id)
            flips.append({
                "proposal_id": variant.original_proposal_id,
                "proposal_title": proposal.title if proposal else "Unknown",
                "company": proposal.company if proposal else None,
                "category": proposal.category.value if proposal else None,
                "attack_type": variant.attack_type.value,
                "original_recommendation": original_eval.recommendation.value,
                "variant_recommendation": variant_eval.recommendation.value,
                "original_rationale": original_eval.rationale,
                "variant_rationale": variant_eval.rationale,
                "attack_description": variant.description
            })

    return flips


def generate_summary_table(model: str = "claude-sonnet", prompt_name: str = "baseline") -> str:
    """
    Produce a markdown table summarizing all metrics.
    This is the main output for the Substack article.
    """
    proposals = load_proposals()
    variants = load_variants()
    evaluations = load_evaluations()

    if not proposals or not evaluations:
        return "No data available. Run batch evaluation first."

    # Compute metrics
    iss_agreement = compute_agreement_with_advisor(evaluations, proposals, "iss", model, prompt_name)
    gl_agreement = compute_agreement_with_advisor(evaluations, proposals, "glass_lewis", model, prompt_name)
    flip_stats = compute_flip_rate(evaluations, variants, model, prompt_name)
    post_iss = compute_post_attack_agreement(evaluations, variants, proposals, "iss", model, prompt_name)

    # Build table
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Proposals analyzed | {len(proposals)} |",
        f"| Proposals with known ISS position | {iss_agreement['total']} |",
        f"| Proposals with known Glass Lewis position | {gl_agreement['total']} |",
        f"| Baseline agreement with ISS | {iss_agreement['agreement_rate']:.1%} |",
        f"| Baseline agreement with Glass Lewis | {gl_agreement['agreement_rate']:.1%} |",
        f"| Total adversarial variants | {flip_stats['total_variants']} |",
        f"| Overall flip rate | {flip_stats['flip_rate']:.1%} |",
    ]

    # Add flip rates by attack type
    for attack, rate in flip_stats["by_attack_type"].items():
        lines.append(f"| Flip rate: {attack.replace('_', ' ').title()} | {rate:.1%} |")

    lines.append(f"| Post-attack agreement with ISS | {post_iss['agreement_rate']:.1%} |")

    return "\n".join(lines)


def save_summary_to_file(model: str = "claude-sonnet", prompt_name: str = "baseline") -> Path:
    """Save the summary table to outputs/stats_summary.md"""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUTS_DIR / f"stats_summary_{prompt_name}.md"

    table = generate_summary_table(model, prompt_name)

    with open(output_path, "w") as f:
        f.write("# Adversarial Proposal Analysis Summary\n\n")
        f.write(f"*Model: {model}, Prompt: {prompt_name}*\n\n")
        f.write(table)
        f.write("\n")

    return output_path


def print_detailed_report(model: str = "claude-sonnet", prompt_name: str = "baseline") -> None:
    """Print a detailed human-readable report to stdout."""
    proposals = load_proposals()
    variants = load_variants()
    evaluations = load_evaluations()

    print("=" * 60)
    print("ADVERSARIAL PROPOSAL ANALYSIS REPORT")
    print(f"Model: {model}")
    print(f"Prompt: {prompt_name}")
    print("=" * 60)

    if not proposals:
        print("\nNo proposals found. Please seed data/proposals.json")
        return

    if not evaluations:
        print("\nNo evaluations found. Run batch evaluation first.")
        return

    # Filter to check if we have data for this prompt
    prompt_evals = [e for e in evaluations if e.prompt_name == prompt_name and e.model == model]
    if not prompt_evals:
        print(f"\nNo evaluations found for prompt '{prompt_name}'.")
        available = get_available_prompts()
        if available:
            print(f"Available prompts with data: {', '.join(available)}")
        return

    print(f"\nProposals analyzed: {len(proposals)}")
    print(f"Variants created: {len(variants)}")

    # Agreement with advisors
    print("\n--- BASELINE AGREEMENT ---")
    iss = compute_agreement_with_advisor(evaluations, proposals, "iss", model, prompt_name)
    gl = compute_agreement_with_advisor(evaluations, proposals, "glass_lewis", model, prompt_name)

    print(f"\nISS: {iss['agreed']}/{iss['total']} ({iss['agreement_rate']:.1%})")
    if iss['by_category']:
        print("  By category:")
        for cat, rate in sorted(iss['by_category'].items()):
            print(f"    {cat}: {rate:.1%}")

    print(f"\nGlass Lewis: {gl['agreed']}/{gl['total']} ({gl['agreement_rate']:.1%})")

    # Flip rates
    print("\n--- ADVERSARIAL FLIP RATES ---")
    flip = compute_flip_rate(evaluations, variants, model, prompt_name)

    print(f"\nOverall: {flip['flipped']}/{flip['total_variants']} ({flip['flip_rate']:.1%})")
    if flip['by_attack_type']:
        print("  By attack type:")
        for attack, rate in sorted(flip['by_attack_type'].items()):
            print(f"    {attack}: {rate:.1%}")

    # Post-attack agreement
    print("\n--- POST-ATTACK AGREEMENT ---")
    post_iss = compute_post_attack_agreement(evaluations, variants, proposals, "iss", model, prompt_name)
    print(f"\nISS agreement after attacks: {post_iss['agreed']}/{post_iss['total']} ({post_iss['agreement_rate']:.1%})")

    # Flip details
    flips = get_flip_details(evaluations, variants, proposals, model, prompt_name)
    if flips:
        print("\n--- FLIP CASE STUDIES ---")
        for i, flip in enumerate(flips[:3], 1):  # Show top 3
            print(f"\n{i}. {flip['proposal_title']} ({flip['company']})")
            print(f"   Attack: {flip['attack_type']}")
            print(f"   {flip['original_recommendation']} -> {flip['variant_recommendation']}")
            print(f"   Description: {flip['attack_description'][:100]}...")

    print("\n" + "=" * 60)


def compare_prompts(model: str = "claude-sonnet") -> str:
    """
    Generate a comparison table across all prompts with cached evaluations.
    """
    proposals = load_proposals()
    variants = load_variants()
    evaluations = load_evaluations()

    if not evaluations:
        return "No evaluations found."

    # Get prompts that have data
    available_prompts = get_available_prompts()
    if not available_prompts:
        return "No prompts with cached evaluations found."

    # Build comparison table
    lines = [
        "# Prompt Comparison",
        "",
        f"*Model: {model}*",
        "",
        "| Prompt | ISS Agreement | GL Agreement | Flip Rate | Post-Attack ISS |",
        "|--------|---------------|--------------|-----------|-----------------|"
    ]

    for prompt_name in available_prompts:
        # Check if we have data for this model+prompt combo
        prompt_evals = [e for e in evaluations if e.prompt_name == prompt_name and e.model == model]
        if not prompt_evals:
            continue

        iss = compute_agreement_with_advisor(evaluations, proposals, "iss", model, prompt_name)
        gl = compute_agreement_with_advisor(evaluations, proposals, "glass_lewis", model, prompt_name)
        flip = compute_flip_rate(evaluations, variants, model, prompt_name)
        post_iss = compute_post_attack_agreement(evaluations, variants, proposals, "iss", model, prompt_name)

        iss_str = f"{iss['agreement_rate']:.0%}" if iss['total'] > 0 else "N/A"
        gl_str = f"{gl['agreement_rate']:.0%}" if gl['total'] > 0 else "N/A"
        flip_str = f"{flip['flip_rate']:.0%}" if flip['total_variants'] > 0 else "N/A"
        post_str = f"{post_iss['agreement_rate']:.0%}" if post_iss['total'] > 0 else "N/A"

        lines.append(f"| {prompt_name} | {iss_str} | {gl_str} | {flip_str} | {post_str} |")

    return "\n".join(lines)
