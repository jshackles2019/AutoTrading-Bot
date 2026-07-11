# Breakout Trading Bot

This repository contains the Breakout Trading Bot project. The full guide is in guide.txt — see that file for detailed design, setup, and implementation steps.

Quick start:

1. Review guide.txt for the project overview and implementation plan.
2. Copy `.env.example` to `.env` and add your Alpaca keys.
3. Update `config/settings.yaml` with the symbols and risk settings you want.
4. Create and activate a Python virtual environment, then install dependencies:

   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt

5. Run the starter main (it currently contains a stub):

   python src/main.py

Files of interest:
- guide.txt (the full guide)
- README.md (this file)
- config/settings.yaml (example config)
- .env.example (environment variables template)
- src/ (starter module stubs)
- tests/ (basic test stubs)

Contributions and notes:
- Start with paper trading only.
- See the guide for steps on hardening, migration to IBKR, and deployment.
