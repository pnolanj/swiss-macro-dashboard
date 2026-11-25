# Switzerland Macroeconomic Monitor (CHE)

An institutional, auto-updating macroeconomic monitoring dashboard for **Switzerland (CHE)** built on **Python 3.12**, **Streamlit**, **Plotly**, and **GitHub Actions**.

**Core Analytical Question:**
> *How is the Swiss economy navigating low inflation, near-zero policy rates, and Swiss franc strength without sacrificing real output growth or labor-market stability?*

---

## Repository Architecture

```text
.
├── .github/workflows/refresh_data.yml   # Daily 12:00 UTC + manual workflow_dispatch refresh
├── .streamlit/config.toml               # Locked institutional light theme
├── data/
│   ├── series/*.csv                     # Normalized two-column ISO CSVs (date,value)
│   ├── refresh_metadata.json            # UTC/Zurich refresh timestamps & per-series audit metadata
│   └── refresh_log.csv                  # Rolling 200-run execution audit log
├── scripts/
│   └── fetch_data.py                    # Keyless, fault-tolerant FRED + SNB ingestion pipeline
├── app.py                               # Institutional 3-tab Streamlit + Plotly dashboard
├── requirements.txt                     # Minimal pinned/compatible dependencies
└── README.md
