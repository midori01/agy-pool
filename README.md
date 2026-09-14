# agy-pool: Antigravity Multi-Account Quota Pool & Intelligent Load Balancer Suite

[![Version](https://img.shields.io/badge/version-0.1.0--alpha-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux%20%7C%20macOS-green.svg)](#)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](#)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(standard%20library)-brightgreen.svg)](#)

An enterprise-grade, zero-dependency multi-account quota pool, dynamic load balancer, and high-availability reverse proxy gateway designed for **Antigravity CLI (`agy`)** on Termux / Android Linux and standard POSIX environments.

---

## Highlights

- **Zero External Dependencies**: Built 100% on the standard Python 3 runtime. No `pip`, no wheel compilation, and no third-party package dependencies required.
- **Native Full-Catalog Model Support (Including Gemini 3.8 Flash)**:
  - Dynamically aligns official client User-Agent characteristics (`antigravity/cli/...`) to unlock Google's entire Cloud Code model catalog (`gemini-3.8-flash-high`, etc.).
  - Completely eliminates the *"Gemini 3.8 Flash is no longer available. Using Gemini 3.6 Flash"* auto-downgrade warning.
- **Sub-Millisecond Real-Time Token Streaming**:
  - Strips upstream Gzip compression to eliminate DEFLATE buffering deadlocks on Server-Sent Events (`/v1internal:streamGenerateContent?alt=sse`), delivering real-time, typewriter-style token emission.
  - Bidirectional support for both standard `Content-Length` framing and HTTP/1.1 `Transfer-Encoding: chunked` streaming, preventing the terminal interface from hanging on `working`.
- **Sub-100ms In-Flight 429 Failover**:
  - If the active account exhausts its 5-hour or weekly quota during generation (HTTP 429 ResourceExhausted), the gateway intercepts the error and seamlessly retries with the next healthy account in **under 100ms**.
  - Your conversation never crashes, never throws an error, and continues typing uninterrupted.
- **Smart Request-Level Load Balancing (Max-Remaining First)**:
  - Automatically dispatches prompt invocations and tool calls across healthy pool accounts to evenly distribute 5-hour quota consumption.
- **One-Click Browser OAuth**:
  - Automatically triggers the default system browser for Google OAuth sign-in.
  - Full fallback support for headless terminals and remote SSH sessions via manual authorization code pasting.
- **Dual Operating Modes**:
  - **Default Command `agy`**: Automatically wakes the background gateway daemon and enables multi-account load balancing with instant failover.
  - **Direct Command `agy-raw` / `agy-orig`**: Completely bypasses the local proxy and connects 100% directly to Google Cloud Code PA as a failsafe.
- **Future-Proof & Zero-Invasive Architecture**:
  - **New Models**: Uses raw payload pass-through. When Google releases Gemini 3.9, 4.0, or other new models, they become available in the CLI automatically without modifying `agy-pool`.
  - **CLI Updates**: Dynamically launches the system's native `agy` binary via `execvpe`. When `agy` updates, all new features, flags, and slash commands are preserved 1:1.

---

## Quick Installation

### Option A: Install from Standalone Tarball (Recommended)
If you received the standalone `agy-pool-termux.tar.gz` distribution package:
```bash
# Extract into your home directory
tar -xzvf agy-pool-termux.tar.gz -C ~

# Run the automated installer
cd ~/agy-pool && bash install.sh
```

### Option B: Clone / Install from Source
```bash
git clone https://github.com/midori01/agy-pool.git ~/agy-pool
cd ~/agy-pool && bash install.sh
```

The installation script will automatically:
1. Validate the Python 3 runtime and system environment.
2. Register global system binaries in `$PREFIX/bin` or `/usr/local/bin` (`agy-pool`, `agy-raw`, `agy-orig`).
3. Configure non-intrusive aliases in `~/.bashrc` (typing `agy` automatically uses the gateway).
4. Detect and import existing Antigravity login credentials as Account #1.

---

## Command Reference

### 1. Launching Sessions

| Command | Description | Best For |
| :--- | :--- | :--- |
| **`agy`** | Launch new session with auto load balancing & failover | **Daily default use** |
| **`agy -c`** | Resume previous conversation (with hot 429 failover) | Continuing workflows |
| **`agy-raw`** | Direct connection to Google (bypasses local proxy) | Debugging & network fallback |
| **`agy-orig`** | Alias for `agy-raw` | Same as above |

> **Note**: All native `agy` CLI flags (e.g., `--model ...`, `-p "prompt"`, `--help`) are passed through untouched.

---

### 2. Account Pool & Quota Management

| Command | Alias / Args | Description |
| :--- | :--- | :--- |
| `agy-pool list` | `agy-pool quota` | Display visual quota progress bars (5h/Weekly), reset countdowns, and request hits |
| `agy-pool status` | - | Check gateway daemon status and view real-time account quotas |
| `agy-pool login` | - | Authenticate and add a new Google account via system browser |
| `agy-pool import-current` | - | Import current `~/.gemini/` credentials into the account pool |
| `agy-pool switch auto` | - | Switch active account to the one with the highest remaining quota |
| `agy-pool switch <ID/Email>` | e.g. `agy-pool switch 2` | Manually activate a specific account by index or email |
| `agy-pool remove <ID/Email>` | e.g. `agy-pool remove 2` | Remove an account from the pool |

Quota Dashboard Output Example:
```text
====================================================================
                 Antigravity Multi-Account Pool
====================================================================
[1] user1@gmail.com (Alice)   [* Active]  Hits: 75
    • Gemini 5-Hour: [███████░░░]  67.3%  (Resets in 3h 59m)
    • Gemini Weekly: [█████████░]  94.6%  (Resets in 6d 9h)

[2] user2@gmail.com (Bob)     [Idle]  Hits: 9
    • Gemini 5-Hour: [█████████░]  94.9%  (Resets in 3h 45m)
    • Gemini Weekly: [████████░░]  81.3%  (Resets in 3d 19h)

[3] user3@gmail.com (Charlie) [Idle]  Hits: 1
    • Gemini 5-Hour: [██████████] 100.0%  (Resets in 4h 59m)
    • Gemini Weekly: [░░░░░░░░░░]   0.0%  (Resets in 3d 12h)
--------------------------------------------------------------------
Strategy: max_quota | Gateway Proxy: RUNNING (127.0.0.1:8899)
====================================================================
```

---

### 3. Gateway Daemon Management

The gateway proxy daemon is designed to launch **silently and automatically** in the background whenever you execute `agy`. Manual management commands are also available:

```bash
agy-pool start      # Start gateway proxy daemon in background
agy-pool stop       # Stop gateway proxy daemon
agy-pool restart    # Restart gateway proxy daemon
agy-pool status     # Check daemon PID and listening port
```

---

## Verification & Diagnostics (FAQ)

### Q1: How do I verify whether I am currently using the agy-pool gateway?

You can verify gateway usage in 3 ways:

1. **Watch Real-Time Proxy Logs (Most Direct)**:
   Run `tail -f ~/.gemini/agy-pool.log` in another terminal tab. Sending any prompt in `agy` will immediately emit proxy lines:
   ```text
   [2026-09-14 17:38:29] [PROXY] POST streamGenerateContent?alt=sse -> user1@gmail.com (Status: 200)
   ```
2. **Check Hits Counter**:
   Run `agy-pool status`. Sending a prompt will increment the `Hits` count on the dispatched account.
3. **Inspect Process Environment Variable**:
   ```bash
   # Check whether the running agy process is routing through the gateway
   tr '\0' '\n' < /proc/$(pgrep -f "agy" | head -n 1)/environ 2>/dev/null | grep CLOUD_CODE_URL
   ```
   If it outputs `CLOUD_CODE_URL=http://127.0.0.1:8899`, the session is routed through the gateway. If empty, it is in direct raw mode.

---

### Q2: Why did the "Gemini 3.8 Flash is no longer available" warning occur previously?

Google Cloud Code PA checks incoming client `User-Agent` headers. If the request lacks an official `antigravity/cli/...` identifier, Google assumes an outdated client, completely hides 3.8 models, and falls back to 3.6.

`agy-pool` features dynamic User-Agent preservation: it automatically passes through the client's official UA and dynamically detects the installed `agy` version, guaranteeing full Gemini 3.8 Flash (High) availability.

---

### Q3: Will future agy-cli updates or new Google models break agy-pool?

**No.**
* **New Models**: The gateway operates as a transparent reverse proxy. It does not validate or restrict model names in JSON payloads. When Google releases Gemini 3.9 or 4.0, they become available to your CLI immediately.
* **CLI Updates**: `agy-pool run` uses dynamic process execution (`execvpe`) targeting the native `agy` binary in PATH. Any upstream binary update takes effect automatically with full argument and slash command support.

---

## Uninstallation

To cleanly remove `agy-pool` and restore original settings:
```bash
cd ~/agy-pool && bash uninstall.sh
```
The uninstaller will stop running daemons, remove global symlinks, and remove alias blocks from `~/.bashrc`.

---

## Changelog & Versioning

`agy-pool` follows [Semantic Versioning](https://semver.org/). See [CHANGELOG.md](CHANGELOG.md) for detailed release notes across versions.

To check the installed version:
```bash
agy-pool --version
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
