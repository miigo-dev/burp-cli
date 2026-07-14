# pipeline

Glue between the Google Form/Sheet client intake and `burp-cli --job`. Reads
one pending row from the intake Sheet per run, maps its `Website URL` /
`Username` / `Password` columns straight into a `job.json`, invokes
`burp-cli`, and writes the outcome back to the Sheet.

Designed to be run on a schedule (Windows Task Scheduler), not as a
long-running process — each invocation of `poller.py` claims and processes
exactly one eligible row, then exits.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. Create a GCP service account, enable the Sheets API, download its JSON
   key to `secrets/service-account.json`, and share the intake Sheet with
   the service account's `client_email` as Editor.
4. `copy .env.example secrets\.env` and fill in the values (spreadsheet ID,
   tab name, path to the `burp-cli` binary, Burp target host/port).
5. Run once manually to verify: `python poller.py`

`burp_runner.py` prefers the compiled `burp-cli` binary (`BURP_CLI_PATH`). If
it's missing, or the OS refuses to launch it outright (e.g. an Application
Control / AppLocker policy blocking direct exe execution -- seen in some
locked-down environments), it automatically falls back to `go run .` against
`BURP_CLI_SOURCE_DIR` (needs Go on PATH). A scan that starts but exceeds
`BURP_SUBPROCESS_TIMEOUT_MINUTES` is reported as a timeout either way, not
retried under the other invocation method.

The intake form/Sheet must have `Website URL`, `Username`, and `Password`
columns (`Username`/`Password` blank is fine for an unauthenticated scan).
The Sheet will also have these tracking columns auto-created on first run if
missing: `Status`, `Processed At`, `Export Dir`.

## Scheduling (Windows Task Scheduler)

```cmd
schtasks /create /tn "BurpCLI VAPT Pipeline" ^
  /tr "\"C:\Development\burp-cli\pipeline\.venv\Scripts\python.exe\" \"C:\Development\burp-cli\pipeline\poller.py\"" ^
  /sc minute /mo 15 /ru "<username>" /rl LIMITED /f
```

Logs land in `logs/` (Task Scheduler does not capture stdout).

## Row lifecycle

`Status` column: blank -> `Processing` -> `Scanned` or `Failed: <reason>`.
A row left in `Processing` past `MAX_ROW_RUNTIME_MINUTES` is treated as an
abandoned run and reclaimed.
