#!/bin/bash
# Isaac — Quick Setup für Termux (Android)
# Ausführung: bash ANDROID_SETUP.sh admin

set -e

MODE="${1:-user}"  # "admin" or "user" (default)
OWNER="${ISAAC_OWNER:-Steffen}"

echo "╔════════════════════════════════════════╗"
echo "║  Isaac Quick Setup for Termux (Android) ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Mode: $MODE"
echo "Owner: $OWNER"
echo ""

# Prüfe ob Termux
if [ ! -d "$PREFIX" ]; then
    echo "⚠️  Nicht in Termux erkannt. Dieses Script funktioniert in Termux."
    exit 1
fi

echo "[1/5] Installing dependencies..."
pkg install -y python3 git curl

echo "[2/5] Cloning Isaac..."
if [ ! -d "Isaac" ]; then
    git clone https://github.com/glinkasteffen075-bit/Isaac.git
else
    echo "  (Isaac directory already exists)"
fi

cd Isaac

echo "[3/5] Creating Python venv..."
python3 -m venv .venv
source .venv/bin/activate

echo "[4/5] Installing Python packages..."
pip install -q -r requirements.txt

echo "[5/5] Creating .env configuration..."
cat > .env << ENVEOF
ISAAC_OWNER=$OWNER
ACTIVE_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
ISAAC_DISABLE_VECTOR_MEMORY=1
ISAAC_PRIVILEGE_MODE=$MODE
ENVEOF

echo ""
echo "✅ Isaac setup complete!"
echo ""
echo "Next steps:"
echo "  1. Install Ollama locally OR use GROQ_API_KEY"
echo "  2. Edit .env if needed (API keys, model, etc.)"
echo "  3. Start Isaac:"
echo "     cd Isaac && source .venv/bin/activate"
echo "     python isaac_core.py"
echo ""
if [ "$MODE" = "admin" ]; then
    echo "🔓 Admin-Mode is ACTIVE — Isaac has full permissions"
else
    echo "🔒 User-Mode — Standard security gating applies"
fi
echo ""
echo "📖 More info: Read ANDROID_ADMIN_MODE.md"
