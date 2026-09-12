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


def save_cfg(cfg):
    json.dump(cfg, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def known_chats(cfg):
    """список получателей; поддерживает и старое поле chat_id"""
    ids = [str(x) for x in (cfg.get('chat_ids') or [])]
    if cfg.get('chat_id') and str(cfg['chat_id']) not in ids:
        ids.insert(0, str(cfg['chat_id']))
    return ids


def pending_chats(cfg):
    """кто написал боту, но ещё не в рассылке"""
    res = api(cfg, 'getUpdates')
    found = {}
    for u in res.get('result', []):
        msg = u.get('message') or u.get('my_chat_member') or {}
        chat = msg.get('chat')
        if chat and chat.get('type') == 'private':
            name = ' '.join(filter(None, [chat.get('first_name'), chat.get('last_name')])) or chat.get('username') or '—'
            found[str(chat['id'])] = name
    return found


def resolve_chats(cfg):
    ids = known_chats(cfg)
    if ids:
        return ids
    found = pending_chats(cfg)
    if not found:
        sys.exit('напишите боту /start в Telegram, затем запустите скрипт ещё раз')
    cfg['chat_ids'] = list(found)
    cfg.pop('chat_id', None)
    save_cfg(cfg)
    print('получатели сохранены: ' + ', '.join(f'{n} ({i})' for i, n in found.items()))
    return cfg['chat_ids']


def add_recipients(cfg):
    """добавить в рассылку всех, кто недавно написал боту"""
    ids = known_chats(cfg)
    found = pending_chats(cfg)
    new = {i: n for i, n in found.items() if i not in ids}
    if not new:
        print('новых получателей нет.')
        print('Попросите человека открыть бота и отправить /start, затем запустите команду снова.')
        if found:
            print('сейчас в рассылке: ' + ', '.join(f'{found.get(i, "—")} ({i})' for i in ids))
        return
    cfg['chat_ids'] = ids + list(new)
    cfg.pop('chat_id', None)
    save_cfg(cfg)
    print('добавлены: ' + ', '.join(f'{n} ({i})' for i, n in new.items()))
    print(f'всего получателей: {len(cfg["chat_ids"])}')


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
    if '--add' in sys.argv:
        add_recipients(cfg)
        return
    if '--list' in sys.argv:
        found = pending_chats(cfg)
        for i in resolve_chats(cfg):
            print(f'  {found.get(i, "—")} ({i})')
        return
    chats = resolve_chats(cfg)
    w, cats = pick_word(cfg)
    cat_names = {c['id']: (c['icon'], c['name']) for c in cats}
    icon, cname = cat_names.get(w['cats'][0], ('📖', 'Общая лексика'))
    text = (f"<b>Слово дня</b>\n\n"
            f"🇬🇪 <b>{w['ka']}</b>\n"
            f"<i>{w['tr']}</i>\n\n"
            f"🇷🇺 {w['ru']}\n\n"
            f"{icon} {cname} · уровень {w['lvl']}")
    idx = json.load(open(f'{BASE}/data/audio_index.json', encoding='utf-8'))
    h = idx.get(w['ka'])
    voice = cfg.get('voice', 'f')
    path = f'{BASE}/audio/{voice}/{h}.mp3' if h else None
    audio = open(path, 'rb').read() if path and os.path.exists(path) else None
    sent, failed = [], []
    for chat_id in chats:
        try:
            api(cfg, 'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})
            if audio:
                api(cfg, 'sendVoice' if cfg.get('as_voice') else 'sendAudio',
                    {'chat_id': chat_id, 'title': w['ka'], 'performer': 'ქართული'},
                    {'voice' if cfg.get('as_voice') else 'audio': (f"{w['tr']}.mp3", audio)})
            sent.append(chat_id)
        except Exception as e:
            failed.append(f'{chat_id}: {e}')
    print(f"отправлено ({len(sent)} получателям): {w['ka']} — {w['ru']}")
    for f in failed:
        print('не доставлено —', f)


if __name__ == '__main__':
    main()
