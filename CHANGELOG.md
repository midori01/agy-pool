# Changelog

All notable changes to the `agy-pool` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta.6] - 2026-09-26

### Fixed
- **macOS & BSD Cross-Platform Compatibility**:
  - Restored standard POSIX shebangs (`#!/usr/bin/env python3` and `#!/usr/bin/env bash`) across `agy-pool` and `agy-raw`.
  - Implemented loopback-aware proxy bypass ensuring internal health endpoints (`/_agy_pool/stats`) and local test upstream handlers never route through system HTTP/HTTPS proxies (such as Clash/Surge on macOS).
  - Added case-insensitive process commandline inspection via `ps` on macOS when `/proc` is absent.
  - Fixed BSD `sed -i` syntax errors in `install.sh` and `uninstall.sh` using a portable backup-and-remove pattern.
  - Added shell profile configuration support for `~/.zprofile` and `~/.bash_profile` for macOS login shells.
  - Isolated installer lifecycle unit tests to temporary fixtures to eliminate accidental git repository working tree modifications.
  - Resolved macOS `/home` firmlink symlink resolution discrepancy in production directory detection tests.
  - 100% test pass rate (113/113 tests) verified on both Android Termux and macOS Darwin.

## [0.1.0-beta.5] - 2026-09-19

### Added
- **Interactive Real-Time TUI Dashboard (`agy-pool top`)**:
  - Implemented a zero-dependency, live-updating terminal dashboard monitor (aliases: `watch`, `monitor`).
  - Flicker-free ANSI frame rendering with cursor management, clean screen updates, and POSIX terminal state restoration.
  - **True Dynamic Responsive Layout Engine (50 ~ 120 Columns)**:
    - Continuously scales column widths to terminal width (`target = width - 1`) leaving exactly 1 character safe margin, eliminating right-side empty space while ensuring the Weekly Quota percentage (`%`) is never cut off or wrapped.
    - Upgraded `STATUS` column to width 13 for widths $\ge 60$, fully accommodating wide emoji `[⚡ Running]` (12 visible chars) without truncation.
    - Expanded `ACCOUNT` and `STATUS` separation to 2 spaces (`  `) for clean breathing room.
    - Dynamic quota progress bar tiers (8 blocks $\ge 90$ cols, 6 blocks $\ge 78$ cols, 4 blocks $\ge 60$ cols) with integer/float percentage precision and account name absorption.
  - Accurate CJK / East Asian character display width calculation (`unicodedata.east_asian_width`) ensuring flawless vertical alignment for Chinese, Japanese, and Korean account names.
  - Real-time in-flight request tracking and active running concurrency indicators per account.
  - Interactive hotkey controls: `q`/`Esc` to quit cleanly, `r` to trigger background quota refresh, `s` to live-cycle load balancing strategy (`max_quota` -> `least_used` -> `round_robin`), `+`/`-` to adjust refresh intervals, and `Space` to pause/resume.
  - Added lightweight internal gateway metrics & health endpoint (`/_agy_pool/stats`) for microsecond-latency in-memory telemetry inspection.
- **Refresh Interval Preference Persistence & Tactical Feedback**:
  - Automatically remembers and persists user-adjusted refresh intervals (`top_interval`) across sessions upon pressing `+` / `-`.
  - Added CLI configuration support via `agy-pool config top_interval <sec>`.
  - Added non-intrusive, timed visual feedback alerts in the dashboard header for interactive hotkeys (`Interval saved`, `Strategy switched`, `Syncing quotas`).
  - Added `SIGWINCH` signal handling for instantaneous zero-lag re-rendering upon terminal or phone orientation resizing.
- **Unified Command Experience (`agy-pool status -w` & In-Flight Awareness)**:
  - Integrated the live watch dashboard directly into `status` and `quota` via `-w` / `--watch` flags (e.g. `agy-pool status -w`).
  - Added live `[⚡ Running (N)]` in-flight concurrency tags to static `list` / `status` / `quota` output.
  - Added subtle CLI navigation tip on static dashboards linking to the live dashboard.

### Fixed
- **Strategy Hotkey Button Formatting**:
  - Padded column width outside parentheses (`Strategy (max_quota)  `), eliminating awkward trailing spaces inside parentheses.
- **Missing Background Quota Trigger on Manual Refresh**:
  - Implemented `trigger_background_quota_refresh()` daemon thread helper, fixing a `NameError` crash when pressing `r` in interactive dashboard mode.
- **ANSI Truncation & Color Leak Elimination**:
  - Rewrote `_fit_term_string()` to tokenize ANSI escape sequences vs printable characters, preventing color code truncation, premature clipping, and trailing color leaks.
- **Progress Bar N/A Alignment Calibration**:
  - Aligned `render_progress_bar()` `None` fraction width with valid percentage bars to eliminate table header drift.

## [0.1.0-beta.4] - 2026-09-19

### Fixed
- **Token Refresh False-Positive `auth_error` Elimination**:
  - Replaced overly aggressive uncommitted transport error classification during token refresh with dedicated `_is_token_auth_error()`.
  - Transient network timeouts (`socket.timeout`, `TimeoutError`), remote disconnects (`http.client.RemoteDisconnected`), and cellular network switches during OAuth token refresh are now properly recorded as transport errors instead of falsely flagging valid credentials as `auth_error` with a 1-hour ban.
- **Uncommitted Transport Error Matching on Exception Objects**:
  - Fixed `_is_uncommitted_transport_error()` evaluating `isinstance(target, str)` against `URLError.reason` exception objects (such as `socket.gaierror` or `OSError`), which caused string pattern matching for network failures ("name or service not known", "nodename nor servname provided") to fail silently.
- **In-Flight Concurrency Awareness & Burst Desynchronization**:
  - Implemented thread-safe in-flight request tracking (`track_in_flight_generation()`) in the proxy daemon.
  - Enhanced `max_quota` and `least_used` candidate selection strategies with active in-flight request bias, eliminating thundering herd stampedes where concurrent parallel agent calls all routed to the identical single highest account and triggered 429 rate limits.
- **Simulated Quota Runway Stale Reset Normalization**:
  - Corrected `simulate_quota_runway()` handling for accounts whose reset timestamp had elapsed prior to the current time, automatically recognizing that Google has already replenished the bucket to 100% and rolling the next reset timestamp forward into the future.
- **Resource Hygiene & Descriptor Leak Prevention**:
  - Added explicit `finally: e.close()` cleanup to `HTTPError` handlers in `query_quota()` and `do_login()`, eliminating Python 3.14 `ResourceWarning` on unclosed response buffers.
- **Automated Test Coverage Expansion**:
  - Added 5 new comprehensive test cases covering in-flight concurrency bias, token refresh error classification, past reset advancement, and exception string matching, bringing the test suite to 104 tests with 100% pass rate.

## [0.1.0-beta.3] - 2026-09-19

### Fixed
- **Telemetry Micro-Burst Damping & Multi-Window Rate Smoothing**:
  - Resolved runaway forecast collapse where temporary 15-minute coding bursts (e.g. 92 calls in 15m) were linearly extrapolated across 168 hours of continuous 24/7 non-stop usage.
  - Implemented multi-window blended moving average with micro-burst damping ($n_{60} \ge 10$ blends 50% 1h rate, 30% clamped burst rate, and 20% 4h rate) to prevent wild oscillation.
  - Expanded rolling generation telemetry ring buffer from 100 to 1000 events (`TELEMETRY_CAP = 1000`), eliminating historical truncation under intensive tool bursts.
- **Empirically Calibrated Per-Hit Quota Consumption Constants**:
  - Calibrated `DEFAULT_FRACTION_PER_HIT_WEEKLY` from 0.0015 (0.15%) to 0.00035 (~0.035% per call), matching actual Google Cloud Code weekly account limits (~2,850 calls/week) and eliminating 4.3x pessimistic distortion.
  - Calibrated `DEFAULT_FRACTION_PER_HIT_5H` from 0.0075 to 0.0050 (~0.50% per call, ~200 calls/5h window).
- **Realistic Active Coding Duty-Cycle Simulation**:
  - Differentiated burst endurance (testing whether the pool can sustain the active sprint) from multi-day weekly stamina.
  - Modeled natural human/agent coding workflows (8 hours active work/day duty cycle) for 7-day weekly projections, preventing unrealistic 24/7 continuous burn panic while retaining full continuous simulation for explicit `--pace` benchmarks.
- **Universal Multi-Environment Installer Hardening (`install.sh`)**:
  - Eliminated script aborts caused by `set -e` on transient Termux mirror warnings or interactive dpkg prompts.
  - Added autonomous non-interactive dependency resolution across Termux (`pkg` / `apt-get`), Debian/Ubuntu (`apt-get`), Arch (`pacman`), Fedora (`dnf`), Alpine (`apk`), openSUSE (`zypper`), and macOS (`brew`).
  - Added verification for `ca-certificates` and Python SSL certificate verification to prevent Google OAuth HTTPS validation failures on fresh installations.
  - Added PATH environment detection and auto-configuration across both `~/.bashrc` and `~/.zshrc`.
  - Added end-to-end post-install binary execution verification.
- **Automated Test Coverage**:
  - Expanded test suite to 99 automated tests with 100% pass rate.

## [0.1.0-beta.2] - 2026-09-19

### Added
- **Quota Runway & Endurance Forecasting Engine**:
  - Implemented event-driven chronological simulation modeling rolling consumption against staggered account reset times.
  - Telemetry tracking capturing recent inference frequency across 15m, 1h, and 4h rolling windows to compute real-time burn rates.
  - Multi-window bottleneck detection differentiating between 5-hour rolling burst limits and 7-day total weekly capacity constraints.
  - Natural capacity replenishment modeling identifying infinite sustainable endurance when aggregate staggered reset inflow exceeds demand.
  - Added `agy-pool forecast` CLI command (aliases: `runway`, `predict`) supporting custom workload simulation (`--pace <N>`) and structured output (`--json`).
  - Integrated compact runway summary block directly into `agy-pool quota`, `status`, and `list` dashboards.
  - Expanded automated test coverage from 86 to 95 tests covering all forecasting scenarios and edge cases.

## [0.1.0-beta] - 2026-09-19

### Added
- **Official Promotion to Beta Release Stage**:
  - Successfully graduated `agy-pool` from experimental alpha iterations into official beta status with hardened scheduling, failover correctness, and test sandboxing.
- **Atomic Concurrency & Round-Robin Scheduling**:
  - Atomically reserves candidate accounts and advances the round-robin cursor prior to network I/O, preventing completion-order races under concurrent CLI sessions.
  - Multi-window capacity scheduling balancing both 5-hour and weekly quotas relative to time remaining before reset.
  - Quota snapshot freshness classification (fresh, aging, stale, unknown) with asynchronous single-flight refresh and bounded exponential backoff.
- **Provably Uncommitted Transport Failover & Anti-Replay Protection**:
  - Transparently fails over for provably uncommitted network errors (DNS resolution failure, connection refusal `ECONNREFUSED`, network unreachable, and early TLS setup failures).
  - Enforces strict no-replay semantics on ambiguous transport timeouts and mid-stream disconnects, returning 504/502 to eliminate duplicate token generation and accidental double quota consumption.
- **Account Privacy Masking & Configurable Visibility**:
  - Automatically masks raw Google account email addresses in terminal status dashboards and proxy logs behind user-configured friendly names or anonymous fallback aliases (`Account 1`, `Account 2`).
  - Added multi-tier privacy visibility controls: `agy-pool config show_email <true|false>`, `AGY_SHOW_EMAIL` environment variable, and `--show-email` / `--hide-email` CLI arguments on `status` and `quota`.
- **Persistent State Isolation & Test Sandbox Safety**:
  - Added fail-closed runtime protection (`_assert_safe_write_path`) ensuring unit tests never accidentally write to or delete production `~/.gemini` or host installation paths.
  - Decoupled hardcoded paths with configurable runtime state roots via `configure_paths()` and `AGY_GEMINI_DIR`.
  - Expanded automated test coverage to 84 tests covering installer lifecycle, upgrade idempotency, and state preservation.

### Changed
- **Documentation Streamlining**:
  - Polished and streamlined `README.md` into a concise, high-signal overview highlighting essential workflows and commands.

## [0.1.0-alpha9] - 2026-09-16

### Fixed
- **Upstream Failover Resilience for SSL/Network Interruptions**:
  - Fixed a critical bug in the proxy daemon where generic unhandled network exceptions (e.g., `urllib.error.URLError`, `[SSL: UNEXPECTED_EOF_WHILE_READING]`) from Google's backend would prematurely abort the request and return an unrecoverable `502 Bad Gateway` error to the client.
  - The proxy now correctly intercepts generic socket and protocol violations, gracefully triggering an instant `continue` to seamlessly failover to the next healthy account in the pool, shielding the client from upstream HTTP/1.1 load-balancer connection drops.

## [0.1.0-alpha8] - 2026-09-15

### Added
- **Automated Gateway Daemon Hot-Reload Guard (`ensure_daemon_running`)**:
  - Automatically verifies in-memory daemon bytecode version and script file modification timestamp (`script_mtime`) stored in `PID_FILE` against active CLI code on disk.
  - Transparently and gracefully hot-restarts the gateway proxy daemon (~0.5s) upon running `agy` or `agy-pool start` whenever code updates occur, permanently preventing stale in-memory execution or frozen metrics across upgrades.
- **Daemon Metadata & Health Observability**:
  - `PID_FILE` structured JSON serialization storing PID, loaded code version, and launch timestamp with full backward-compatibility for legacy integer PID files.
  - Enhanced `agy-pool status` to display running daemon version (e.g., `PID: 5263 [v0.1.0-alpha8]`) and explicitly warn when the running process is executing outdated disk code (`⚠ Outdated Code`).
  - Added native `agy-pool version` CLI subcommand and fast dispatch.
- **Robust Daemon Cleanup on Exit**:
  - Hardened daemon process exit handlers to directly inspect PID file ownership on shutdown, ensuring reliable PID file cleanup across environments and test runners.

### Fixed
- **Pure AI Generation Metric Tracking (`Hits`)**:
  - Fixed an issue where a long-running proxy daemon instance in memory could retain pre-alpha6 bytecode, causing `gen_count` to stay frozen while quota decreased during user requests.

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
