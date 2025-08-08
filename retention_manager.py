"""Simple retention manager for Cloudflare R2 buckets.

The script checks the total size of all objects in ``R2_BUCKET`` and removes
the oldest objects until the size is below ``R2_MAX_BYTES``.
"""

from __future__ import annotations

import os

from r2_uploader import delete_oldest_if_over_quota


def main() -> None:
    limit = int(os.environ.get("R2_MAX_BYTES", "0"))
    if not limit:
        raise SystemExit("R2_MAX_BYTES environment variable is required")
    deleted = delete_oldest_if_over_quota(limit)
    print(f"Deleted {deleted} objects")


if __name__ == "__main__":
    main()

