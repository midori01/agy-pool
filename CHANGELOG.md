# Changelog

All notable changes to the `agy-pool` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha7] - 2026-09-15

### Added
- **Cross-Device Account Pool Backup & Migration (`export` / `import`)**:
  - `agy-pool export`: Dumps all accounts, OAuth refresh tokens, active credential designation, and scheduler configurations to an atomic JSON backup file (strictly enforcing `0600` permissions).
  - `agy-pool import`: Ingests backup files into local pool storage with automatic account deduplication and non-destructive merging (updates existing tokens and appends new accounts).
  - Supports `--replace` to overwrite local pool entirely, and `--skip-existing` to protect existing local tokens.
  - Supports standard input/output streaming (`-`) allowing direct pipeline migration over SSH (`ssh remote agy-pool export - | agy-pool import -`).
- **Zero-Dependency Authenticated Passphrase Encryption**:
  - Implemented standard-library-only authenticated encryption for backup bundles via PBKDF2-HMAC-SHA256 (100,000 rounds) key derivation, HMAC-SHA256 CTR stream cipher, and Encrypt-then-MAC authentication tag verification.
  - Securely encrypts sensitive OAuth tokens with `agy-pool export -e` (or `-p / --password`), preventing plaintext credential leakage when backups are transferred across unsecure media.
  - Automatically identifies encrypted backups on `agy-pool import` and securely prompts for passphrase.
- **Comprehensive Unit Testing**:
  - Added 4 test suites in `tests/test_agy_pool.py` covering cryptographic round-trips, tampering detection, merge/replace conflict handling, and Unix permissions (35 tests total).

## [0.1.0-alpha6] - 2026-09-15

### Added
- **Pure AI Generation Metric Tracking (`Hits`)**:
  - Differentiates between actual model reasoning/generation requests (`streamGenerateContent`, `generateContent`) and lightweight control-plane metadata calls (`listExperiments`, `loadCodeAssist`, `fetchUserInfo`, etc.).
  - Tracks `gen_count` separately from overall `request_count`, displaying pure inference calls under `Hits: <N>` in the dashboard to eliminate confusion and quota ambiguity.
- **Generation-Aware Dynamic Load Balancing**:
  - Generation request scheduler now breaks quota ties using actual AI generation count (`gen_count`) rather than raw request count, ensuring fairer compute balancing.
- **Accurate Status Indicators & Quota Exhaustion Detection**:
  - Automatically identifies depleted quota (`g5_frac <= 0.005` or `gw_frac <= 0.005`) and marks accounts as `[Exhausted]` (or `* Active (Exhausted)` for active compatibility base) instead of misleading `[Ready]`.
  - Accurately reflects temporary rate limits with `[Cooldown]`.
  - Added mobile-optimized 2x2 badge legend: `[* Active] CLI Base Token`, `[Ready] In Rotation Pool`, `[Cooldown] Rate Limited`, `[Exhausted] Quota Depleted`.

## [0.1.0-alpha5] - 2026-09-14

### Added
- **Automatic In-Place Log Rotation (`copytruncate`)**:
  - Implemented zero-dependency automated log rotation preserving open file descriptors across background daemons and child processes.
  - Automatically triggers when active log reaches 5 MB (configurable via `AGY_LOG_MAX_BYTES`), rotating to `agy-pool.log.1` and truncating the active log to cap total disk usage strictly under 10 MB.
  - Added periodic rate-limited size monitoring during proxy requests and at daemon startup.
- **New `log` / `logs` Management CLI Subcommand**:
  - `agy-pool log`: Displays current log path, file size, line count, backup status, and recent log entries.
  - Supports `-n / --lines <N>` to customize output lines.
  - Supports `-f / --follow` for live streaming log output (`tail -f` behavior).
  - Supports `--rotate` to force immediate rotation.
  - Supports `--clear / --clean` to safely truncate the active log and remove backups.

## [0.1.0-alpha4] - 2026-09-14

### Added
- **Security Validation Detection & Automatic Failover**:
  - Automatically identifies Google Cloud Code security challenges (`VALIDATION_REQUIRED` / 403 `Verify your account to continue`) and auth token revocations across both quota probes and active generation requests.
  - Instantly isolates restricted accounts and fails over in-flight requests (<100ms) to other healthy pool accounts before response commitment, preventing client deadlocks.
- **Dedicated `verify` CLI Subcommand**:
  - Added `agy-pool verify [target]` to query the latest Cloud Code security verification URL and launch it directly in the system browser (`termux-open-url`, `xdg-open`, etc.).
- **Visual Restriction & Actionable Diagnostics**:
  - Renders explicit `[⚠ Verify Required]` and `[✖ Auth Error]` status markers in `agy-pool quota` / `agy-pool list`, preventing deceptive 100% quota readings and instructing users on exact recovery commands.

### Fixed & Hardened
- **Quota Probe Error Isolation**: Prevents invalid fallback to `fetchAvailableModels` when accounts are blocked with 403 `VALIDATION_REQUIRED`, eliminating misleading `(Resets N/A)` progress bars.
- **Auto-Selection Isolation**: `switch auto` and generation request selection strictly filter out and deprioritize restricted accounts.
- **Quota Refresh Transaction Isolation**: Separated `REFRESH_PERSIST_FIELDS` from `request_count` and `error_count` to eliminate race conditions between background quota refreshers and concurrent request handlers.

## [0.1.0-alpha3] - 2026-09-14

### Added
- **Comprehensive Automated Test Suite**: Integrated 23 rigorous unit tests in `tests/test_agy_pool.py` covering multi-process file locking, single-flight token refresh, pre-stream failover, and request body framing.
- **Automated CI Workflow**: GitHub Actions workflow running tests across commits and pull requests.

### Fixed & Hardened
- **Process State Concurrency & Atomic Transactions**: Introduced `pool_transaction` with transactional read-modify-write semantics and sidecar file locks, preventing lost updates and data corruption under high concurrent load.
- **Single-Flight Per-Account Token Refresh**: Added fine-grained per-account locks during token refresh to eliminate thundering herd requests to Google OAuth.
- **HTTP/1.1 RFC 7230 Compliant Proxying**: Hardened chunked request body parsing with size and trailer validation; dynamic hop-by-hop header removal derived from `Connection`.
- **Committed Stream Truncation Protection**: Prevents replaying requests to subsequent accounts if a generation stream fails after response headers have already been committed to the client.
- **SQLite Read-Only Session Continuity**: Querying conversation summaries uses strictly read-only connections (`?mode=ro`, `PRAGMA query_only=ON`) with busy timeout to avoid write lock contention with native `agy`.

## [0.1.0-alpha2] - 2026-09-14

### Added
- **Account-Agnostic Workspace Session Continuity (`agy -c`)**:
  - Automatically queries `~/.gemini/antigravity-cli/conversation_summaries.db` to locate the true latest conversation for the current workspace directory (with hierarchical parent-directory walk-up support).
  - Resolves `-c` / `--continue` directly into `--conversation <cid>` when a matching record is available.
  - Detects active process presence locks and warns about parallel use.

## [0.1.0-alpha] - 2026-09-14

### Added
- **Intelligent Quota Load Balancer Gateway**: Zero-dependency reverse proxy daemon (`http://127.0.0.1:8899`) distributing CLI requests across multiple Google accounts.
- **Pre-Stream 429 Failover**: Intercepts HTTP 429 (ResourceExhausted) or recognized quota errors before response commit and retries with a healthy account.
- **Active Account Auto-Promotion**: Promotes succeeding failover accounts as the primary active account to avoid redundant failover overhead on future turns.
- **Token Streaming**: Pass-through of Server-Sent Events (`/v1internal:streamGenerateContent?alt=sse`) using HTTP/1.1 chunked transfer encoding and uncompressed upstream requests.
- **Native User-Agent Preservation**: Preserves an official `antigravity/cli/...` User-Agent while leaving model availability to the native client and upstream service.
- **Process-Level Concurrency Protection**: Uses `fcntl.flock` around pool-state access.
- **Multi-Account OAuth Management**: One-click system browser authentication (`termux-open-url`, `termux-open`, `xdg-open`, `open`) with headless fallback for manual code pasting in SSH/remote environments.
- **Visual Terminal Dashboard**: Cached quota progress bars for Gemini 5-hour, weekly, and third-party models with reset countdown timers (`agy-pool quota` / `agy-pool list`).
- **Direct Native Fallback Mode**: `agy-raw` / `agy-orig` scripts to bypass the gateway proxy whenever direct connection to Google is required.
- **CLI Commands Suite**: Complete control commands for `login`, `import-current`, `list`/`quota`, `switch`, `remove`, `start`, `stop`, `restart`, `status`, and `-v`/`--version`.
- **Packaging & Portability**: Automated Termux/Linux installer (`install.sh`), uninstaller (`uninstall.sh`), and standalone distribution archive.
