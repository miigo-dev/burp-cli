# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`burp-cli` is a Go CLI that drives Burp Suite Professional's REST API: launching scans (single URL, URL list, Nmap XML), checking status/metrics, exporting results, generating standalone HTML reports, and running scheduled scans. Requires Burp Suite Professional (Community Edition unsupported) with its REST API enabled (default `127.0.0.1:1337`).

## Build / run

```bash
go build -o burp-cli .          # build local binary
go build -o burp-cli . && ./burp-cli -V   # build then sanity-check version output
./build-all.sh                  # cross-compile all platform binaries into ./builds (reads VERSION from burp-cli.go)
```

There are no test files in this repository (`go test ./...` currently has nothing to run) and no lint config — verify changes by building and exercising the relevant CLI flags manually (e.g. against a local Burp instance, or by reading the HTTP calls for correctness since there's no mock server).

## Architecture

Single Go module (`burp-cli`), flat package layout, no internal/ or cmd/ split:

- **`burp-cli.go`** (package `main`) — entry point. Defines all CLI flags via `flaggy` in `init()`, and `main()` dispatches to module functions based on which flags are set. Version (`-V`) and the `schedule` subcommand are special-cased *before* `flaggy.Parse()` runs (see the `os.Args` check at the top of `main()`). Also owns scan-history management (`handleScanManagement`, sync-from-Burp logic) and filename/export-directory helpers — these are not in their own module.
- **`modules/configure`** — talks to Burp's REST API to check liveness (`CheckBurp`), start scans (`ScanConfig` for the simple case, `ScanConfigAdvanced` for scope/config-library/login-script/resource-pool/webhook options), poll scan status, and fetch issue descriptions/names from Burp's knowledge base. Also resolves Burp's `ConfigLibrary` directory per-OS (Windows/macOS/Linux paths differ) and assigns numeric shortcuts to built-in + ConfigLibrary + custom-file scan configurations (`-cn` flag).
- **`modules/commander`** — the read side of the Burp API: `GetMetrics`, `GetScan`/`GetScanWithFilename` (fetch scan JSON, print issue summary, write raw export to disk).
- **`modules/nmap`** — parses Nmap XML (`ParseNmap`, via `tomsteele/go-nmap`) or a plain URL list file (`ParseFile`) into a slice of scan targets.
- **`modules/reporter`** — turns a Burp JSON export into a self-contained HTML report. Contains a large inline HTML/CSS template (`reportTemplate`) with base64-embedded icons; report generation is entirely template-based, no external assets.
- **`modules/scanner`** — local scan-history tracker persisted to `~/.burp-cli/scan_history.json` (`ScanTracker`: add/update/list/clear scan records). This is what backs `-L`/`-LA` and is kept in sync with live Burp state by polling scan IDs 1–50 (see `syncScansFromBurp` in `burp-cli.go`).
- **`modules/scheduler`** — the `schedule` subcommand (create/list/delete/status/test/daemon), backed by JSON storage in `~/.burp-cli/schedules.json`. Split into `interfaces.go` (Scheduler/Storage/Executor/CronCalculator contracts), `schedule.go` (data model + validation), `storage.go` (JSON persistence), `cron.go` (next-run-time calculation for daily/weekly/monthly patterns), `cli.go` (subcommand handling), `utils.go` (path/time helpers). **Note:** the daemon only supports `--foreground` (background mode is an unimplemented stub), and `executeSchedule` is a placeholder that does not yet actually invoke a scan — it's a known gap, not a bug to "fix" silently if you're asked to touch this area without being told about it.

## Conventions to preserve

- Colored terminal output goes through `fmt.Fprintf(color.Output, ...)` using the `joanbono/color` package, with a consistent set of `cyan`/`green`/`red`/`yellow` sprint functions redeclared per-package (not shared) and a `[+] SUCCESS:`/`[-] ERROR:`/`[i] INFO:`/`[!] WARNING:` prefix convention.
- Burp API endpoints are built as `http://<target>:<port>/<apikey?>/v0.1/...` — always branch on whether an API key is set when constructing a new endpoint (existing functions all do this inline rather than via a shared URL builder).
- JSON responses from Burp are parsed with `gjson` (path-style queries), not struct unmarshaling, throughout `commander` and `configure`.
- Flags are added in `burp-cli.go`'s `init()` using `flaggy.String`/`flaggy.Bool`/`flaggy.Int` — comments there are tagged with the version that introduced them (`v1.1.x`); keep that pattern if adding new flags.
