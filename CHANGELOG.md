# Changelog

All notable changes to the `agy-pool` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
