"""Home page entrypoint for Streamlit multipage navigation label."""

from pathlib import Path
import runpy


# Execute the sibling dashboard file directly to avoid ambiguous module imports.
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
