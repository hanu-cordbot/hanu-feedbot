"""Flask application exposing a minimal API for uploading and managing
videos on Cloudflare R2.

Endpoints:
* ``POST /videos`` – accepts either a multipart file upload (``file``) or a
  JSON body with ``source_url``. The file is stored on R2 and basic metadata is
  returned.
* ``GET /videos/<key>/meta`` – returns object metadata.
* ``DELETE /videos/<key>`` – deletes an object from the bucket.
* ``GET /health`` – basic liveness probe.

The service is intentionally light‑weight and can be run with gunicorn or the
Flask development server for local testing.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Dict

import requests
from flask import Flask, jsonify, request

from .uploader import delete_object, get_metadata, upload_file


app = Flask(__name__)


@app.route("/videos", methods=["POST"])
def create_video():
    """Upload a video to R2 from a file or a source URL."""

    key = request.form.get("key") or request.args.get("key")
    if not key and "file" in request.files:
        key = request.files["file"].filename
    if not key and request.json and request.json.get("source_url"):
        key = os.path.basename(request.json["source_url"]) or "video.mp4"
    if not key:
        return jsonify({"error": "missing key"}), 400

    temp = tempfile.NamedTemporaryFile(delete=False)
    size = 0

    if "file" in request.files:
        file = request.files["file"]
        file.save(temp.name)
        size = os.path.getsize(temp.name)
    elif request.json and request.json.get("source_url"):
        r = requests.get(request.json["source_url"], stream=True)
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=8192):
            size += len(chunk)
            temp.write(chunk)
        temp.flush()
    else:
        temp.close()
        os.unlink(temp.name)
        return jsonify({"error": "no file or source_url supplied"}), 400

    temp.seek(0)
    metadata = upload_file(temp, key, size)
    temp.close()
    os.unlink(temp.name)
    return jsonify(metadata), 201


@app.route("/videos/<path:key>/meta", methods=["GET"])
def video_metadata(key: str):
    meta = get_metadata(key)
    return jsonify(meta)


@app.route("/videos/<path:key>", methods=["DELETE"])
def delete_video(key: str):
    delete_object(key)
    return "", 204


@app.route("/health", methods=["GET"])
def health() -> Dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

