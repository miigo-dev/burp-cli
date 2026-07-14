"""Builds a job.json matching modules/job/job.go's Spec schema exactly, from
a single Sheet row. Only the fields the intake form actually collects are
populated -- everything else (scope, login script, resource pool, ...) is
left out entirely, matching the Go struct's `omitempty` tags.
"""

import json
import time
from pathlib import Path

import config
from sheets_client import RowRecord


class MissingTargetURLError(Exception):
    """Raised when a row has no Website URL -- the one field burp-cli
    actually requires (see modules/job/job.go's Load())."""


def build_job_spec(row: RowRecord) -> dict:
    website_url = row.website_url.strip()
    if not website_url:
        raise MissingTargetURLError(f"Row {row.row_number} has no Website URL")

    spec = {"target_url": website_url}
    if row.client_name.strip():
        spec["client_name"] = row.client_name.strip()
    if row.username.strip():
        spec["username"] = row.username.strip()
    if row.password.strip():
        spec["password"] = row.password.strip()
    return spec


def write_job_file(row: RowRecord) -> Path:
    spec = build_job_spec(row)
    filename = f"job_{row.row_number}_{int(time.time())}.json"
    path = config.JOBS_DIR / filename
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path
