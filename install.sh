#!/usr/bin/env bash
# agy-pool installer for Termux / Android Linux and standard POSIX environments

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_SRC="$SCRIPT_DIR/bin/agy-pool"
RAW_SRC="$SCRIPT_DIR/bin/agy-raw"

echo -e "\033[1;36m===================================================="
echo -e "       Installing agy-pool (Antigravity Pool)       "
echo -e "====================================================\033[0m"

# 1. Environment & Target directory detection
if [ -n "${PREFIX:-}" ] && [ -d "$PREFIX/bin" ]; then
    TARGET_DIR="$PREFIX/bin"
    IS_TERMUX=1
    echo -e "\033[32m[✓] Detected Termux environment: $TARGET_DIR\033[0m"
elif [ -w "/usr/local/bin" ]; then
    TARGET_DIR="/usr/local/bin"
    IS_TERMUX=0
    echo -e "\033[32m[✓] System environment detected: $TARGET_DIR\033[0m"
elif mkdir -p "$HOME/.local/bin" 2>/dev/null && [ -w "$HOME/.local/bin" ]; then
    TARGET_DIR="$HOME/.local/bin"
    IS_TERMUX=0
    echo -e "\033[33m[!] /usr/local/bin not writable, installing to user directory: $TARGET_DIR\033[0m"
else
    TARGET_DIR="/usr/local/bin"
    IS_TERMUX=0
fi

# 2. Dependency resolution across diverse environments
install_deps() {
    echo -e "\033[36m[*] Checking dependencies (python3, ca-certificates, curl)...\033[0m"

    local need_python=0
    local need_certs=0
    local need_curl=0

    if ! command -v python3 >/dev/null 2>&1; then
        need_python=1
    fi

    if ! command -v curl >/dev/null 2>&1; then
        need_curl=1
    fi

    # Check SSL certificate validation in python
    if [ "$need_python" -eq 0 ]; then
        if ! python3 -c "import urllib.request, ssl; ssl.create_default_context().load_default_certs()" >/dev/null 2>&1; then
            need_certs=1
        fi
    else
        need_certs=1
    fi

    if [ "$need_python" -eq 0 ] && [ "$need_certs" -eq 0 ] && [ "$need_curl" -eq 0 ]; then
        echo -e "\033[32m[✓] All dependencies are already satisfied.\033[0m"
        return 0
    fi

    echo -e "\033[33m[!] Installing missing dependencies (python: $need_python, certs: $need_certs, curl: $need_curl)...\033[0m"

    if [ "$IS_TERMUX" -eq 1 ]; then
        echo -e "\033[36m[*] Termux detected. Installing python, ca-certificates, termux-tools, curl...\033[0m"
        export DEBIAN_FRONTEND=noninteractive
        # Try direct install first without full upgrade to avoid broken mirror prompts
        pkg install -y -o Dpkg::Options::="--force-confnew" python ca-certificates termux-tools curl 2>/dev/null || {
            echo -e "\033[33m[!] Direct install needed repo refresh; updating package indexes...\033[0m"
            pkg update -y -o Dpkg::Options::="--force-confnew" 2>/dev/null || true
            pkg install -y -o Dpkg::Options::="--force-confnew" python ca-certificates termux-tools curl 2>/dev/null || {
                # Fallback to apt-get inside Termux
                apt-get update -y 2>/dev/null || true
                apt-get install -y --no-install-recommends -o Dpkg::Options::="--force-confnew" python ca-certificates termux-tools curl || true
            }
        }
    elif command -v apt-get >/dev/null 2>&1; then
        echo -e "\033[36m[*] Debian/Ubuntu/WSL detected. Installing python3, ca-certificates, curl...\033[0m"
        local SUDO=""
        if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        export DEBIAN_FRONTEND=noninteractive
        $SUDO apt-get update -y 2>/dev/null || true
        $SUDO apt-get install -y python3 python3-minimal ca-certificates curl || true
    elif command -v pacman >/dev/null 2>&1; then
        echo -e "\033[36m[*] Arch Linux detected. Installing python, ca-certificates, curl...\033[0m"
        local SUDO=""
        if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        $SUDO pacman -Sy --noconfirm python ca-certificates curl || true
    elif command -v dnf >/dev/null 2>&1; then
        echo -e "\033[36m[*] Fedora/RHEL detected. Installing python3, ca-certificates, curl...\033[0m"
        local SUDO=""
        if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        $SUDO dnf install -y python3 ca-certificates curl || true
    elif command -v apk >/dev/null 2>&1; then
        echo -e "\033[36m[*] Alpine Linux detected. Installing python3, ca-certificates, bash, curl...\033[0m"
        local SUDO=""
        if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        $SUDO apk add --no-cache python3 ca-certificates bash curl || true
    elif command -v zypper >/dev/null 2>&1; then
        echo -e "\033[36m[*] openSUSE detected. Installing python3, ca-certificates, curl...\033[0m"
        local SUDO=""
        if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        $SUDO zypper install -y python3 ca-certificates curl || true
    elif command -v brew >/dev/null 2>&1; then
        echo -e "\033[36m[*] macOS Homebrew detected. Installing python3, curl...\033[0m"
        brew install python3 curl || true
    else
        echo -e "\033[31m[Error] No supported package manager found. Please install python3 and ca-certificates manually.\033[0m"
        exit 1
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "\033[31m[Error] python3 installation failed or not found in PATH.\033[0m"
        exit 1
    fi
}

install_deps

# 3. Shebang adjustment and executable permissions
chmod +x "$BIN_SRC" "$RAW_SRC"
if [ "$IS_TERMUX" -eq 1 ]; then
    if command -v termux-fix-shebang >/dev/null 2>&1; then
        termux-fix-shebang "$BIN_SRC" "$RAW_SRC" 2>/dev/null || true
    else
        sed -i -E "1 s@^#\!(/usr)?/bin/(env\s+)?(.*)@#\!$PREFIX/bin/\3@" "$BIN_SRC" "$RAW_SRC" 2>/dev/null || true
    fi
else
    # Standard POSIX: ensure standard shebang
    sed -i "1s|^#!.*python.*|#!/usr/bin/env python3|" "$BIN_SRC" 2>/dev/null || true
    sed -i "1s|^#!.*bash.*|#!/usr/bin/env bash|" "$RAW_SRC" 2>/dev/null || true
fi

# 4. Create symlinks in bin directory
ln -sf "$BIN_SRC" "$TARGET_DIR/agy-pool"
ln -sf "$RAW_SRC" "$TARGET_DIR/agy-raw"
ln -sf "$RAW_SRC" "$TARGET_DIR/agy-orig"
echo -e "\033[32m[✓] Installed executables: agy-pool, agy-raw, agy-orig in $TARGET_DIR\033[0m"

# 5. Configure Shell Aliases (~/.bashrc and ~/.zshrc)
MARKER="# >>> agy-pool integration >>>"
ALIAS_BLOCK="
# >>> agy-pool integration >>>
alias agy='agy-pool run'
alias agy-raw='agy-raw'
alias agy-orig='agy-raw'
# <<< agy-pool integration <<<"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] || [ "$(basename "$rc")" = ".bashrc" ]; then
        touch "$rc" 2>/dev/null || true
        if ! grep -Fq "$MARKER" "$rc" 2>/dev/null; then
            echo "$ALIAS_BLOCK" >> "$rc" 2>/dev/null || true
            echo -e "\033[32m[✓] Added agy aliases to $rc\033[0m"
        fi
        if ! echo ":${PATH:-}:" | grep -Fq ":$TARGET_DIR:"; then
            PATH_LINE="export PATH=\"$TARGET_DIR:\$PATH\""
            if ! grep -Fq "$PATH_LINE" "$rc" 2>/dev/null; then
                echo "$PATH_LINE" >> "$rc" 2>/dev/null || true
                echo -e "\033[32m[✓] Added $TARGET_DIR to PATH in $rc\033[0m"
            fi
        fi
    fi
done

# 6. Verify installation
echo -e "\033[36m[*] Verifying agy-pool execution...\033[0m"
if "$TARGET_DIR/agy-pool" version >/dev/null 2>&1; then
    VER_STR="$("$TARGET_DIR/agy-pool" version 2>/dev/null || echo "ok")"
    echo -e "\033[32m[✓] Verification successful: $VER_STR\033[0m"
else
    echo -e "\033[33m[!] Direct execution check returned warning, verifying syntax with python3...\033[0m"
    python3 "$BIN_SRC" version || true
fi

# 7. Auto-import current antigravity credentials if present
echo -e "\033[36m[*] Checking for existing Antigravity login token...\033[0m"
"$TARGET_DIR/agy-pool" import-current >/dev/null 2>&1 || true

echo -e "\n\033[1;32m===================================================="
echo -e "             Installation Successful!               "
echo -e "====================================================\033[0m"
echo -e "You can now use:"
echo -e "  \033[1magy\033[0m            - Runs Antigravity with auto load balancer & failover"
echo -e "  \033[1magy -c\033[0m         - Resumes session with auto load balancer"
echo -e "  \033[1magy-raw\033[0m        - Directly runs original native agy (NO proxy)"
echo -e "  \033[1magy-orig\033[0m       - Alias for agy-raw (original direct mode)"
echo -e "  \033[1magy-pool quota\033[0m - Real-time quota dashboard for all accounts"
echo -e "  \033[1magy-pool login\033[0m - Add new Google accounts to pool"
echo -e ""
