# agy-pool: Antigravity Multi-Account Quota Pool & Intelligent Load Balancer Suite

[![Version](https://img.shields.io/badge/version-0.1.0--beta.5-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux%20%7C%20macOS-green.svg)](#)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](#)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(standard%20library)-brightgreen.svg)](#)
[![100% Autonomous AI](https://img.shields.io/badge/built%20by-100%25%20Autonomous%20AI-purple.svg)](https://github.com/midori01/agy-pool)

A zero-dependency multi-account quota pool and local reverse proxy for **Antigravity CLI (`agy`)** on Termux / Android Linux and standard POSIX environments.

> [!NOTE]
> ### 🤖 100% Autonomous AI Engineering
> Every single line of code, architecture, troubleshooting workflow, unit test suite, and the project repository name (`agy-pool`) was conceived, designed, implemented, and maintained 100% autonomously by AI (Antigravity).

---

## Key Features

- **Zero External Dependencies**: Pure Python 3 standard library (`urllib`, `http.server`, `sqlite3`, `fcntl`, `hashlib`, `hmac`). Runs instantly anywhere without `pip` or compilation.
- **Intelligent Quota Routing & Failover**: Routes requests by cached model quotas. Transparently fails over in-flight requests (<100ms) on HTTP 429, uncommitted transport errors, or quota exhaustion.
- **Concurrency-Safe Atomic Scheduling**: Atomic reservation of round-robin cursors before network I/O; strict no-replay semantics on ambiguous timeouts to prevent duplicate quota consumption.
- **Privacy-First Display**: Automatically masks real Google email addresses behind friendly names or anonymous aliases in logs and dashboards.
- **Session Continuity (`agy -c`)**: Context-aware workspace lookup preserves conversation threads seamlessly across different accounts.
- **Encrypted Migration & Backup**: PBKDF2 + HMAC-CTR encrypted account bundles (`export` / `import`) with pipe streaming (`ssh remote agy-pool export - | agy-pool import -`).
- **Self-Healing & Observability**: Background daemon auto-hot-reloads within 0.5s upon code updates; automated in-place log rotation capped strictly under 10 MB.

---

## Quick Start

### Installation

```bash
# Clone and install
git clone https://github.com/midori01/agy-pool.git ~/agy-pool
cd ~/agy-pool && bash install.sh
```

*(Alternatively, extract `agy-pool-termux.tar.gz` and run `bash install.sh`)*

The installer validates Python 3, sets up symlinks (`agy-pool`, `agy-raw`), configures aliases, and imports existing Antigravity credentials as Account 1.

---

## Daily Workflow

| Command | Description | Best For |
| :--- | :--- | :--- |
| **`agy`** | Launch CLI with automatic multi-account load balancing & failover | **Daily default use** |
| **`agy -c`** | Resume previous conversation thread in current directory across accounts | Continuing work |
| **`agy-raw`** | Direct connection to Google Cloud Code (bypasses proxy gateway) | Fallback / Debugging |

> All native `agy` arguments and options pass through transparently.

---

## Pool & Gateway Management

| Command | Description |
| :--- | :--- |
| `agy-pool status [-w]` | Show daemon status & quotas; `-w` / `--watch` launches live dashboard |
| `agy-pool top` | Interactive real-time TUI dashboard with live in-flight & quota meters (`watch`) |
| `agy-pool quota` | Probe and render visual quota bars and reset countdowns (`alias: list`) |
| `agy-pool config` | View or toggle pool settings (e.g. `agy-pool config show_email true/false`) |
| `agy-pool login` | Authenticate and add a new Google account via system browser |
| `agy-pool switch auto` | Designate the account with highest available quota as active |
| `agy-pool switch <ID>` | Manually switch active account (e.g. `agy-pool switch 2`) |
| `agy-pool verify [ID]` | Open Cloud Code security challenge verification flow in browser |
| `agy-pool rename <ID> [name]` | Set, update, or clear a friendly display name/alias for an account |
| `agy-pool remove <ID>` | Remove an account from the pool |
| `agy-pool start / stop` | Manage the background gateway daemon (`127.0.0.1:8899`) |
| `agy-pool log [-f]` | Inspect or follow proxy daemon log (`--rotate`, `--clear`) |
| `agy-pool forecast` | Predict quota runway, burn rates, and staggered replenishment (`--pace`, `--json`) |
| `agy-pool export [-e]` | Export accounts (plain or encrypted with `-e` / `--password`) |
| `agy-pool import <file>`| Restore/merge accounts from backup (supports `-` for stdin) |

```text
====================================================================
                 Antigravity Multi-Account Pool
====================================================================
[1] Account 1 (Work)          [* Active]   Hits: 45
    • Gemini 5-Hour: [███████░░░]  67.3%  (Resets in 3h 59m)
    • Gemini Weekly: [█████████░]  94.6%  (Resets in 6d 9h)

[2] Account 2                 [Ready]      Hits: 30
    • Gemini 5-Hour: [█████████░]  94.9%  (Resets in 3h 45m)
    • Gemini Weekly: [████████░░]  81.3%  (Resets in 3d 19h)

[3] Account 3                 [Exhausted]  Hits: 12
    • Gemini 5-Hour: [██████████] 100.0%  (Resets in 5h 0m)
    • Gemini Weekly: [░░░░░░░░░░]   0.0%  (Resets in 2d 20h)
--------------------------------------------------------------------
 [* Active] CLI Base Token    [Ready] In Rotation Pool
 [Cooldown] Rate Limited      [Exhausted] Quota Depleted
 Strategy: max_quota | Gateway Proxy: RUNNING (127.0.0.1:8899)
--------------------------------------------------------------------
⚡ Quota Runway & Endurance Forecast:
  • Health & Pace:   3/3 Active | ~18.5 gens/hr (15m window)
  • Burn/Replenish:  ~13.9%/hr burn | +60.0%/hr reload (+46.1%/hr net)
  • 5-Hour Runway:   ⚡ Sustainable (Pool replenishes faster than burn rate)
  • Weekly Runway:   ~5.4 Days remaining
====================================================================
```

---

## Uninstallation

To cleanly remove `agy-pool` and restore original environment:
```bash
cd ~/agy-pool && bash uninstall.sh
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
