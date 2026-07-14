"""Central config loader for the pipeline. Reads pipeline/secrets/.env explicitly
(not CWD-relative auto-discovery) so behavior is identical whether this runs
from an interactive shell or a Task-Scheduler-triggered process with an
unrelated working directory.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parent
ENV_PATH = PIPELINE_DIR / "secrets" / ".env"

load_dotenv(ENV_PATH)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required config value {name!r}. "
            f"Copy pipeline/.env.example to {ENV_PATH} and fill it in."
        )
    return value


def _resolve_dir(name: str, default: str) -> Path:
    raw = os.environ.get(name, default).strip() or default
    path = Path(raw)
    if not path.is_absolute():
        path = PIPELINE_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


GOOGLE_SHEETS_SPREADSHEET_ID = _require("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_TAB_NAME = os.environ.get("GOOGLE_SHEETS_TAB_NAME", "Form Responses 1").strip()
GOOGLE_SERVICE_ACCOUNT_KEY_PATH = PIPELINE_DIR / os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_KEY_PATH", "secrets/service-account.json"
)

BURP_CLI_PATH = os.environ.get("BURP_CLI_PATH", "burp-cli.exe").strip()
# Fallback invocation when the compiled binary is missing or the OS refuses to
# launch it (e.g. an Application Control / AppLocker policy blocking the exe,
# observed in some locked-down environments) -- `go run .` against the burp-cli
# source tree instead. Defaults to the repo root (pipeline/'s parent directory).
BURP_CLI_SOURCE_DIR = Path(os.environ.get("BURP_CLI_SOURCE_DIR", str(PIPELINE_DIR.parent)))
BURP_TARGET_HOST = os.environ.get("BURP_TARGET_HOST", "127.0.0.1").strip()
BURP_TARGET_PORT = os.environ.get("BURP_TARGET_PORT", "1337").strip()

JOBS_DIR = _resolve_dir("JOBS_DIR", "jobs")
LOG_DIR = _resolve_dir("LOG_DIR", "logs")

MAX_ROW_RUNTIME_MINUTES = int(os.environ.get("MAX_ROW_RUNTIME_MINUTES", "240"))
BURP_SUBPROCESS_TIMEOUT_MINUTES = int(os.environ.get("BURP_SUBPROCESS_TIMEOUT_MINUTES", "180"))

# Sheet column headers this script owns (auto-created if missing).
STATUS_COLUMN = "Status"
PROCESSED_AT_COLUMN = "Processed At"
EXPORT_DIR_COLUMN = "Export Dir"

# Intake form columns this script reads.
CLIENT_NAME_COLUMN = "Client Name"
WEBSITE_URL_COLUMN = "Website URL"
USERNAME_COLUMN = "Username"
PASSWORD_COLUMN = "Password"
