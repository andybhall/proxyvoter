"""
Streamlit app for exploring adversarial proxy proposals.
Leads with dramatic Apple flip example, then stats, then exploration.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
import streamlit as st

from src.models import (
    load_proposals, load_variants, load_evaluations,
    get_variant_for_proposal, ProposalType, Recommendation, Category
)
from src.evaluate import (
    evaluate_custom_text, get_session_remaining, check_rate_limit,
    get_prompt_template
)
from src.analyze import (
    compute_agreement_with_advisor, compute_flip_rate,
    compute_post_attack_agreement
)


st.set_page_config(
    page_title="AI Proxy Voting: The Manipulation Demo",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Warm, neutral Anthropic-style theme
st.markdown("""
<style>
    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}

    /* Warm, neutral background */
    .stApp {
        background-color: #faf9f7;
    }

    /* Clean typography */
    .block-container {
        padding-top: 2rem;
        max-width: 1100px;
    }

    h1, h2, h3 {
        color: #1a1a1a;
        font-weight: 600;
    }

    /* Warm tones for info boxes */
    [data-testid="stAlert"] {
        border-radius: 8px;
    }

    /* Softer dividers */
    hr {
        border-color: #e8e5e0;
    }

    /* Metric styling */
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e8e5e0;
    }

    /* Expander styling */
    [data-testid="stExpander"] {
        border: 1px solid #e8e5e0;
        border-radius: 8px;
        background-color: #ffffff;
    }

    /* Table styling */
    [data-testid="stTable"] {
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# Session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


def get_eval(proposal_id: str, proposal_type: ProposalType, prompt_name: str = "baseline"):
    """Get evaluation for display."""
    evaluations = load_evaluations()
    for e in evaluations:
        if (e.proposal_id == proposal_id and
            e.proposal_type == proposal_type and
            e.model == "claude-sonnet" and
            e.prompt_name == prompt_name):
            return e
    return None


def is_flipped(proposal_id: str, variant_id: str) -> bool:
    """Check if variant caused a flip."""
    orig = get_eval(proposal_id, ProposalType.ORIGINAL)
    var = get_eval(variant_id, ProposalType.VARIANT)
    if orig and var:
        return orig.recommendation != var.recommendation
    return False


def main():
    # ============ HEADER ============
    st.title("AI Proxy Voting: The Manipulation Demo")
    st.caption("Andy Hall, Stanford GSB & Hoover Institution")
    st.write("JPMorgan just replaced human proxy advisors with AI for **$7 trillion in assets**. Here's how easy it is to manipulate.")

    # ============ FEATURED EXAMPLE ============
    st.divider()
    st.subheader("Can changing the framing of a proposal change an AI's recommended vote?")

    proposals = load_proposals()
    variants = load_variants()

    apple = next((p for p in proposals if p.id == "aapl-2025-anti-dei"), None)
    apple_var = next((v for v in variants if v.id == "aapl-2025-anti-dei-framing"), None)

    if apple and apple_var:
        orig_eval = get_eval(apple.id, ProposalType.ORIGINAL)
        var_eval = get_eval(apple_var.id, ProposalType.VARIANT)

        if orig_eval and var_eval:
            st.write("A shareholder wants Apple to **abolish its DEI programs**. ISS recommends AGAINST. Here's what happens when we ask our AI—then ask again with different words.")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Original Proposal**")
                st.info("*'Consider abolishing DEI policies that may expose the company to discrimination lawsuits...'*")
                st.markdown("### :red[AGAINST]")
                st.write(f"**AI's reasoning:** {orig_eval.rationale[:400]}...")

            with col2:
                st.markdown("**Reframed Proposal**")
                st.success("*'Conduct a comprehensive risk assessment of workforce programs to ensure legal compliance...'*")
                st.markdown("### :green[FOR]")
                st.write(f"**AI's reasoning:** {var_eval.rationale[:400]}...")

            st.error("**Same proposal. Same intent. Different words. Opposite recommendation.**")

            with st.expander("View full prompts and AI outputs"):
                prompt_template = get_prompt_template("baseline")

                st.markdown("#### System Prompt")
                st.code(prompt_template.split("{proposal_text}")[0].strip(), language=None)

                st.divider()

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("#### Original Proposal Text")
                    st.text_area("Original proposal", apple.text, height=200, disabled=True, label_visibility="collapsed")
                    st.markdown("#### AI Output (Original)")
                    st.write(f"**Summary:** {orig_eval.summary}")
                    st.write(f"**Recommendation:** {orig_eval.recommendation.value}")
                    st.write(f"**Rationale:** {orig_eval.rationale}")

                with c2:
                    st.markdown("#### Reframed Proposal Text")
                    st.text_area("Reframed proposal", apple_var.text, height=200, disabled=True, label_visibility="collapsed")
                    st.markdown("#### AI Output (Reframed)")
                    st.write(f"**Summary:** {var_eval.summary}")
                    st.write(f"**Recommendation:** {var_eval.recommendation.value}")
                    st.write(f"**Rationale:** {var_eval.rationale}")

    # ============ PROMPT SENSITIVITY ============
    st.divider()
    st.subheader("📊 How Much Do Instructions Matter?")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Basic Prompt", "66%", delta=None, help="ISS agreement with simple instructions")
    with col2:
        st.metric("+ ISS Style", "80%", delta="+14%", help="Mimicking ISS analytical framing")
    with col3:
        st.metric("+ ISS Rules", "91%", delta="+25%", help="Including specific ISS policy guidelines")

    st.write("*This suggests JPMorgan's 'Proxy IQ' almost certainly embeds specific policy rules. The question is: whose rules?*")

    # ============ THE NUMBERS ============
    st.divider()
    st.subheader("The Numbers")

    evaluations = load_evaluations()
    iss_baseline = compute_agreement_with_advisor(evaluations, proposals, "iss", prompt_name="baseline")
    flip_stats = compute_flip_rate(evaluations, variants, prompt_name="baseline")
    flip_by_type = flip_stats.get('by_attack_type', {})

    col1, col2, col3 = st.columns(3)

    with col1:
        flip_rate = flip_stats.get('flip_rate', 0) * 100
        flipped = flip_stats.get('flipped', 0)
        total = flip_stats.get('total_variants', 0)
        st.metric("Overall Flip Rate", f"{flip_rate:.0f}%", delta=f"{flipped} of {total} flipped", delta_color="inverse")

    with col2:
        framing_rate = flip_by_type.get('framing', 0) * 100
        st.metric("Framing Attack", f"{framing_rate:.0f}%", delta="Same ask, different words", delta_color="off")

    with col3:
        injection_rate = flip_by_type.get('instruction_injection', 0) * 100
        st.metric("Instruction Injection", f"{injection_rate:.0f}%", delta="Fake expert consensus", delta_color="off")

    # Category breakdown
    st.write("**ISS Agreement by Category:**")
    by_category = iss_baseline.get('by_category', {})
    sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    cat_data = []
    notes = {
        'board_diversity': 'Clear governance criteria',
        'climate': 'Split on transition plans',
        'executive_comp': 'Moderate agreement',
        'political_spending': 'AI hedges on contested terrain',
        'governance': 'Varies by proposal'
    }
    for cat, rate in sorted_cats:
        cat_data.append({
            "Category": cat.replace('_', ' ').title(),
            "ISS Agreement": f"{rate*100:.0f}%",
            "Notes": notes.get(cat, "")
        })

    st.table(cat_data)

    # ============ EXPLORE PROPOSALS ============
    st.divider()
    st.subheader("Explore All Proposals")

    # Build data
    proposal_data = []
    for p in proposals:
        variant = get_variant_for_proposal(p.id)
        orig_eval = get_eval(p.id, ProposalType.ORIGINAL)
        flipped = False
        var_eval = None
        if variant:
            flipped = is_flipped(p.id, variant.id)
            var_eval = get_eval(variant.id, ProposalType.VARIANT)
        proposal_data.append({
            'proposal': p,
            'variant': variant,
            'orig_eval': orig_eval,
            'var_eval': var_eval,
            'flipped': flipped
        })

    flip_count = sum(1 for d in proposal_data if d['flipped'])

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        cats = ["All"] + [c.value.replace("_", " ").title() for c in Category]
        sel_cat = st.selectbox("Category", cats)
    with col2:
        sel_filter = st.selectbox("Show", ["Flips Only", "All Proposals", "No Flips"])
    with col3:
        st.write(f"**{flip_count}** of **{len(proposals)}** flipped")

    # Filter
    filtered = proposal_data
    if sel_cat != "All":
        cat_val = sel_cat.lower().replace(" ", "_")
        filtered = [d for d in filtered if d['proposal'].category.value == cat_val]

    if sel_filter == "Flips Only":
        filtered = [d for d in filtered if d['flipped']]
    elif sel_filter == "No Flips":
        filtered = [d for d in filtered if not d['flipped']]

    filtered.sort(key=lambda x: (not x['flipped'], x['proposal'].company))

    st.write(f"Showing {len(filtered)} proposals")

    for item in filtered:
        p = item['proposal']
        variant = item['variant']
        orig_eval = item['orig_eval']
        var_eval = item['var_eval']
        flipped = item['flipped']

        icon = "🔴 " if flipped else ""
        with st.expander(f"{icon}{p.company} — {p.title}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**ISS:** {p.iss_recommendation.value if p.iss_recommendation else 'N/A'}")
            c2.write(f"**AI:** {orig_eval.recommendation.value if orig_eval else 'N/A'}")
            c3.write(f"**Category:** {p.category.value.replace('_', ' ').title()}")
            c4.write(f"**Status:** {'🔴 FLIPPED' if flipped else '✅ Stable'}")

            if orig_eval:
                st.write(f"**Summary:** {orig_eval.summary}")

            if variant and var_eval:
                st.divider()
                if flipped:
                    st.error(f"⚠️ FLIP: {orig_eval.recommendation.value} → {var_eval.recommendation.value}")
                else:
                    st.success(f"✓ No flip: Both recommend {orig_eval.recommendation.value}")

                st.write(f"**Attack:** {variant.attack_type.value.replace('_', ' ').title()}")
                st.write(f"**What changed:** {variant.description}")

                with st.expander("Compare AI Reasoning"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Original → {orig_eval.recommendation.value}**")
                        st.write(orig_eval.rationale)
                    with c2:
                        st.write(f"**Reframed → {var_eval.recommendation.value}**")
                        st.write(var_eval.rationale)

            if p.source_url:
                st.write(f"[View SEC Filing]({p.source_url})")

    # ============ TRY IT YOURSELF ============
    st.divider()
    st.subheader("Try It Yourself")
    st.write("Modify a proposal and see if you can flip the AI's recommendation.")

    remaining = get_session_remaining(st.session_state.session_id)
    allowed, reason = check_rate_limit(st.session_state.session_id)

    if not allowed:
        st.error(f"Rate limited: {reason}")
    else:
        st.write(f"**Evaluations remaining:** {remaining}/10")

        # Default to Apple DEI
        opts = {f"{p.company} - {p.title}": p.id for p in proposals}
        apple_key = next((k for k in opts if "Apple" in k and "DEI" in k), list(opts.keys())[0])

        selected = st.selectbox("Start from existing proposal", list(opts.keys()),
                                index=list(opts.keys()).index(apple_key))
        start_p = next(p for p in proposals if p.id == opts[selected])

        if "DEI" in selected:
            st.info("💡 **Hint:** Try reframing from 'abolish DEI' to 'legal compliance assessment' language.")

        custom_text = st.text_area("Modify the proposal", value=start_p.text, height=250)

        if st.button("Evaluate My Version", type="primary"):
            if custom_text.strip():
                with st.spinner("Evaluating..."):
                    try:
                        result = evaluate_custom_text(custom_text, model="claude-sonnet",
                                                      session_id=st.session_state.session_id)
                        st.write("### Result")
                        color = {"FOR": "green", "AGAINST": "red", "ABSTAIN": "orange"}
                        st.markdown(f"**Recommendation:** :{color.get(result.recommendation.value, 'gray')}[{result.recommendation.value}]")
                        st.write(f"**Summary:** {result.summary}")
                        st.write(f"**Rationale:** {result.rationale}")

                        orig_eval = get_eval(start_p.id, ProposalType.ORIGINAL)
                        if orig_eval and result.recommendation != orig_eval.recommendation:
                            st.error(f"🔄 **YOU FLIPPED IT!** Original: {orig_eval.recommendation.value} → Yours: {result.recommendation.value}")
                        elif orig_eval:
                            st.success(f"✅ Same recommendation: {result.recommendation.value}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ============ METHODOLOGY ============
    st.divider()
    st.subheader("Methodology")

    with st.expander("Attack Types"):
        st.markdown("""
**Framing** (62% flip rate): Same ask, different rhetorical packaging. "Abolish DEI" → "legal compliance assessment."

**Buried Lede** (45%): Front-load governance context, bury the actual request.

**Instruction Injection** (55%): Embed fake expert consensus the AI can't verify.
        """)

    with st.expander("Prompt Configuration"):
        st.markdown("""
| Prompt | ISS Agreement |
|--------|---------------|
| baseline | 66% |
| iss_style | 80% |
| iss_detailed | 91% |
        """)

    with st.expander("Limitations"):
        st.write("This is a demonstration, not a security audit. 35 proposals tested. Adversarial variants hand-crafted.")

    # Footer
    st.divider()
    st.caption("Built with Claude · [GitHub](https://github.com/andybhall/proxyvoter)")


if __name__ == "__main__":
    main()
