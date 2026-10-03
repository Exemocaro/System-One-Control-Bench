"""Compatibility entry point for the short report's used assets."""
from build_appendices import build_tables, build_example
from sync_results import sync_results

if __name__ == "__main__":
    build_tables()
    build_example()
    sync_results()
