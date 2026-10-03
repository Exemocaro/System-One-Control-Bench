import os

# Typer styles its error boxes when GITHUB_ACTIONS is set, which splits option names with
# colour codes; it reads these once, at import, so set them before any test imports it.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
os.environ["TERMINAL_WIDTH"] = "200"
