# -*- coding: utf-8 -*-
"""Слово дня в Telegram: текст + озвучка. Запускается по расписанию через launchd."""
import json, os, random, sys, urllib.request, urllib.parse, datetime, mimetypes

BASE = os.path.expanduser('~/Library/Application Support/kartuli')
CFG = f'{BASE}/telegram_config.json'
HIST = f'{BASE}/data/wod_history.json'
API = 'https://api.telegram.org/bot{token}/{method}'


def load_cfg():
    if not os.path.exists(CFG):
        sys.exit(f'нет файла настроек {CFG}')
    c = json.load(open(CFG, encoding='utf-8'))
    if not c.get('bot_token'):
        sys.exit('в telegram_config.json не заполнен bot_token (получите его у @BotFather)')
    return c


def api(cfg, method, data=None, files=None):
    url = API.format(token=cfg['bot_token'], method=method)
    if files:                                   # multipart для отправки аудио
        boundary = '----kartuli' + str(random.randint(10**8, 10**9))
        body = b''
        for k, v in (data or {}).items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
        for k, (fname, content) in files.items():
            ctype = mimetypes.guess_type(fname)[0] or 'application/octet-stream'
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
                     f'Content-Type: {ctype}\r\n\r\n').encode() + content + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        req = urllib.request.Request(url, data=body,
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data or {}).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def resolve_chat_id(cfg):
    """если chat_id не задан — берём из последних сообщений боту (нужно написать боту /start)"""
    if cfg.get('chat_id'):
        return str(cfg['chat_id'])
    res = api(cfg, 'getUpdates')
    chats = [u['message']['chat'] for u in res.get('result', []) if 'message' in u]
    if not chats:
        sys.exit('напишите боту /start в Telegram, затем запустите скрипт ещё раз')
    cid = str(chats[-1]['id'])
    cfg['chat_id'] = cid
    json.dump(cfg, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'chat_id определён и сохранён: {cid}')
    return cid


def pick_word(cfg):
    data = json.load(open(f'{BASE}/data/words.json', encoding='utf-8'))
    words = data['words']
    hist = json.load(open(HIST, encoding='utf-8')) if os.path.exists(HIST) else {}
    sent = set(hist.get('sent', []))
    levels = cfg.get('levels') or ['A1', 'A2', 'B1']
    cats = cfg.get('categories') or []
    pool = [w for w in words if w['lvl'] in levels and (not cats or any(c in cats for c in w['cats']))]
    fresh = [w for w in pool if w['id'] not in sent]
    if not fresh:                                # словарь пройден — начинаем круг заново
        sent = set(); fresh = pool
    fresh.sort(key=lambda w: -w['f'])            # сначала самые употребимые
    top = fresh[:max(30, len(fresh) // 20)]
    w = random.Random(datetime.date.today().toordinal()).choice(top)
    sent.add(w['id'])
    hist['sent'] = list(sent)
    hist['last'] = {'date': str(datetime.date.today()), 'ka': w['ka'], 'ru': w['ru']}
    json.dump(hist, open(HIST, 'w', encoding='utf-8'), ensure_ascii=False)
    return w, data['categories']


def main():
    cfg = load_cfg()
    chat_id = resolve_chat_id(cfg)
    w, cats = pick_word(cfg)
    cat_names = {c['id']: (c['icon'], c['name']) for c in cats}
    icon, cname = cat_names.get(w['cats'][0], ('📖', 'Общая лексика'))
    text = (f"<b>Слово дня</b>\n\n"
            f"🇬🇪 <b>{w['ka']}</b>\n"
            f"<i>{w['tr']}</i>\n\n"
            f"🇷🇺 {w['ru']}\n\n"
            f"{icon} {cname} · уровень {w['lvl']}")
    api(cfg, 'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})
    # озвучка
    idx = json.load(open(f'{BASE}/data/audio_index.json', encoding='utf-8'))
    h = idx.get(w['ka'])
    voice = cfg.get('voice', 'f')
    path = f'{BASE}/audio/{voice}/{h}.mp3' if h else None
    if path and os.path.exists(path):
        api(cfg, 'sendVoice' if cfg.get('as_voice') else 'sendAudio',
            {'chat_id': chat_id, 'title': w['ka'], 'performer': 'ქართული'},
            {'voice' if cfg.get('as_voice') else 'audio': (f"{w['tr']}.mp3", open(path, 'rb').read())})
    print(f"отправлено: {w['ka']} — {w['ru']}")


if __name__ == '__main__':
    main()
