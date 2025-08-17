# Compatibility shim for tests that expect top-level r2_uploader
from r2.uploader import upload_file, get_metadata, delete_oldest_if_over_quota

__all__ = ["upload_file", "get_metadata", "delete_oldest_if_over_quota"]
