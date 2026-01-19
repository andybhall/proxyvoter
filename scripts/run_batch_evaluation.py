#!/usr/bin/env python3
"""
Batch evaluation script for all proposals and variants.

Usage: python3 scripts/run_batch_evaluation.py [--model MODEL] [--prompt PROMPT] [--force]

Options:
    --model MODEL   Which model to use (claude-sonnet, gpt-4o). Default: claude-sonnet
    --prompt PROMPT Which prompt template to use. Default: baseline
    --force         Re-evaluate even if cached results exist
    --list-prompts  List available prompt templates and exit

Evaluates:
1. All original proposals in data/proposals.json
2. All variants in data/variants.json

Results saved to cache/evaluations.json
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    load_proposals, load_variants, ProposalType,
    get_evaluation_for_proposal
)
from src.evaluate import (
    evaluate_proposal, get_today_spend_cents,
    list_available_prompts, PROMPT_TEMPLATES
)


def main():
    parser = argparse.ArgumentParser(description="Run batch evaluation of proposals")
    parser.add_argument(
        "--model",
        default="claude-sonnet",
        choices=["claude-sonnet", "gpt-4o"],
        help="Which model to use (default: claude-sonnet)"
    )
    parser.add_argument(
        "--prompt",
        default="baseline",
        choices=list_available_prompts(),
        help="Which prompt template to use (default: baseline)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-evaluate even if cached results exist"
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt templates and exit"
    )
    parser.add_argument(
        "--originals-only",
        action="store_true",
        help="Only evaluate original proposals, skip variants"
    )
    args = parser.parse_args()

    # List prompts and exit
    if args.list_prompts:
        print("Available prompt templates:\n")
        for name in list_available_prompts():
            template = PROMPT_TEMPLATES[name]
            # Show first line of template description
            first_line = template.split('\n')[0][:80]
            print(f"  {name:15} {first_line}...")
        sys.exit(0)

    print("=" * 60)
    print("BATCH EVALUATION")
    print(f"Model: {args.model}")
    print(f"Prompt: {args.prompt}")
    print(f"Force re-evaluation: {args.force}")
    print("=" * 60)

    # Load data
    proposals = load_proposals()
    variants = load_variants()

    if not proposals:
        print("\nERROR: No proposals found in data/proposals.json")
        print("Please seed the proposals file first.")
        sys.exit(1)

    print(f"\nFound {len(proposals)} proposals and {len(variants)} variants")
    print(f"Starting spend today: ${get_today_spend_cents()/100:.2f}")

    # Evaluate original proposals
    print("\n--- EVALUATING ORIGINAL PROPOSALS ---")
    original_count = 0
    original_cached = 0

    for proposal in proposals:
        # Check cache unless force
        if not args.force:
            existing = get_evaluation_for_proposal(
                proposal.id, ProposalType.ORIGINAL, args.model, args.prompt
            )
            if existing:
                print(f"  [cached] {proposal.id}: {existing.recommendation.value}")
                original_cached += 1
                continue

        try:
            evaluation = evaluate_proposal(
                proposal_text=proposal.text,
                proposal_id=proposal.id,
                proposal_type=ProposalType.ORIGINAL,
                model=args.model,
                prompt_name=args.prompt,
                use_cache=not args.force
            )
            print(f"  [done] {proposal.id}: {evaluation.recommendation.value}")
            original_count += 1
        except Exception as e:
            print(f"  [ERROR] {proposal.id}: {e}")

    print(f"\nOriginal proposals: {original_count} evaluated, {original_cached} cached")

    # Evaluate variants (unless --originals-only)
    if not args.originals_only:
        print("\n--- EVALUATING ADVERSARIAL VARIANTS ---")
        variant_count = 0
        variant_cached = 0

        for variant in variants:
            # Check cache unless force
            if not args.force:
                existing = get_evaluation_for_proposal(
                    variant.id, ProposalType.VARIANT, args.model, args.prompt
                )
                if existing:
                    print(f"  [cached] {variant.id}: {existing.recommendation.value}")
                    variant_cached += 1
                    continue

            try:
                evaluation = evaluate_proposal(
                    proposal_text=variant.text,
                    proposal_id=variant.id,
                    proposal_type=ProposalType.VARIANT,
                    model=args.model,
                    prompt_name=args.prompt,
                    use_cache=not args.force
                )
                print(f"  [done] {variant.id}: {evaluation.recommendation.value}")
                variant_count += 1
            except Exception as e:
                print(f"  [ERROR] {variant.id}: {e}")

        print(f"\nVariants: {variant_count} evaluated, {variant_cached} cached")
    else:
        variant_count = 0
        variant_cached = 0
        print("\n(Skipping variants due to --originals-only)")

    # Summary
    print("\n" + "=" * 60)
    print("BATCH EVALUATION COMPLETE")
    print(f"Total API calls: {original_count + variant_count}")
    print(f"Total cached: {original_cached + variant_cached}")
    print(f"Ending spend today: ${get_today_spend_cents()/100:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
