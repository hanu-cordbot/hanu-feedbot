"""Cloudflare R2 helpers.

This package provides small helpers for uploading videos to Cloudflare R2
and managing retention.  It exposes convenience functions from
:mod:`r2.uploader`.
"""

from .uploader import (
    upload_file,
    get_metadata,
    delete_object,
    delete_oldest_if_over_quota,
    upload_path_and_prune,
)

__all__ = [
    "upload_file",
    "get_metadata",
    "delete_object",
    "delete_oldest_if_over_quota",
    "upload_path_and_prune",
]
