# agy-pool: Antigravity Multi-Account Quota Pool & Intelligent Load Balancer Suite

[![Version](https://img.shields.io/badge/version-0.1.0--beta.15-blue.svg)](CHANGELOG.md)
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
| `agy-pool move <ID> <pos>` | Move account to position (`1..N`, `top`, `bottom`, `up`, `down`) (`mv`) |
| `agy-pool swap <A> <B>` | Swap positions of two accounts in the pool |
| `agy-pool sort [criteria]` | Sort pool by `quota`, `hits`, `name`, `email`, `status`, `id` (`-r` reverse) |
| `agy-pool reorder [seq]` | Custom batch reordering or display ordering guide (`order`) |
| `agy-pool remove <ID>` | Remove an account from the pool |
| `agy-pool start / stop` | Manage the background gateway daemon (`127.0.0.1:8899`) |
| `agy-pool log [-f]` | Inspect or follow proxy daemon log (`--rotate`, `--clear`) |
| `agy-pool forecast` | Predict quota runway, burn rates, and staggered replenishment (`--pace`, `--json`) |
| `agy-pool export [-e]` | Export accounts (plain or encrypted with `-e` / `--password`) |
| `agy-pool import <file>`| Restore/merge accounts from backup (supports `-` for stdin) |

### Custom User-Agent

`agy-pool` supports configurable User-Agent spoofing for both proxy traffic and quota probes:
- **`auto`** (default): Passes through the client's native `antigravity/...` User-Agent, falling back to a synthesized native CLI UA.
- **`desktop`**: Emulates the official Antigravity desktop app (`antigravity/hub/2.26.0 ...`).
- **Custom string**: Any literal custom User-Agent string (printable ASCII, max 512 characters).

```bash
# Spoof Antigravity desktop app
agy-pool config ua desktop

# Set custom User-Agent string
agy-pool config ua "MyCustomClient/1.0 (aidev_client)"

# Reset to automatic pass-through
agy-pool config ua auto

# Environment variable override (applies immediately without daemon restart)
export AGY_USER_AGENT="desktop"
```

### Per-Account Model Fallback

Not every account in a pool can use every model. When a rotated account answers a generation request with HTTP 404 (`NOT_FOUND`), the gateway logs the error snippet, checks the account's available models via `fetchAvailableModels` (cached for 30 minutes), and decides whether the failure is an entitlement gap or a transient error:
- **`auto`** (default): Falls back to `gemini-4-hydrogen`, keeping the requested tier (`low` / `medium` / `high` / `xhigh`; `MAX` maps to `xhigh`). If the account's model list lacks `xhigh` but includes `high`, `xhigh` automatically drops to `high`. `thinkingLevel` is rewritten to match and `maxOutputTokens` is capped at the fallback model's advertised limit when known (otherwise left unchanged).
- **Model id**: A family (`gemini-4-hydrogen`) keeps tier matching; a full id (`gemini-4-hydrogen-high`) pins the tier.
- **`off`**: Passes model-unavailable errors through unchanged.

Accounts that can use the requested model are never rewritten. When an account's model list confirms it lacks the requested model (or the model list is unavailable), the 404 is remembered per account and model for 60 minutes, so later requests on that account go straight to the fallback model. If the account does list the requested model, the 404 is treated as transient and retried on up to 2 other accounts before passing the 404 through to the client.

```bash
agy-pool config fallback_model auto
agy-pool config fallback_model gemini-4-hydrogen
agy-pool config fallback_model gemini-4-hydrogen-high
agy-pool config fallback_model off

# Environment variable override
export AGY_FALLBACK_MODEL="off"
```

```text
====================================================================
                 Antigravity Multi-Account Pool
====================================================================
[1] Account 1 (Work)          [* Active]   Hits: 45  •  Age: 12s
    • Gemini 5-Hour: [███████░░░]  67.3%  (Resets in 3h 59m)
    • Gemini Weekly: [█████████░]  94.6%  (Resets in 6d 9h)

[2] Account 2                 [Ready]      Hits: 30  •  Age: 15s
    • Gemini 5-Hour: [█████████░]  94.9%  (Resets in 3h 45m)
    • Gemini Weekly: [████████░░]  81.3%  (Resets in 3d 19h)

[3] Account 3                 [Exhausted]  Hits: 12  •  Age: 1m02s
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

### Free-Tier Accounts

Accounts without a paid license (free tier) return HTTP 403 (`"valid license"`) from `retrieveUserQuotaSummary`. `agy-pool` falls back to `fetchAvailableModels` and renders the per-model free quota as `Gemini Free` (about a 7-day window) with `Gemini Weekly` shown as `N/A (free tier)`. On quota refresh, any expired cached windows whose reset time has already passed are discarded.

---

## Uninstallation

To cleanly remove `agy-pool` and restore original environment:
```bash
cd ~/agy-pool && bash uninstall.sh
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
