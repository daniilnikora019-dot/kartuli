# -*- coding: utf-8 -*-
"""Рассылка в Telegram, запускается по расписанию через launchd.

  без флагов   слово дня: текст, транскрипция, перевод и озвучка
  --quiz       тест одного слова викториной Telegram: четыре варианта,
               направление чередуется по дням (грузинское→русское и обратно)
  --dry-run    показать, что было бы отправлено, и ничего не слать
  --add        добавить в рассылку всех, кто написал боту
  --list       показать получателей
"""
import json, os, random, sys, urllib.request, urllib.parse, datetime, mimetypes

BASE = os.path.expanduser('~/Library/Application Support/kartuli')
CFG = f'{BASE}/telegram_config.json'
HIST = f'{BASE}/data/wod_history.json'
QUIZ_HIST = f'{BASE}/data/quiz_history.json'
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



# ---------------------------------------------------------------- тест дня

def pick_quiz(cfg):
    """Слово для теста и три отвлекающих варианта.

    Отвлекающие подбираются не случайно: сначала из той же категории и уровня,
    затем той же части речи, и всегда «слово к слову, фраза к фразе». Случайный
    набор делает тест бессмысленным — правильный ответ виден, не зная языка.
    """
    data = json.load(open(f'{BASE}/data/words.json', encoding='utf-8'))
    words = [w for w in data['words'] if w.get('q')]
    hist = json.load(open(QUIZ_HIST, encoding='utf-8')) if os.path.exists(QUIZ_HIST) else {}
    asked = set(hist.get('asked', []))

    levels = cfg.get('levels') or ['A1', 'A2', 'B1']
    cats = cfg.get('categories') or []
    def plain(w):
        # первый перевод должен быть словом, а не грамматической пометой вроде
        # «кем-либо (творитель действия)» — вопросом такое не задать
        ru = w['ru'].split(',')[0].strip()
        return ru and '(' not in ru and len(ru) <= 40

    pool = [w for w in words
            if w['lvl'] in levels and plain(w) and (not cats or any(c in cats for c in w['cats']))]
    fresh = [w for w in pool if w['id'] not in asked] or pool
    if len(fresh) == len(pool):
        asked = set()                                   # круг пройден, начинаем заново

    rnd = random.Random(datetime.date.today().toordinal() * 31 + 7)
    fresh.sort(key=lambda w: (-w['f'], w['id']))        # сначала употребимые, порядок устойчив
    w = rnd.choice(fresh[:max(40, len(fresh) // 15)])

    multi = ' ' in w['ka']
    def score(x):
        if x['id'] == w['id'] or x['ru'] == w['ru'] or x['ka'] == w['ka']:
            return -1
        if x['ru'].split(',')[0].strip() == w['ru'].split(',')[0].strip():
            return -1                                   # синоним — как отвлекающий не годится
        s = 0
        s += 30 if set(x['cats']) & set(w['cats']) else 0
        s += 20 if x['lvl'] == w['lvl'] else 0
        s += 15 if x.get('pos') == w.get('pos') else 0
        s += 12 if (' ' in x['ka']) == multi else 0
        return s

    ranked = sorted((x for x in pool if score(x) > 0), key=lambda x: (-score(x), rnd.random()))
    others = ranked[:3]
    if len(others) < 3:                                 # редкий случай узкой категории
        others += [x for x in words if score(x) > 0 and x not in others][:3 - len(others)]

    asked.add(w['id'])
    hist['asked'] = list(asked)
    hist['last'] = {'date': str(datetime.date.today()), 'ka': w['ka'], 'ru': w['ru']}
    json.dump(hist, open(QUIZ_HIST, 'w', encoding='utf-8'), ensure_ascii=False)
    return w, others, rnd


def send_quiz(cfg, chats, dry=False):
    w, others, rnd = pick_quiz(cfg)
    # направление чередуется по дням: сегодня переводим с грузинского, завтра на грузинский
    ka_to_ru = datetime.date.today().toordinal() % 2 == 0
    if ka_to_ru:
        question = f"Что значит «{w['ka']}»?"
        options = [x['ru'].split(',')[0].strip() for x in ([w] + others)]
    else:
        question = f"Как будет «{w['ru'].split(',')[0].strip()}»?"
        options = [x['ka'] for x in ([w] + others)]

    order = list(range(4))
    rnd.shuffle(order)
    options = [options[i][:100] for i in order]
    correct = order.index(0)
    explanation = f"{w['ka']} — {w['ru']} [{w['tr']}]"[:200]

    if dry:
        print(f"тест дня ({'грузинское → русское' if ka_to_ru else 'русское → грузинское'}):")
        print(f'  вопрос: {question}')
        for i, o in enumerate(options):
            print(f'  {"✓" if i == correct else " "} {o}')
        print(f'  пояснение: {explanation}')
        print(f'  получателей: {len(chats)}')
        return

    sent, failed = [], []
    for chat_id in chats:
        try:
            api(cfg, 'sendPoll', {
                'chat_id': chat_id,
                'question': question[:300],
                'options': json.dumps(options, ensure_ascii=False),
                'type': 'quiz',
                'correct_option_id': correct,
                'explanation': explanation,
                'is_anonymous': 'false',
                'is_closed': 'false',
            })
            sent.append(chat_id)
        except Exception as e:
            failed.append(f'{chat_id}: {e}')
    print(f"тест отправлен ({len(sent)} получателям): {w['ka']} — {w['ru']}")
    for f in failed:
        print('не доставлено —', f)


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
    dry = '--dry-run' in sys.argv
    if '--quiz' in sys.argv:
        send_quiz(cfg, chats, dry)
        return
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
    if dry:
        print('слово дня:'); print(text.replace('<b>', '').replace('</b>', '')
                                      .replace('<i>', '').replace('</i>', ''))
        print(f'озвучка: {"есть" if audio else "нет"} · получателей: {len(chats)}')
        return
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
