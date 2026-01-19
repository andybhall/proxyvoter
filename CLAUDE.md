# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

This project demonstrates how AI-based proxy voting advisors can be manipulated through adversarial proposal language. It produces:
1. **Statistical Analysis**: Batch evaluation of AI agreement rates with ISS/Glass Lewis, and flip rates under adversarial modifications
2. **Interactive Explorer**: Streamlit web tool for viewing proposals and testing adversarial variants

See `INSTRUCTIONS.md` for full architecture specification and `SOUL.md` for research principles.

---

## Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
cp .env.example .env  # then add API keys

# Run batch evaluation (all proposals + variants)
python3 scripts/run_batch_evaluation.py
python3 scripts/run_batch_evaluation.py --model gpt-4o --force  # re-run with GPT-4o

# Generate statistics for article
python3 scripts/generate_stats.py

# Run interactive Streamlit app
streamlit run src/app.py
```

---

## Architecture

### Data Flow
```
data/proposals.json → src/evaluate.py → cache/evaluations.json → src/analyze.py → outputs/stats_summary.md
data/variants.json  ↗
```

### Key Files
- `src/models.py`: Pydantic models (Proposal, AdversarialVariant, Evaluation) and data loading utilities
- `src/evaluate.py`: AI evaluation logic with caching, rate limiting, and API calls (Anthropic/OpenAI)
- `src/analyze.py`: Statistical analysis (agreement rates, flip rates, summary tables)
- `src/app.py`: Streamlit interactive tool

### Data Model
- **Proposals** (`data/proposals.json`): Shareholder proposals with ISS/Glass Lewis recommendations
- **Variants** (`data/variants.json`): Adversarial modifications (framing, buried_lede, instruction_injection)
- **Evaluations** (`cache/evaluations.json`): Cached AI recommendations and rationale

### Attack Types
1. `framing`: Same ask, different rhetorical packaging (e.g., environmental advocacy → fiduciary risk)
2. `buried_lede`: Bury actual request deep in context paragraphs
3. `instruction_injection`: Embed fake consensus claims or evaluative framing

---

## Critical Workflow Requirements

**These rules are non-negotiable.**

1. **Never claim something works without running a test to prove it.** After writing any code, immediately write and run a test. If you cannot test it, say so explicitly. "It should work" is not acceptable—show me that it works.

2. **Work modularly.** Complete one module or task at a time. After each module, report what you built, show test results, and wait for confirmation before proceeding.

3. **Iterate and fix errors yourself.** Run the code, observe the output, and fix problems before presenting results.

4. **Be explicit about unknowns.** If you're uncertain about something, say so. Don't guess. Don't confabulate.

5. **Use python3 and pip3.** Always use `python3` (not `python`) and `pip3` (not `pip`) for all commands.

---

## Data Handling

- **Preserve raw data.** Never modify original data files. Transformations produce new files in `cache/` or `outputs/`.
- **Verify completeness.** After collecting/processing data, verify counts, check for anomalies.
- **Verify merges.** After any merge, check observation counts and unexpected duplicates.
- **Document sources.** All proposals should have `source_url` pointing to SEC EDGAR or verifiable source.

---

## Code Standards

- Use relative paths from project root
- One task per script
- Print progress for long operations (batch evaluation)
- Handle errors gracefully—don't let scripts fail silently
- Cache aggressively: hash (proposal_text, prompt, model) tuple for cache keys

---

## Analysis Standards

- Start simple, add complexity after the simple version works
- Sanity check results: Are coefficients plausible? Sample sizes expected?
- Document specifications clearly for every analysis
- Save output systematically to `outputs/` for reproducibility

---

## Cost Controls (Interactive Tool)

- Rate limit: max 10 custom evaluations per session
- Daily budget: disable custom evaluations if daily spend exceeds $5 (tracked in `cache/daily_costs.json`)
- Proposal length limit: reject proposals over 5,000 characters
- Default model: claude-sonnet for cost efficiency

---

## Environment Variables

Required in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...  # Optional, for GPT-4o comparison
DAILY_BUDGET_CENTS=500
```

---

## Companion Documents

- `SOUL.md`: Research principles and values (honesty, no p-hacking, calibrated confidence)
- `INSTRUCTIONS.md`: Full technical specification with data models, prompt template, and implementation details
