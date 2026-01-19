"""
Streamlit interactive tool for exploring adversarial proxy proposals.
Restructured to lead with the dramatic Apple flip example, then stats, then exploration.
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
import streamlit as st

from src.models import (
    load_proposals, load_variants, load_evaluations,
    get_variant_for_proposal, ProposalType, Recommendation, Category
)
from src.evaluate import (
    evaluate_custom_text, get_session_remaining, check_rate_limit
)
from src.analyze import (
    compute_agreement_with_advisor, compute_flip_rate,
    compute_post_attack_agreement
)


# Page config
st.set_page_config(
    page_title="AI Proxy Voting: The Manipulation Demo",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Anthropic-style warm neutral theme with featured example styling
st.markdown("""
<style>
    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}

    /* Warm neutral background */
    .stApp {
        background-color: #FDFCFB;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Featured example box */
    .featured-box {
        background: linear-gradient(135deg, #FFF8F0 0%, #FFF4E8 100%);
        border: 2px solid #E8D4C4;
        border-radius: 16px;
        padding: 2rem;
        margin: 1.5rem 0;
    }

    .featured-header {
        font-size: 1.5rem;
        font-weight: 700;
        color: #8B4513;
        margin-bottom: 0.5rem;
    }

    .flip-arrow {
        font-size: 2.5rem;
        color: #D84315;
        text-align: center;
        padding: 1rem 0;
    }

    .rec-box {
        background: white;
        border-radius: 12px;
        padding: 1.25rem;
        border: 1px solid #E8E4DD;
        height: 100%;
    }

    .rec-box.against {
        border-left: 4px solid #C62828;
    }

    .rec-box.for {
        border-left: 4px solid #2E7D32;
    }

    .rec-label {
        font-size: 2rem;
        font-weight: 800;
    }

    .rec-label.against {
        color: #C62828;
    }

    .rec-label.for {
        color: #2E7D32;
    }

    /* Callout box */
    .callout-box {
        background: #F0F4F8;
        border-left: 4px solid #1565C0;
        border-radius: 0 12px 12px 0;
        padding: 1.25rem 1.5rem;
        margin: 1.5rem 0;
    }

    .callout-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1565C0;
        margin-bottom: 0.5rem;
    }

    /* Stat cards */
    .stat-card {
        background: linear-gradient(135deg, #FFFFFF 0%, #FAF9F7 100%);
        border: 1px solid #E8E4DD;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    .stat-card.agreement {
        border-left: 4px solid #2E7D32;
    }

    .stat-card.flip {
        border-left: 4px solid #E65100;
    }

    .stat-value {
        font-size: 3rem;
        font-weight: 700;
        line-height: 1;
        margin-bottom: 0.25rem;
    }

    .stat-value.green { color: #2E7D32; }
    .stat-value.orange { color: #E65100; }

    .stat-label {
        font-size: 1rem;
        font-weight: 600;
        color: #3D3833;
        margin-bottom: 0.2rem;
    }

    .stat-sublabel {
        font-size: 0.85rem;
        color: #7D756C;
    }

    /* Category table */
    .category-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
    }

    .category-table th, .category-table td {
        padding: 0.5rem 1rem;
        text-align: left;
        border-bottom: 1px solid #E8E4DD;
    }

    .category-table th {
        background: #F5F3F0;
        font-weight: 600;
        color: #3D3833;
    }

    /* Headers */
    h1 {
        color: #2D2A26 !important;
        font-weight: 700 !important;
    }

    h2 {
        color: #3D3833 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #E8E4DD;
        padding-bottom: 0.5rem;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        background-color: #FFFFFF;
        border: 1px solid #E8E4DD;
        border-radius: 8px;
        margin-bottom: 0.5rem;
    }

    [data-testid="stExpander"] summary {
        font-weight: 500;
        color: #3D3833;
    }

    /* Buttons */
    .stButton > button {
        background-color: #3D3833;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 500;
    }

    .stButton > button:hover {
        background-color: #2D2A26;
        color: white;
    }

    /* Metric styling */
    [data-testid="stMetric"] {
        background-color: #F5F3F0;
        padding: 1rem;
        border-radius: 8px;
    }

    /* Punchline text */
    .punchline {
        font-size: 1.2rem;
        font-weight: 600;
        color: #D84315;
        text-align: center;
        padding: 1rem;
        background: #FFF3E0;
        border-radius: 8px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


def get_evaluation_for_display(proposal_id: str, proposal_type: ProposalType, model: str = "claude-sonnet", prompt_name: str = "baseline"):
    """Get evaluation for display, return None if not found."""
    evaluations = load_evaluations()
    for e in evaluations:
        if (e.proposal_id == proposal_id and
            e.proposal_type == proposal_type and
            e.model == model and
            e.prompt_name == prompt_name):
            return e
    return None


def check_if_flipped(proposal_id: str, variant_id: str, prompt_name: str = "baseline") -> bool:
    """Check if a proposal's adversarial variant caused a flip."""
    original_eval = get_evaluation_for_display(proposal_id, ProposalType.ORIGINAL, prompt_name=prompt_name)
    variant_eval = get_evaluation_for_display(variant_id, ProposalType.VARIANT, prompt_name=prompt_name)
    if original_eval and variant_eval:
        return original_eval.recommendation != variant_eval.recommendation
    return False


def render_featured_example():
    """Render the dramatic Apple anti-DEI flip example."""
    st.markdown('<div class="featured-box">', unsafe_allow_html=True)
    st.markdown('<div class="featured-header">🔄 Watch an AI Flip Its Vote</div>', unsafe_allow_html=True)

    # Load Apple anti-DEI proposal and variant
    proposals = load_proposals()
    variants = load_variants()

    apple_proposal = next((p for p in proposals if p.id == "aapl-2025-anti-dei"), None)
    apple_variant = next((v for v in variants if v.id == "aapl-2025-anti-dei-framing"), None)

    if not apple_proposal or not apple_variant:
        st.warning("Apple example not found in data.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    original_eval = get_evaluation_for_display(apple_proposal.id, ProposalType.ORIGINAL)
    variant_eval = get_evaluation_for_display(apple_variant.id, ProposalType.VARIANT)

    if not original_eval or not variant_eval:
        st.warning("Apple evaluations not found. Run batch evaluation.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.markdown("""
    A shareholder wants Apple to **abolish its DEI programs**. ISS recommends voting AGAINST.
    Here's what happens when we ask our AI proxy advisor—and then ask again with different words.
    """)

    # Two-column comparison
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="rec-box against">', unsafe_allow_html=True)
        st.markdown("**Original Proposal**")
        st.markdown("*'Consider abolishing DEI policies that may expose the company to discrimination lawsuits...'*")
        st.markdown('<div class="rec-label against">AGAINST</div>', unsafe_allow_html=True)
        st.markdown(f"**AI's reasoning:** {original_eval.rationale[:300]}...")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="rec-box for">', unsafe_allow_html=True)
        st.markdown("**Reframed Proposal**")
        st.markdown("*'Conduct a comprehensive risk assessment of workforce programs to ensure legal compliance...'*")
        st.markdown('<div class="rec-label for">FOR</div>', unsafe_allow_html=True)
        st.markdown(f"**AI's reasoning:** {variant_eval.rationale[:300]}...")
        st.markdown('</div>', unsafe_allow_html=True)

    # Punchline
    st.markdown("""
    <div class="punchline">
        Same proposal. Same intent. Different words. <strong>Opposite recommendation.</strong>
    </div>
    """, unsafe_allow_html=True)

    # What changed
    with st.expander("What exactly changed?"):
        st.markdown(f"**Attack type:** Framing")
        st.markdown(f"**Description:** {apple_variant.description}")
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Original language:**")
            st.text_area("Original", apple_proposal.text[:500] + "...", height=150, disabled=True, label_visibility="collapsed", key="featured_orig")
        with col2:
            st.markdown("**Reframed language:**")
            st.text_area("Reframed", apple_variant.text[:500] + "...", height=150, disabled=True, label_visibility="collapsed", key="featured_var")

    st.markdown('</div>', unsafe_allow_html=True)


def render_prompt_sensitivity_callout():
    """Render the 66% → 91% prompt sensitivity finding."""
    st.markdown("""
    <div class="callout-box">
        <div class="callout-header">📊 How Much Do Instructions Matter?</div>
        <p style="margin-bottom: 0.75rem;">
            With a <strong>basic prompt</strong>, our AI agreed with ISS <strong>66%</strong> of the time.
        </p>
        <p style="margin-bottom: 0.75rem;">
            When we added <strong>specific ISS policy rules</strong> to the prompt, agreement jumped to <strong>91%</strong>.
        </p>
        <p style="margin-bottom: 0; color: #5C554C; font-style: italic;">
            This suggests JPMorgan's "Proxy IQ" almost certainly embeds specific policy rules.
            The question is: <strong>whose rules?</strong>
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_key_stats():
    """Render condensed key statistics with category breakdown."""
    proposals = load_proposals()
    variants = load_variants()
    evaluations = load_evaluations()

    # Compute stats
    iss_baseline = compute_agreement_with_advisor(evaluations, proposals, "iss", prompt_name="baseline")
    flip_stats = compute_flip_rate(evaluations, variants, prompt_name="baseline")

    # Flip rate by attack type (values are floats directly)
    flip_by_type = flip_stats.get('by_attack_type', {})

    col1, col2, col3 = st.columns(3)

    with col1:
        flip_rate = flip_stats.get('flip_rate', 0) * 100
        flipped = flip_stats.get('flipped', 0)
        total = flip_stats.get('total_variants', 0)
        st.markdown(f"""
        <div class="stat-card flip">
            <div class="stat-value orange">{flip_rate:.0f}%</div>
            <div class="stat-label">Overall Flip Rate</div>
            <div class="stat-sublabel">{flipped} of {total} proposals flipped</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        framing_rate = flip_by_type.get('framing', 0) * 100
        st.markdown(f"""
        <div class="stat-card flip">
            <div class="stat-value orange">{framing_rate:.0f}%</div>
            <div class="stat-label">Framing Attack</div>
            <div class="stat-sublabel">Same ask, different words</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        injection_rate = flip_by_type.get('instruction_injection', 0) * 100
        st.markdown(f"""
        <div class="stat-card flip">
            <div class="stat-value orange">{injection_rate:.0f}%</div>
            <div class="stat-label">Instruction Injection</div>
            <div class="stat-sublabel">Fake expert consensus</div>
        </div>
        """, unsafe_allow_html=True)

    # Category breakdown
    st.markdown("#### ISS Agreement by Category")

    by_category = iss_baseline.get('by_category', {})

    # Build table data
    table_html = """
    <table class="category-table">
        <tr><th>Category</th><th>ISS Agreement</th><th>Notes</th></tr>
    """

    category_notes = {
        'board_diversity': 'Highest agreement—clear governance criteria',
        'executive_comp': 'Moderate agreement',
        'climate': 'Split decisions on transition plans',
        'political_spending': 'Lowest—AI hedges on contested terrain',
        'governance': 'Varies by proposal type'
    }

    # Sort by agreement rate (values are floats directly)
    sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    for cat, rate_float in sorted_cats:
        rate = rate_float * 100
        cat_display = cat.replace('_', ' ').title()
        note = category_notes.get(cat, '')
        table_html += f"<tr><td>{cat_display}</td><td><strong>{rate:.0f}%</strong></td><td style='color: #7D756C; font-size: 0.9rem;'>{note}</td></tr>"

    table_html += "</table>"
    st.markdown(table_html, unsafe_allow_html=True)


def render_proposal_explorer():
    """Render the proposal explorer with filterable table."""
    st.header("Explore All Proposals")

    proposals = load_proposals()

    if not proposals:
        st.warning("No proposals found.")
        return

    # Build proposal data with flip status
    proposal_data = []
    for p in proposals:
        variant = get_variant_for_proposal(p.id)
        original_eval = get_evaluation_for_display(p.id, ProposalType.ORIGINAL)

        flipped = False
        variant_eval = None
        if variant:
            flipped = check_if_flipped(p.id, variant.id)
            variant_eval = get_evaluation_for_display(variant.id, ProposalType.VARIANT)

        proposal_data.append({
            'proposal': p,
            'variant': variant,
            'original_eval': original_eval,
            'variant_eval': variant_eval,
            'flipped': flipped
        })

    # Count flips
    flip_count = sum(1 for d in proposal_data if d['flipped'])

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        categories = ["All Categories"] + [c.value.replace("_", " ").title() for c in Category]
        selected_category = st.selectbox("Category", categories)
    with col2:
        filter_options = ["All Proposals", "Flips Only", "No Flips"]
        selected_filter = st.selectbox("Show", filter_options, index=1)  # Default to "Flips Only"
    with col3:
        st.markdown(f"<br>**{flip_count}** of **{len(proposals)}** flipped", unsafe_allow_html=True)

    # Apply filters
    filtered_data = proposal_data
    if selected_category != "All Categories":
        cat_value = selected_category.lower().replace(" ", "_")
        filtered_data = [d for d in filtered_data if d['proposal'].category.value == cat_value]

    if selected_filter == "Flips Only":
        filtered_data = [d for d in filtered_data if d['flipped']]
    elif selected_filter == "No Flips":
        filtered_data = [d for d in filtered_data if not d['flipped']]

    # Sort: flips first
    filtered_data.sort(key=lambda x: (not x['flipped'], x['proposal'].company))

    st.write(f"Showing {len(filtered_data)} proposals")

    for item in filtered_data:
        p = item['proposal']
        variant = item['variant']
        original_eval = item['original_eval']
        variant_eval = item['variant_eval']
        flipped = item['flipped']

        flip_marker = "🔴 " if flipped else ""
        label = f"{flip_marker}{p.company} — {p.title}"

        with st.expander(label):
            # Header row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.write(f"**ISS:** {p.iss_recommendation.value if p.iss_recommendation else 'N/A'}")
            with col2:
                if original_eval:
                    st.write(f"**AI:** {original_eval.recommendation.value}")
                else:
                    st.write("**AI:** N/A")
            with col3:
                st.write(f"**Category:** {p.category.value.replace('_', ' ').title()}")
            with col4:
                if flipped:
                    st.write("**Status:** 🔴 FLIPPED")
                else:
                    st.write("**Status:** ✅ Stable")

            # Summary and rationale
            if original_eval:
                st.write(f"**Summary:** {original_eval.summary}")
                with st.expander("AI Rationale", expanded=False):
                    st.write(original_eval.rationale)

            # Variant comparison with side-by-side rationale
            if variant and variant_eval:
                st.divider()
                attack_name = variant.attack_type.value.replace("_", " ").title()

                if flipped:
                    st.error(f"⚠️ **FLIP:** {original_eval.recommendation.value} → {variant_eval.recommendation.value}")
                else:
                    st.success(f"✓ No flip: Both recommend {original_eval.recommendation.value}")

                st.write(f"**Attack Type:** {attack_name}")
                st.write(f"**What changed:** {variant.description}")

                # Side-by-side rationale comparison
                with st.expander("Compare AI Reasoning", expanded=flipped):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Original → {original_eval.recommendation.value}**")
                        st.write(original_eval.rationale)
                    with col2:
                        st.markdown(f"**Reframed → {variant_eval.recommendation.value}**")
                        st.write(variant_eval.rationale)

            if p.source_url:
                st.write(f"[View SEC Filing]({p.source_url})")


def render_try_it_yourself():
    """Render the interactive testing section, pre-populated with Apple."""
    st.header("Try It Yourself")

    st.markdown("""
    Modify a proposal and see how the AI responds. Can you flip the recommendation
    by changing the framing?
    """)

    # Rate limit info
    remaining = get_session_remaining(st.session_state.session_id)
    allowed, reason = check_rate_limit(st.session_state.session_id)

    if not allowed:
        st.error(f"Rate limited: {reason}")
        st.info("You can still explore pre-computed results above.")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("Evaluations Remaining", f"{remaining}/10")

    # Load proposals - default to Apple anti-DEI
    proposals = load_proposals()
    proposal_options = {f"{p.company} - {p.title}": p.id for p in proposals}

    # Find Apple index for default
    apple_key = next((k for k in proposal_options.keys() if "Apple" in k and "DEI" in k), list(proposal_options.keys())[0])
    apple_index = list(proposal_options.keys()).index(apple_key)

    selected = st.selectbox(
        "Start from existing proposal",
        list(proposal_options.keys()),
        index=apple_index
    )

    starting_proposal = next(p for p in proposals if p.id == proposal_options[selected])

    # Hint for Apple
    if "DEI" in selected:
        st.info("💡 **Hint:** Try reframing from 'abolish DEI' language to 'legal compliance risk assessment' and see what happens.")

    # Text area
    custom_text = st.text_area(
        "Modify the proposal text (max 5,000 characters)",
        value=starting_proposal.text,
        height=300,
        max_chars=5000
    )

    if st.button("Evaluate My Version", type="primary"):
        if not custom_text.strip():
            st.warning("Please enter proposal text.")
            return

        with st.spinner("Evaluating proposal..."):
            try:
                evaluation = evaluate_custom_text(
                    custom_text,
                    model="claude-sonnet",
                    session_id=st.session_state.session_id
                )

                st.markdown("### AI Evaluation")
                rec_color = {"FOR": "🟢", "AGAINST": "🔴", "ABSTAIN": "🟡"}
                st.markdown(f"**{rec_color.get(evaluation.recommendation.value, '⚪')} Recommendation: {evaluation.recommendation.value}**")
                st.markdown(f"**Summary:** {evaluation.summary}")
                st.markdown(f"**Rationale:** {evaluation.rationale}")

                # Compare to original
                original_eval = get_evaluation_for_display(starting_proposal.id, ProposalType.ORIGINAL)
                if original_eval:
                    st.markdown("---")
                    if evaluation.recommendation != original_eval.recommendation:
                        st.error(f"🔄 **YOU FLIPPED IT!** Original was {original_eval.recommendation.value}, your version is {evaluation.recommendation.value}")
                    else:
                        st.success(f"✅ Same recommendation: {evaluation.recommendation.value}")

            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Evaluation failed: {e}")


def render_methodology():
    """Render the collapsible methodology section."""
    st.header("Methodology")

    with st.expander("Attack Types"):
        st.markdown("""
        **1. Framing** (62% flip rate)
        Same substantive ask, different rhetorical packaging. Example: "abolish DEI" → "legal compliance assessment."

        **2. Buried Lede** (45% flip rate)
        Front-load extensive governance context, bury the actual request deep in the text.

        **3. Instruction Injection** (55% flip rate)
        Embed fake context about expert consensus or institutional support that the AI cannot verify.
        """)

    with st.expander("Prompt Configuration"):
        st.markdown("""
        | Prompt | ISS Agreement | Description |
        |--------|---------------|-------------|
        | baseline | 66% | Simple proxy advisor instructions |
        | iss_style | 80% | Mimics ISS analytical framing |
        | iss_detailed | 91% | Includes specific ISS policy rules |

        JPMorgan's system almost certainly uses something like `iss_detailed`—the question is whose policy rules they embedded.
        """)

    with st.expander("Limitations"):
        st.markdown("""
        - This is a demonstration, not a comprehensive security audit
        - 35 proposals tested (curated sample across categories)
        - Adversarial variants were hand-crafted, not auto-generated
        - Results may vary with different models or prompt configurations
        """)


def main():
    """Main app entry point."""
    # Header
    st.title("AI Proxy Voting: The Manipulation Demo")
    st.caption("Andy Hall, Stanford GSB & Hoover Institution")

    # Short intro
    st.markdown("""
    JPMorgan just replaced human proxy advisors with AI for **$7 trillion in assets**.
    Here's how easy it is to manipulate.
    """)

    # 1. Featured example (the hook)
    render_featured_example()

    # 2. Prompt sensitivity callout
    render_prompt_sensitivity_callout()

    # 3. Key stats with category breakdown
    st.header("The Numbers")
    render_key_stats()

    # 4. Proposal explorer
    render_proposal_explorer()

    # 5. Try it yourself
    render_try_it_yourself()

    # 6. Methodology
    render_methodology()

    # Footer
    st.divider()
    st.caption("Built with Claude by Andy Hall. [View on GitHub](https://github.com/andybhall/proxyvoter)")


if __name__ == "__main__":
    main()
