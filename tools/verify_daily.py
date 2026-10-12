# -*- coding: utf-8 -*-
"""Ежедневная сверка словаря с Google Переводчиком: сводка для решения.

Берёт N ещё не проверенных слов (по умолчанию 5), для каждого спрашивает
Google: слово → русский и → английский (английский — второе мнение: Google
переводит грузинский на русский через английский, и сбой виден по нему),
наш русский перевод → грузинский (вернётся ли то же слово) и каждый пример →
русский. Печатает сводку; решение и правки — за человеком или Claude
(tools/word.py). Ключ API не нужен.

Проверенным слово становится только после `word.py ok` или правки через
word.py — так сбой посреди проверки не отмечает непросмотренное.

  python3 tools/verify_daily.py            5 слов
  python3 tools/verify_daily.py -n 10      10 слов
  python3 tools/verify_daily.py სიახლე     конкретное слово
"""
import json, os, random, subprocess, sys, time, urllib.parse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = f'{BASE}/data/verify-log.json'
LEVEL_W = {'A1': 4, 'A2': 4, 'B1': 3, 'B2': 2, 'C1': 1}   # чаще то, что встретится раньше


def gt(text, sl, tl):
    """Через curl, а не urllib: на запросы из Python Google отвечает 429
    при любых заголовках, curl с той же машины получает ответ."""
    url = ('https://translate.googleapis.com/translate_a/single?client=gtx&dt=t'
           f'&sl={sl}&tl={tl}&q={urllib.parse.quote(text)}')
    err = ''
    for attempt in range(5):
        r = subprocess.run(['curl', '-s', '--max-time', '15', '-w', '\n%{http_code}', url],
                           capture_output=True, text=True)
        body, _, code = r.stdout.rpartition('\n')
        if code == '200':
            time.sleep(1)                      # чаще — Google отвечает 429
            data = json.loads(body)
            return ''.join(seg[0] for seg in data[0] if seg and seg[0])
        err = f'HTTP {code or "нет связи"}'
        time.sleep(10 * (attempt + 1))
    return f'(Google не ответил: {err})'


def main():
    args = sys.argv[1:]
    n = 5
    if args[:1] == ['-n']:
        n, args = int(args[1]), args[2:]
    words = json.load(open(f'{BASE}/data/words.json', encoding='utf-8'))['words']
    ex = json.load(open(f'{BASE}/data/examples.json', encoding='utf-8'))
    log = json.load(open(LOG, encoding='utf-8')) if os.path.exists(LOG) else {}
    ovr = json.load(open(f'{BASE}/data/overrides.json', encoding='utf-8')) \
        if os.path.exists(f'{BASE}/data/overrides.json') else {}

    if args:
        pick = [w for w in words if w['ka'] in args]
    else:
        # ручная правка — тоже решение человека, повторно не сверяем
        pool = [w for w in words if w['q'] and w['ka'] not in log and w['ka'] not in ovr]
        rnd = random.Random()
        pick = []
        while pool and len(pick) < n:
            w = rnd.choices(pool, weights=[LEVEL_W.get(x['lvl'], 1) for x in pool])[0]
            pick.append(w); pool.remove(w)
        left = len(pool)
        print(f'не проверено ещё: {left} слов (≈ {left // max(n, 1)} дней)\n')

    for i, w in enumerate(pick, 1):
        first = w['ru'].split(';')[0].split(',')[0].strip()
        print(f'━━ {i}. {w["ka"]} ({w["tr"]}) · {w["lvl"]} · {", ".join(w["cats"])} · id {w["id"]}')
        print(f'   у нас:         {w["ru"]}')
        print(f'   Google → ru:   {gt(w["ka"], "ka", "ru")}')
        print(f'   Google → en:   {gt(w["ka"], "ka", "en")}')
        print(f'   «{first}» → ka: {gt(first, "ru", "ka")}')
        for j, (ka, ru) in enumerate(ex.get(w['id'], []), 1):
            print(f'   пример {j}: {ka}')
            print(f'      у нас:  {ru}')
            print(f'      Google: {gt(ka, "ka", "ru")}')
        if not ex.get(w['id']):
            print('   примеров нет')
        print()


if __name__ == '__main__':
    main()
