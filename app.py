import asyncio
import os

import httpx
import streamlit as st

from engine import prioritize_accounts

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def llm_sales_blurb(account, api_key, model=DEFAULT_MODEL):
    prompt = f"""
Write:
1) Two crisp reasons to contact now
2) One recommended next action
3) A 2-sentence opener email

Use ONLY the facts below. Do not invent anything.
Explicitly reference the scoring inputs (fit + trigger), not just the raw reasons.
Avoid repeating the same phrasing across accounts; pick different evidence when possible.
If contract renewal is not imminent, do not lead with it.

FACTS:
Company: {account.get('company')}
Domain: {account.get('domain')}
Score: {account.get('score')}
Trigger badge: {account.get('badge')}
Reasons (raw): {account.get('reasons')}
Action (raw): {account.get('action')}

SCORING INPUTS:
- Employee count: {account.get('employeeCount')}
- Firmographic IT spend: {account.get('itSpend')}
- Company spend (annual): {account.get('companySpendAnnual')}
- Tech breadth (# installs): {account.get('techCount')}
- Tech intensity (avg): {account.get('techIntensity')}
- Cloud monthly spend: {account.get('cloudMonthlySpend')}
- Functional area coverage (FAI): {account.get('faiAreas')}
- Contract renewal (days): {account.get('daysToRenewal')}
- Industry: {account.get('industry')}
- Top technologies: {account.get('topTechnologies')}
- Cloud top services: {account.get('cloudTopServices')}
- Spend top categories: {account.get('spendTopCategories')}
"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Be concise, factual, and sales-ready."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }

    with httpx.Client(timeout=30) as client:
        r = client.post(OPENROUTER_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

st.set_page_config(page_title="Account Prioritization Agent", layout="wide")

st.title("Account Prioritization Agent")
st.caption("Paste company domains → get ranked accounts with reasons + next action.")

domains_text = st.text_area(
    "Company domains (one per line)",
    value="",
    height=120,
)

use_llm = st.checkbox("Improve output with LLM (OpenRouter)", value=False)
openrouter_key = os.getenv("OPENROUTER_API_KEY")

if use_llm and not openrouter_key:
    st.error(
        "Missing OPENROUTER_API_KEY env var. Set it in your environment (local) or in your deploy settings."
    )
    st.stop()

if st.button("Prioritize"):
    domains = [d.strip() for d in domains_text.splitlines() if d.strip()]

    with st.spinner("Running account prioritization..."):
        results = asyncio.run(prioritize_accounts(domains))

    st.success("Done")

    st.dataframe(results)

    if use_llm:
        with st.spinner("Generating sales blurbs with LLM..."):
            for r in results:
                r["llm_blurb"] = llm_sales_blurb(r, openrouter_key)

        st.subheader("LLM Sales Blurbs")
        for r in results[:10]:
            st.markdown(f"### {r['company']} ({r['domain']})")
            st.write(r.get("llm_blurb", ""))