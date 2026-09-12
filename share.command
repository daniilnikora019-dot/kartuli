#!/bin/zsh
# Открыть приложение для телефона в той же сети (в том числе через раздачу с iPhone)
cd "$(dirname "$0")"
pkill -f "serve.py" 2>/dev/null
sleep 1
nohup python3 tools/serve.py --lan > /tmp/kartuli_server.log 2>&1 &
sleep 1.5
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
echo
echo "=============================================="
echo "  Откройте на iPhone в Safari:"
echo
echo "      http://$IP:8777/"
echo
echo "  Затем: «Поделиться» → «На экран Домой»"
echo "=============================================="
echo
echo "Сервер работает, пока включён Mac и держится раздача."
