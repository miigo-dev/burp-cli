"""Google Sheets access for the intake form responses.

Uses gspread (service-account auth) instead of the raw
google-api-python-client: simple header-name based cell reads/writes are all
this needs, without the range-notation batch-update boilerplate the raw
client requires.

Row claiming (writing "Processing" before doing any work) is the pipeline's
only idempotency mechanism -- there is no local state file. The Sheet itself
is the source of truth, so multiple Task Scheduler firings never double
process the same row (barring the stale-lock recovery window below).
"""

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

STATUS_PENDING = ""  # blank cell
STATUS_PROCESSING = "Processing"
STATUS_SCANNED = "Scanned"


@dataclass
class RowRecord:
    row_number: int  # 1-indexed sheet row, including the header row
    client_name: str
    website_url: str
    username: str
    password: str


class SheetsClient:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            str(config.GOOGLE_SERVICE_ACCOUNT_KEY_PATH), scopes=SCOPES
        )
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(config.GOOGLE_SHEETS_SPREADSHEET_ID)
        self.worksheet = spreadsheet.worksheet(config.GOOGLE_SHEETS_TAB_NAME)
        self.header_index = self._ensure_tracking_columns()

    def _ensure_tracking_columns(self) -> dict:
        """Returns {header_name: 1-indexed column}. Appends any of the three
        tracking columns (Status/Processed At/Export Dir) that don't already
        exist, logging what was added."""
        headers = self.worksheet.row_values(1)
        index = {name: i + 1 for i, name in enumerate(headers)}

        for column_name in (
            config.STATUS_COLUMN,
            config.PROCESSED_AT_COLUMN,
            config.EXPORT_DIR_COLUMN,
        ):
            if column_name not in index:
                new_col = len(headers) + 1
                self.worksheet.update_cell(1, new_col, column_name)
                headers.append(column_name)
                index[column_name] = new_col
                logger.info("Added missing tracking column %r at column %d", column_name, new_col)

        return index

    def _is_stale_processing(self, processed_at_raw: str) -> bool:
        if not processed_at_raw:
            return True
        try:
            claimed_at = datetime.datetime.fromisoformat(processed_at_raw)
        except ValueError:
            logger.warning("Unparseable Processed At value %r; treating as stale", processed_at_raw)
            return True
        age = datetime.datetime.now(datetime.timezone.utc) - claimed_at
        return age.total_seconds() > config.MAX_ROW_RUNTIME_MINUTES * 60

    def find_next_eligible_row(self) -> Optional[RowRecord]:
        """Returns the first row that is blank or has a stale 'Processing'
        claim. Does not claim it -- call claim_row() separately once the
        caller is ready to actually start work."""
        rows = self.worksheet.get_all_values()
        if len(rows) < 2:
            return None

        status_col = self.header_index[config.STATUS_COLUMN] - 1
        processed_col = self.header_index[config.PROCESSED_AT_COLUMN] - 1
        client_col = self.header_index.get(config.CLIENT_NAME_COLUMN)
        url_col = self.header_index.get(config.WEBSITE_URL_COLUMN)
        username_col = self.header_index.get(config.USERNAME_COLUMN)
        password_col = self.header_index.get(config.PASSWORD_COLUMN)

        if url_col is None:
            raise RuntimeError(f"Sheet is missing required column {config.WEBSITE_URL_COLUMN!r}")

        for offset, row in enumerate(rows[1:]):
            row_number = offset + 2
            status = row[status_col] if status_col < len(row) else ""

            if status == STATUS_PENDING:
                eligible = True
            elif status == STATUS_PROCESSING:
                processed_at = row[processed_col] if processed_col < len(row) else ""
                eligible = self._is_stale_processing(processed_at)
                if eligible:
                    logger.warning("Row %d has a stale 'Processing' claim; reclaiming", row_number)
            else:
                eligible = False

            if eligible:
                return RowRecord(
                    row_number=row_number,
                    client_name=(row[client_col - 1] if client_col and client_col - 1 < len(row) else ""),
                    website_url=(row[url_col - 1] if url_col - 1 < len(row) else ""),
                    username=(row[username_col - 1] if username_col and username_col - 1 < len(row) else ""),
                    password=(row[password_col - 1] if password_col and password_col - 1 < len(row) else ""),
                )

        return None

    def claim_row(self, row_number: int) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.worksheet.update_cell(row_number, self.header_index[config.STATUS_COLUMN], STATUS_PROCESSING)
        self.worksheet.update_cell(row_number, self.header_index[config.PROCESSED_AT_COLUMN], now)

    def finalize_row(self, row_number: int, status: str, export_dir: str = "") -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.worksheet.update_cell(row_number, self.header_index[config.STATUS_COLUMN], status)
        self.worksheet.update_cell(row_number, self.header_index[config.PROCESSED_AT_COLUMN], now)
        if export_dir:
            self.worksheet.update_cell(row_number, self.header_index[config.EXPORT_DIR_COLUMN], export_dir)
