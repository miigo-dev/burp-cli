"""Entrypoint. Claims and processes exactly one eligible Sheet row, then
exits -- run this on a schedule (Windows Task Scheduler); see README.md.

All paths are resolved relative to this file's own directory (via
config.PIPELINE_DIR), not the current working directory, since Task
Scheduler does not set one by default.
"""

import logging
import sys

import burp_runner
import config
from job_builder import MissingTargetURLError, write_job_file
from sheets_client import STATUS_SCANNED, SheetsClient


def _setup_logging() -> None:
    log_file = config.LOG_DIR / "poller.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    _setup_logging()
    logger = logging.getLogger("poller")

    sheets = SheetsClient()
    row = sheets.find_next_eligible_row()
    if row is None:
        logger.info("No eligible rows; nothing to do")
        return 0

    logger.info("Claiming row %d (%s)", row.row_number, row.website_url)
    sheets.claim_row(row.row_number)

    try:
        job_path = write_job_file(row)
    except MissingTargetURLError as exc:
        logger.error(str(exc))
        sheets.finalize_row(row.row_number, "Failed: missing Website URL")
        return 1

    logger.info("Wrote job spec to %s", job_path)
    result = burp_runner.run_job(job_path, row.row_number)

    if result.success:
        logger.info("Row %d scanned successfully; export dir: %s", row.row_number, result.export_dir)
        sheets.finalize_row(row.row_number, STATUS_SCANNED, export_dir=result.export_dir)
        return 0

    reason = f"Failed: burp-cli exited {result.exit_code}"
    logger.error("Row %d failed: %s (log: %s)", row.row_number, reason, result.log_path)
    sheets.finalize_row(row.row_number, reason, export_dir=result.export_dir)
    return 1


if __name__ == "__main__":
    sys.exit(main())
