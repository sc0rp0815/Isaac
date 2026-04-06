#!/data/data/com.termux/files/usr/bin/bash
# ════════════════════════════════════════════════════════
#  Isaac – Einmaliges Setup für Android/Termux
# ════════════════════════════════════════════════════════

ISAAC_DIR="$HOME/Isaac/isaac"

echo "╔══════════════════════════════════════╗"
echo "║  Isaac – Setup                       ║"
echo "╚══════════════════════════════════════╝"

echo "[1/5] Kopiere überarbeitete Dateien..."
cp config.py         "$ISAAC_DIR/config.py"
cp relay.py          "$ISAAC_DIR/relay.py"
cp isaac_core.py     "$ISAAC_DIR/isaac_core.py"
cp background_loop.py "$ISAAC_DIR/background_loop.py"
cp start_isaac.sh    "$HOME/start_isaac.sh"
chmod +x "$HOME/start_isaac.sh"
echo "     ✓"

echo "[2/5] Erstelle Modelfile..."
cat > "$HOME/Modelfile" << 'EOF'
FROM qwen2:1.5b
PARAMETER num_ctx 1024
PARAMETER num_predict 256
EOF
echo "     ✓"

echo "[3/5] Starte Ollama..."
pkill ollama 2>/dev/null
sleep 2
OLLAMA_NUM_PARALLEL=1 ollama serve > /dev/null 2>&1 &
sleep 8
echo "     ✓"

echo "[4/5] Erstelle isaac-fast Modell..."
ollama create isaac-fast -f "$HOME/Modelfile"
if [ $? -eq 0 ]; then
    echo "     isaac-fast ✓"
else
    echo "     Fehler – verwende qwen2:1.5b als Fallback"
    sed -i 's/isaac-fast/qwen2:1.5b/' "$ISAAC_DIR/config.py"
fi

echo "[5/5] Teste Ollama..."
RESPONSE=$(curl -s http://localhost:11434/api/chat \
  -d '{"model":"isaac-fast","messages":[{"role":"user","content":"Sag: OK"}],"stream":false}' \
  2>/dev/null)
if echo "$RESPONSE" | grep -q "content"; then
    echo "     Ollama antwortet ✓"
else
    echo "     Warnung: Ollama antwortet noch nicht vollständig"
fi

echo ""
echo "════════════════════════════════════════"
echo "  Setup abgeschlossen!"
echo "  Starten mit:"
echo "    ~/start_isaac.sh"
echo ""
echo "  Oder direkt:"
echo "    cd $ISAAC_DIR && python3 isaac_core.py"
echo "════════════════════════════════════════"
