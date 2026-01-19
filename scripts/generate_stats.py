#!/usr/bin/env python3
"""
Generate summary statistics from cached evaluations.

Usage:
  python3 scripts/generate_stats.py [--model MODEL] [--prompt PROMPT]
  python3 scripts/generate_stats.py --compare-prompts

Reads cached evaluations and produces:
1. outputs/stats_summary_<prompt>.md - Markdown table for the article
2. Prints human-readable summary to stdout

Requires batch evaluation to have been run first.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyze import (
    print_detailed_report,
    save_summary_to_file,
    generate_summary_table,
    compare_prompts
)
from src.models import load_evaluations, get_available_prompts
from src.evaluate import list_available_prompts


def main():
    parser = argparse.ArgumentParser(description="Generate summary statistics")
    parser.add_argument(
        "--model",
        default="claude-sonnet",
        choices=["claude-sonnet", "gpt-4o"],
        help="Which model's evaluations to analyze (default: claude-sonnet)"
    )
    parser.add_argument(
        "--prompt",
        default="baseline",
        help="Which prompt's evaluations to analyze (default: baseline)"
    )
    parser.add_argument(
        "--compare-prompts",
        action="store_true",
        help="Compare results across all prompts with cached data"
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List prompts that have cached evaluation data"
    )
    args = parser.parse_args()

    # Check if evaluations exist
    evaluations = load_evaluations()
    if not evaluations:
        print("ERROR: No evaluations found in cache/evaluations.json")
        print("Please run batch evaluation first:")
        print("  python3 scripts/run_batch_evaluation.py")
        sys.exit(1)

    # List prompts with data
    if args.list_prompts:
        available = get_available_prompts()
        all_prompts = list_available_prompts()
        print("Prompts with cached evaluation data:")
        for p in all_prompts:
            has_data = "✓" if p in available else " "
            print(f"  [{has_data}] {p}")
        sys.exit(0)

    # Compare prompts
    if args.compare_prompts:
        comparison = compare_prompts(args.model)
        print(comparison)

        # Save to file
        output_path = Path("outputs") / "prompt_comparison.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(comparison)
        print(f"\nSaved to: {output_path}")
        sys.exit(0)

    # Validate prompt has data
    available = get_available_prompts()
    if args.prompt not in available:
        print(f"ERROR: No evaluations found for prompt '{args.prompt}'")
        if available:
            print(f"Available prompts with data: {', '.join(available)}")
        else:
            print("No prompts have cached data. Run batch evaluation first.")
        sys.exit(1)

    # Print detailed report
    print_detailed_report(args.model, args.prompt)

    # Save markdown table
    output_path = save_summary_to_file(args.model, args.prompt)
    print(f"\nMarkdown table saved to: {output_path}")

    # Also print the table for easy copy-paste
    print("\n--- MARKDOWN TABLE ---")
    print(generate_summary_table(args.model, args.prompt))


if __name__ == "__main__":
    main()
