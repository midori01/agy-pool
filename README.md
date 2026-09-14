# agy-pool: Antigravity Multi-Account Quota Pool & Intelligent Load Balancer Suite

[![Version](https://img.shields.io/badge/version-0.1.0--alpha5-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux%20%7C%20macOS-green.svg)](#)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](#)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(standard%20library)-brightgreen.svg)](#)
[![100% Autonomous AI](https://img.shields.io/badge/built%20by-100%25%20Autonomous%20AI-purple.svg)](#)

A zero-dependency multi-account quota pool and local reverse proxy for **Antigravity CLI (`agy`)** on Termux / Android Linux and standard POSIX environments.

> [!NOTE]
> ### 🤖 100% Autonomous AI Artifact & Engineering
> **Every single line of code, system architecture, troubleshooting workflow, unit test suite, and even the project repository name (`agy-pool`) was conceived, designed, implemented, and maintained 100% autonomously by AI (Antigravity). Not a single line of code in this repository was written by a human.**

---

## Highlights

- **Zero External Dependencies**: Built 100% on the standard Python 3 runtime. No `pip`, no wheel compilation, and no third-party package dependencies required.
- **Account-Agnostic Workspace Session Continuity (`agy -c`)**:
  - Automatically queries the global conversation store (`conversation_summaries.db`) to locate the most recently active session for the current working directory, regardless of which account originally created it.
  - Maps `agy -c` to `--conversation <id>`. The lookup uses a read-only SQLite connection and may fall back to native behavior if the database stays busy or unavailable.
- **Security Validation & Account Isolation Failover**:
  - Detects Google Cloud Code account security verification challenges (`VALIDATION_REQUIRED` / 403 `Verify your account to continue`) and auth token revocations.
  - Automatically isolates restricted accounts to prevent quota deadlocks and immediately fails over generation requests to other healthy accounts (<100ms), keeping interactive sessions uninterrupted.
  - Provides `agy-pool verify <target>` to launch the dedicated Cloud Code security verification flow in the system browser.
- **Automatic Log Rotation & Zero-Maintenance Footprint**:
  - Automatically monitors gateway proxy logs and rotates them via atomic in-place `copytruncate` whenever log size reaches 5 MB (retaining 1 backup, `~/.gemini/agy-pool.log.1`), capping total disk usage under 10 MB.
  - Built-in `agy-pool log` command supports viewing recent entries (`-n`), following live streams (`-f`), manual truncation (`--clear`), and forced rotation (`--rotate`).
- **Native User-Agent Preservation**:
  - Forwards an official `antigravity/cli/...` User-Agent while leaving model availability to the native client and upstream service.
- **HTTP/1.1 Token Streaming**:
  - Requests uncompressed upstream responses and relays SSE using valid chunked framing.
  - If an upstream stream fails after response data is committed, the client receives a truncated/failed response; the request is not replayed on another account.
- **Pre-Stream Quota & Security Failover**:
  - HTTP 429, recognized quota-exhaustion HTTP 403, and account security verification challenges retry another healthy account before a response is committed to the client.
  - Network failures, permission-related 403 responses, and partially emitted streams are not silently replayed.
- **Cached-Quota Request Load Balancing**:
  - Generation requests prefer accounts using cached quota, cooldown and request-count data. The daemon refreshes quota about every 180 seconds; `list`, `quota`, and `switch auto` also request a refresh.
- **One-Click Browser OAuth**:
  - Automatically triggers the default system browser for Google OAuth sign-in.
  - Full fallback support for headless terminals and remote SSH sessions via manual authorization code pasting.
- **Dual Operating Modes**:
  - **Default Command `agy`**: Automatically wakes the background gateway daemon and enables multi-account load balancing with pre-stream quota failover.
  - **Direct Command `agy-raw` / `agy-orig`**: Completely bypasses the local proxy and connects 100% directly to Google Cloud Code PA as a failsafe.
- **Future-Proof & Zero-Invasive Architecture**:
  - **New Models**: Uses raw payload pass-through and does not maintain a local model allow-list.
  - **CLI Updates**: Dynamically launches the system's native `agy` binary via `execvpe` and passes arguments through unchanged.

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
| **`agy -c`** | Resume previous conversation for directory across accounts | Continuing workflows |
| **`agy-raw`** | Direct connection to Google (bypasses local proxy) | Debugging & network fallback |
| **`agy-orig`** | Alias for `agy-raw` | Same as above |

> **Note**: Native `agy` CLI arguments are passed through unchanged, except `-c` / `--continue`, which is resolved as described above.

---

### 2. Account Pool & Quota Management

| Command | Alias / Args | Description |
| :--- | :--- | :--- |
| `agy-pool list` | `agy-pool quota` | Refresh when possible, then display cached quota, reset countdowns, and request hits |
| `agy-pool status` | - | Check gateway status, refresh when possible, and display cached quotas |
| `agy-pool login` | - | Authenticate and add a new Google account via system browser |
| `agy-pool import-current` | - | Import current `~/.gemini/` credentials into the account pool |
| `agy-pool switch auto` | - | Switch active account to the one with the highest remaining quota |
| `agy-pool switch <ID/Email>` | e.g. `agy-pool switch 2` | Manually activate a specific account by index or email |
| `agy-pool verify [ID/Email]` | e.g. `agy-pool verify 4` | Open Google security verification URL for restricted account in browser |
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

### 4. Log Inspection & Rotation Management

Gateway traffic is logged in compact format to `~/.gemini/agy-pool.log`. Automatic rotation keeps total log usage strictly under 10 MB:

```bash
agy-pool log            # View log summary and last 20 requests
agy-pool log -n 50      # View last 50 log entries
agy-pool log -f         # Follow log in real-time (live streaming tail)
agy-pool log --rotate   # Force immediate log rotation
agy-pool log --clear    # Clear/truncate active log and remove backups
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

The upstream service uses the client `User-Agent` as part of client-version and model-availability handling. An unrecognized value can produce model availability warnings or fallback behavior.

`agy-pool` preserves an official client User-Agent and dynamically detects the installed `agy` version. Final model availability remains controlled by the native client and upstream service.

---

### Q3: Will future agy-cli updates or new Google models break agy-pool?

The proxy does not validate model names and `agy-pool run` passes CLI arguments to the native binary unchanged. Upstream API or authentication changes can still require an `agy-pool` update.

### Q4: Which account state is authoritative during a proxied session?

Each proxied HTTP request uses the account selected by the gateway and its request-level `Authorization` header. The native token file at `~/.gemini/antigravity-cli/antigravity-oauth-token` is compatibility state synchronized when a session starts or an account is explicitly switched. Automatic request failover does not rewrite that global file, so concurrent running sessions cannot churn it on every failover.

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

## Autonomous AI Engineering

This entire project—including its repository name (`agy-pool`), system architecture, implementation across all files, test suites, protocol reverse-engineering, log management, and git commit history—was engineered and executed 100% autonomously by AI (**Antigravity**). Not a single line of code was written or edited by a human.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
