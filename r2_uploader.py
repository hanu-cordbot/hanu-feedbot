"""Compatibility shim for legacy imports.

This module re-exports the helpers from ``r2.uploader`` so older
code and tests that expect ``r2_uploader`` keep working.
"""
from r2.uploader import *  # noqa: F401,F403
