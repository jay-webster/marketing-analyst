# 🕵️‍♀️ Market Intelligence Agent

An automated AI agent that monitors competitor websites for strategic updates, product launches, and press releases.

## 🏗 Architecture

The system consists of three core components:
* **`app.py`**: A Streamlit UI for manual, ad-hoc research (Demo Mode).
* **`monitor.py`**: A Headless script designed for Cloud Run Jobs (Automation Mode).
* **`agent.py`**: The core logic utilizing Google Gemini 2.0 Flash to analyze DOM content.

## 🚀 How to Run Locally

### 1. Manual Research (UI)
```bash
streamlit run app.py