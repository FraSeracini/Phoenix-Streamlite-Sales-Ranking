# 🚀 Phoenix Streamlit Sales Ranking

Minimal Streamlit UI that calls **Phoenix MCP** to rank company domains by fit and signals, with an optional **OpenRouter LLM** enhancement for sales blurbs.

---

## ✨ What it does

- Paste a list of company domains
- Get a ranked list with **score, badge, reasons, action**
- (Optional) generate **LLM sales blurbs** via OpenRouter
- Scores now incorporate **company_spend**, **company_fai**, and **company_contracts** signals
- Trigger badge blends **contract renewal + tech recency** with a weighted mix

---

## 🧱 Project Structure

```
.
├── app.py          # Streamlit UI
├── engine.py       # Phoenix MCP calls + scoring logic
└── requirements.txt
```

---

## ✅ Requirements

- Python 3.10+
- Dependencies from `requirements.txt`
- Optional: OpenRouter API key for LLM blurbs

---

## ⚙️ Local Setup

```bash
pip install -r requirements.txt
```

### (Optional) Enable LLM

Set the OpenRouter API key in your terminal session:

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-..."
```

---

## ▶️ Run the app

```bash
streamlit run app.py
```

Then open the URL shown in the terminal (e.g. http://localhost:8504).

---

## 🧮 Scoring Details (Current Weights)

### Fit Score (0–100)
- **Employee count** (log scale): **0–20**
- **Firmographic IT spend** (`itSpend`, log): **0–15**
- **Company spend** (`company_spend` annual, log): **0–15**
- **Tech breadth** (# installs): **0–15**
- **Tech intensity** (avg `intensity`): **0–15**
- **Cloud monthly spend** (log): **0–10**
- **Functional area coverage** (`company_fai`): **0–10**
  - +2 per area (max 10), filtered by keywords: IT, Engineering, Data, Security, Cloud, AI, Machine Learning, ML

### Trigger Badge (Hot/Warm/Cold)
The badge uses a **weighted mix**:
- **60% contract renewal proximity**
- **40% technographic recency**

**Contract score** (days to renewal):
- ≤ 30 days → 1.0
- ≤ 90 days → 0.8
- ≤ 180 days → 0.5
- ≤ 365 days → 0.2

**Recency score** (tech verification):
- ≤ 30 days → 1.0
- ≤ 120 days → 0.6
- ≤ 365 days → 0.2

**Combined thresholds**:
- **Hot** ≥ 0.75
- **Warm** ≥ 0.40
- **Cold** < 0.40

Final score = **fit score + trigger boost** (Hot +15, Warm +7, Cold +0).

---

## 🌍 Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub
2. Go to https://share.streamlit.io
3. Click **New app**
4. Select:
   - Repo: `FraSeracini/Phoenix-Streamlite-Sales-Ranking`
   - Branch: `main`
   - File: `app.py`
5. Add the secret (Advanced settings → Secrets):

```toml
OPENROUTER_API_KEY = "sk-or-v1-..."
```

6. Deploy ✅

---

## 🔐 Notes on Secrets

- End users **do not need** any API keys
- Phoenix MCP and OpenRouter keys are used **server-side only**

---

## 🧩 Optional Enhancements

- Add simple login (password env var)
- Add batch upload via CSV
- Add filters by score/badge

---

If you want any of the enhancements above, just ask! 👋
