#!/data/data/com.termux/files/usr/bin/bash
echo "=== A / 8765 ==="
cat "$HOME/.ktx100-remote-a/config.json" 2>/dev/null || echo "A 설정 없음"
echo
echo "=== B / 8766 ==="
cat "$HOME/.ktx100-remote-b/config.json" 2>/dev/null || echo "B 설정 없음"
