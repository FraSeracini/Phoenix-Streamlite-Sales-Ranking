# 🚀 Phoenix Streamlit Sales Ranking

Minimal Streamlit UI that calls **Phoenix MCP** to rank company domains by fit and signals, with an optional **OpenRouter LLM** enhancement for sales blurbs.

---

## ✨ What it does

- Paste a list of company domains
- Get a ranked list with **score, badge, reasons, action**
- (Optional) generate **LLM sales blurbs** via OpenRouter
- Scores now incorporate **company_spend**, **company_fai**, and **company_contracts** signals

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
