# Changelog

All notable changes to the `agy-pool` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha] - 2026-09-14

### Added
- **Intelligent Quota Load Balancer Gateway**: Zero-dependency reverse proxy daemon (`http://127.0.0.1:8899`) distributing CLI requests across multiple Google accounts.
- **Sub-100ms In-Flight 429 Failover**: Seamlessly intercepts HTTP 429 (ResourceExhausted) or quota limit errors during model generation and retries with healthy accounts under 100ms without crashing sessions.
- **Active Account Auto-Promotion**: Promotes succeeding failover accounts as the primary active account to avoid redundant failover overhead on future turns.
- **Real-Time Token Streaming**: Pass-through of Server-Sent Events (`/v1internal:streamGenerateContent?alt=sse`) and HTTP/1.1 chunked transfer encoding, with upstream Gzip stripping to eliminate typewriter token delays.
- **Dynamic Full-Catalog Model Support**: Dynamically aligns official client User-Agent strings (`antigravity/cli/...`) to unlock Google's entire Cloud Code model catalog (e.g. `gemini-3.8-flash-high`) without downgrade warnings.
- **Process-Level Concurrency Protection**: Integrated `fcntl.flock` file locking to guarantee ACID atomic JSON configuration updates and prevent race conditions between background daemon and foreground CLI.
- **Multi-Account OAuth Management**: One-click system browser authentication (`termux-open-url`, `termux-open`, `xdg-open`, `open`) with headless fallback for manual code pasting in SSH/remote environments.
- **Visual Terminal Dashboard**: Real-time quota progress bars for Gemini 5-hour, weekly, and third-party models with reset countdown timers (`agy-pool quota` / `agy-pool list`).
- **Direct Native Fallback Mode**: `agy-raw` / `agy-orig` scripts to bypass the gateway proxy whenever direct connection to Google is required.
- **CLI Commands Suite**: Complete control commands for `login`, `import-current`, `list`/`quota`, `switch`, `remove`, `start`, `stop`, `restart`, `status`, and `-v`/`--version`.
- **Packaging & Portability**: Automated Termux/Linux installer (`install.sh`), uninstaller (`uninstall.sh`), and standalone distribution archive.
