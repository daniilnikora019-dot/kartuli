# -*- coding: utf-8 -*-
"""Правка словаря одной командой: найти слово, поправить перевод, уровень,
примеры — и выложить.

Появился 12.10.2026: переводы из Викисловаря и примеры, подобранные по
совпадению букв, правятся постоянно («новизна» вместо «новость», «конь» с
примером «в чём проблема»), и каждый раз это было пять–десять ручных шагов.

  W=~/Developer/apps/.venv/bin/python; T=tools/word.py
  $W $T სიახლე                       карточка слова (поиск по слову, переводу или id)
  $W $T найти новость                то же, но поиск только по русскому переводу
  $W $T ru სიახლე "новость; новизна" перевод
  $W $T lvl რაში C1                  уровень A1…C1
  $W $T off რაში                     убрать из тренировок (в словаре остаётся)
  $W $T on რაში                      вернуть в тренировки
  $W $T del რაში                     выбросить из словаря совсем (с примерами и озвучкой)
  $W $T ex-drop რაში 1 3             снять примеры №1 и №3 (или all); пересборка их не вернёт
  $W $T ex-add სიახლე "…" "…"        свой пример (грузинский, русский) + озвучка
  $W $T tts                          озвучить новое, удалить ненужное
  $W $T check                        проверки данных
  $W $T test                         проверки + быстрые пользовательские сценарии
  $W $T ship "сообщение"             коммит, публикация, ожидание сайта

Ключ -a hayeren|romana — то же для другого тренажёра (перевод, уровень,
поиск; примеров и озвучки предложений там пока нет).

Куда что пишется:
  data/overrides.json        перевод/уровень/тема/q — применяется build_dataset.py
  data/examples-manual.json  свои примеры — перекрывают собранные
  data/examples-block.json   снятые примеры — build_examples.py их пропускает
words.json и examples.json правятся сразу, пересборка не нужна.
"""
import json, os, re, subprocess, sys, time, urllib.request

APPS = os.path.expanduser('~/Developer/apps')
VENV_PY = f'{APPS}/.venv/bin/python'
SITE = 'https://daniilnikora019-dot.github.io'
REPO = 'daniilnikora019-dot'
PORTS = {'kartuli': 8777, 'romana': 8778, 'hayeren': 8779}
LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1']

app = 'kartuli'
args = sys.argv[1:]
if args[:1] == ['-a']:
    app, args = args[1], args[2:]
BASE = f'{APPS}/{app}'
sys.path.insert(0, f'{BASE}/tools')


def jload(p, default=None):
    p = f'{BASE}/{p}'
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def jsave(p, data, compact=True):
    with open(f'{BASE}/{p}', 'w', encoding='utf-8') as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write('\n')


# пути к данным — из config.js тренажёра: у армянского и румынского имена файлов свои
_cfg = open(f'{BASE}/config.js', encoding='utf-8').read()
def _path(key, default):
    m = re.search(key + r":\s*'([^']+)'", _cfg)
    return m.group(1) if m else default
WORDS_P = _path('words', 'data/words.json')
WORDS = jload(WORDS_P)
EX = jload(_path('examples', 'data/examples.json'), {}) or {}
MN = jload(_path('mnemonics', 'data/mnemonics.json'), {}) or {}


def find(q, ru_only=False):
    ws = WORDS['words']
    if not ru_only:
        hit = [w for w in ws if w['ka'] == q or w['id'] == q]
        if hit:
            return hit
    ql = q.lower()
    hit = [w for w in ws if re.search(r'(?<![а-яё])' + re.escape(ql), w['ru'].lower())]
    if not ru_only:
        hit = [w for w in ws if ql in w['ka'].lower()] + hit
    return hit


def one(q):
    hit = [w for w in WORDS['words'] if w['ka'] == q or w['id'] == q]
    if len(hit) != 1:
        sys.exit(f'слово «{q}» не найдено точно; поиск: tools/word.py {q}')
    return hit[0]


def show(w, full=True):
    flag = '' if w['q'] else '  [не в тренировках]'
    print(f"{w['ka']}  ({w['tr']})  —  {w['ru']}")
    print(f"   id {w['id']} · {w['lvl']} · {', '.join(w['cats'])} · источник {w['src']} · частота {w['f']}{flag}")
    if not full:
        return
    ovr = jload('data/overrides.json', {}).get(w['ka'])
    if ovr:
        print(f'   ручная правка: {ovr}')
    if w['ka'] in MN:
        print(f'   ассоциация: {MN[w["ka"]]}')
    man = jload('data/examples-manual.json', {})
    lst = EX.get(w['id'], [])
    try:
        from example_check import plausible
    except ImportError:
        plausible = None
    for i, (ka, ru) in enumerate(lst, 1):
        mark = ''
        if plausible and w['id'] not in man and not plausible(w['ka'], w['ru'], ka, ru):
            mark = '  ⚠ похоже на совпадение букв'
        print(f'   {i}. {ka}\n      {ru}{mark}')
    if not lst:
        print('   примеров нет')
    if w['id'] in man:
        print('   (примеры ручные)')


def set_override(w, **kv):
    ovr = jload('data/overrides.json', {})
    cur = ovr.setdefault(w['ka'], {})
    cur.update(kv)
    jsave('data/overrides.json', ovr, compact=False)
    for x in WORDS['words']:
        if x['id'] == w['id']:
            x.update(kv)
    jsave(WORDS_P, WORDS)


def _recount():
    """счётчики тем и общее число слов — как их считает build_dataset.py"""
    import collections
    ws = WORDS['words']
    allc = collections.Counter(c for x in ws for c in x['cats'])
    train = collections.Counter(c for x in ws if x['q'] for c in x['cats'])
    for c in WORDS.get('categories', []):
        c['count'], c['all'] = train.get(c['id'], 0), allc.get(c['id'], 0)
    if 'meta' in WORDS:
        d = len(ws) - WORDS['meta'].get('total', len(ws))
        WORDS['meta']['total'] = len(ws)
        WORDS['meta']['wikt'] = WORDS['meta'].get('wikt', 0) + d


def run(cmd, **kw):
    print('$', cmd if isinstance(cmd, str) else ' '.join(cmd), flush=True)
    return subprocess.run(cmd, cwd=BASE, shell=isinstance(cmd, str), **kw)


def tts():
    if not os.path.exists(f'{BASE}/tools/tts_generate.py'):
        print('у этого тренажёра озвучка собирается иначе — пропускаю'); return
    old = set((jload('data/audio_index.json', {}) or {}).values())
    env = dict(os.environ, TTS_CONCURRENCY='3')
    for v in ('f', 'm'):
        for attempt in range(3):              # сервис иногда отвечает 403 — повтор помогает
            run([VENV_PY, '-I', 'tools/tts_generate.py', v], env=env)
            if not os.path.exists(f'{BASE}/audio/failed_{v}.json'):
                break
            os.remove(f'{BASE}/audio/failed_{v}.json'); time.sleep(3)
    new = set(jload('data/audio_index.json', {}).values())
    gone = 0
    for h in old - new:                       # только то, что было в индексе и выпало из него
        for v in ('f', 'm'):
            p = f'{BASE}/audio/{v}/{h}.mp3'
            if os.path.exists(p):
                os.remove(p); gone += 1
    print(f'удалено ненужных озвучек: {gone}')


def check():
    ok = True
    if os.path.exists(f'{BASE}/tools/check_build.py'):
        ok &= run([sys.executable, '-I', 'tools/check_build.py']).returncode == 0
    if os.path.exists(f'{BASE}/tools/example_check.py'):
        # оба фильтра должны быть уже применены: повторный прогон ничего не меняет
        before = open(f'{BASE}/data/examples.json', encoding='utf-8').read()
        for t in ('localize_names.py', 'example_check.py'):
            run([sys.executable, '-I', f'tools/{t}'], capture_output=True)
        after = open(f'{BASE}/data/examples.json', encoding='utf-8').read()
        if before != after:
            print('примеры поменялись после фильтров — проверьте git diff data/examples.json'); ok = False
        audio = jload('data/audio_index.json', {})
        miss = [ka for lst in jload('data/examples.json', {}).values() for ka, _ in lst if ka not in audio]
        if miss:
            print(f'без озвучки {len(miss)} примеров — запустите: tools/word.py tts'); ok = False
    for other in PORTS:
        if other != app and os.path.exists(f'{APPS}/{other}/tools/sync_shared.py') and app == 'kartuli':
            r = subprocess.run([sys.executable, '-I', 'tools/sync_shared.py', '--check'],
                               cwd=f'{APPS}/{other}', capture_output=True, text=True)
            if r.returncode != 0:
                print(f'{other}: общий код расходится с грузинским — cd ../{other} && python3 tools/sync_shared.py')
    print('проверки пройдены' if ok else 'ЕСТЬ ПРОБЛЕМЫ')
    return ok


def test():
    if not check():
        return False
    port = PORTS[app]
    srv = None
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1)
    except Exception:
        srv = subprocess.Popen([sys.executable, 'tools/serve.py'], cwd=BASE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
    try:
        sc = f'{APPS}/kartuli/tools/check_scenarios.py'
        names = ['norm-interrupted', 'instant-close', 'double-tap-known']
        if app != 'kartuli':
            print('сценарии написаны под порт грузинского тренажёра — пропускаю'); return True
        return run([VENV_PY, '-I', sc, *names]).returncode == 0
    finally:
        if srv:
            srv.terminate()


def ship(msg):
    paths = [x for x in ('data', 'audio', 'tools', 'app.js', 'style.css', 'sw.js', 'config.js', 'index.html')
             if os.path.exists(f'{BASE}/{x}')]
    run(['git', 'add', '-A', *paths])
    if run(['git', 'diff', '--cached', '--quiet']).returncode == 0:
        print('нечего выкладывать'); return
    run(['git', 'commit', '-q', '-m', msg])
    if run(['git', 'push', '-q', 'origin', 'main']).returncode != 0:
        sys.exit('не удалось отправить')
    time.sleep(6)
    rid = subprocess.run(['gh', 'run', 'list', '-R', f'{REPO}/{app}', '-L', '1', '--json', 'databaseId',
                          '-q', '.[0].databaseId'], capture_output=True, text=True).stdout.strip()
    if rid:
        r = subprocess.run(['gh', 'run', 'watch', rid, '-R', f'{REPO}/{app}', '--exit-status'],
                           capture_output=True, text=True)
        print('публикация:', 'готово' if r.returncode == 0 else 'ОШИБКА — gh run view ' + rid)
    print(f'сайт: {SITE}/{app}/ — на телефоне закрыть и открыть приложение')


def main():
    if not args:
        print(__doc__); return
    cmd, rest = args[0], args[1:]
    if cmd == 'ru':
        w = one(rest[0]); set_override(w, ru=rest[1]); show(w, False)
    elif cmd == 'lvl':
        lv = rest[1].upper()
        if lv not in LEVELS: sys.exit(f'уровень: {LEVELS}')
        w = one(rest[0]); set_override(w, lvl=lv); show(w, False)
    elif cmd in ('off', 'on'):
        w = one(rest[0]); set_override(w, q=0 if cmd == 'off' else 1); _recount(); jsave(WORDS_P, WORDS); show(w, False)
    elif cmd == 'del':
        w = one(rest[0])
        ovr = jload('data/overrides.json', {})
        ovr[w['ka']] = {'drop': True, 'note': ' '.join(rest[1:]) or f"было: {w['ru']}"}
        jsave('data/overrides.json', ovr, compact=False)
        WORDS['words'] = [x for x in WORDS['words'] if x['id'] != w['id']]
        _recount()
        jsave(WORDS_P, WORDS)
        if EX.pop(w['id'], None) is not None:
            jsave(_path('examples', 'data/examples.json'), EX)
        man = jload('data/examples-manual.json', {})
        if man.pop(w['id'], None) is not None:
            jsave('data/examples-manual.json', man, compact=False)
        if MN.pop(w['ka'], None) is not None:          # формат файла — одна строка на слово
            with open(f"{BASE}/{_path('mnemonics', 'data/mnemonics.json')}", 'w', encoding='utf-8') as f:
                f.write('{\n' + ',\n'.join(f'{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}'
                                            for k, v in MN.items()) + '\n}')
        print(f"выброшено: {w['ka']} — {w['ru']}"); tts()
    elif cmd == 'ex-drop':
        w = one(rest[0]); lst = EX.get(w['id'], [])
        nums = range(1, len(lst) + 1) if rest[1:] == ['all'] else [int(x) for x in rest[1:]]
        drop = [lst[n - 1][0] for n in nums]
        block = jload('data/examples-block.json', {})
        block[w['ka']] = sorted(set(block.get(w['ka'], [])) | set(drop))
        jsave('data/examples-block.json', block, compact=False)
        man = jload('data/examples-manual.json', {})
        keep = [p for p in lst if p[0] not in drop]
        if w['id'] in man:
            man[w['id']] = keep
            if not keep: del man[w['id']]
            jsave('data/examples-manual.json', man, compact=False)
        if keep: EX[w['id']] = keep
        else: EX.pop(w['id'], None)
        jsave('data/examples.json', EX)
        print(f'снято примеров: {len(drop)}'); show(w)
        print('озвучку лишнего удалит: tools/word.py tts')
    elif cmd == 'ex-add':
        w = one(rest[0]); ka, ru = rest[1].strip(), rest[2].strip()
        man = jload('data/examples-manual.json', {})
        cur = man.get(w['id']) or [p for p in EX.get(w['id'], [])]
        if [ka, ru] not in cur: cur.append([ka, ru])
        man[w['id']] = cur[-3:] if len(cur) > 3 else cur
        jsave('data/examples-manual.json', man, compact=False)
        EX[w['id']] = man[w['id']]
        jsave('data/examples.json', EX)
        show(w); tts()
    elif cmd == 'tts':
        tts()
    elif cmd == 'check':
        sys.exit(0 if check() else 1)
    elif cmd == 'test':
        sys.exit(0 if test() else 1)
    elif cmd == 'ship':
        ship(' '.join(rest) or 'Правка словаря')
    elif cmd == 'найти':
        for w in find(' '.join(rest), ru_only=True)[:15]: show(w, False)
    else:
        hit = find(' '.join(args))
        if not hit: print('ничего не найдено'); return
        for w in hit[:1]: show(w)
        if len(hit) > 1:
            print(f'\nещё совпадения ({len(hit) - 1}):')
            for w in hit[1:12]: show(w, False)


if __name__ == '__main__':
    main()
