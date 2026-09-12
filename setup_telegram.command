#!/bin/zsh
# Настройка ежедневного «слова дня» в Telegram
cd "$(dirname "$0")"
CFG="telegram_config.json"

echo "=============================================="
echo "  Слово дня в Telegram — настройка"
echo "=============================================="
echo
echo "Шаг 1. Создайте бота:"
echo "  • откройте Telegram, найдите @BotFather"
echo "  • отправьте ему:  /newbot"
echo "  • придумайте имя (например: Грузинский — слово дня)"
echo "  • придумайте username, обязательно оканчивается на bot"
echo "  • BotFather пришлёт токен вида 1234567890:AAH-xxxxxxxxxxxxxxxxxxxx"
echo
printf "Вставьте токен и нажмите Enter: "
read -r TOKEN
if [ -z "$TOKEN" ]; then echo "Токен не введён. Запустите скрипт ещё раз."; exit 1; fi

printf "Во сколько присылать слово дня? Час (0-23), Enter = 9: "
read -r HOUR
[ -z "$HOUR" ] && HOUR=9

python3 - "$TOKEN" "$HOUR" << 'PY'
import json, sys, os
token, hour = sys.argv[1].strip(), int(sys.argv[2])
cfg = json.load(open('telegram_config.json', encoding='utf-8'))
cfg['bot_token'] = token
cfg['hour'] = hour
json.dump(cfg, open('telegram_config.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
plist = open('tools/com.kartuli.wordofday.plist', encoding='utf-8').read()
import re
plist = re.sub(r'<key>Hour</key><integer>\d+</integer>', f'<key>Hour</key><integer>{hour}</integer>', plist)
open('tools/com.kartuli.wordofday.plist', 'w', encoding='utf-8').write(plist)
print(f'Токен сохранён, время рассылки: {hour}:00')
PY

echo
echo "Шаг 2. Откройте своего бота в Telegram и отправьте ему команду /start"
printf "Сделали? Нажмите Enter — отправлю тестовое слово дня: "
read -r _

python3 tools/telegram_word_of_day.py || { echo; echo "Не получилось. Проверьте токен и что боту отправлено /start."; exit 1; }

echo
printf "Включить ежедневную рассылку? (y/n): "
read -r YN
if [ "$YN" = "y" ]; then
  sed "s|REPLACE_HOME|$HOME|" tools/com.kartuli.wordofday.plist > ~/Library/LaunchAgents/com.kartuli.wordofday.plist
  launchctl unload ~/Library/LaunchAgents/com.kartuli.wordofday.plist 2>/dev/null
  launchctl load ~/Library/LaunchAgents/com.kartuli.wordofday.plist
  echo "Готово: слово дня будет приходить каждый день."
  echo "Отключить: launchctl unload ~/Library/LaunchAgents/com.kartuli.wordofday.plist"
fi
echo
echo "Можно закрыть это окно."
