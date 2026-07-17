#!/usr/bin/env python3
"""Backward-compatible entry point for deterministic review merging."""

from merge_review import main


if __name__ == "__main__":
    raise SystemExit(main())
