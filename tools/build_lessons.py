# -*- coding: utf-8 -*-
"""Сборка тем раздела «Грамматика»: tools/grammar/<тема>.py → data/grammar/<тема>.json.

Какие темы собирать и в каком порядке они стоят в приложении — список TOPICS
ниже; тот же порядок должен быть в `grammar: [...]` в config.js (сверяется здесь же).

Здесь же делается перестановка вариантов ответа. В исходнике верный ответ всегда
стоит первым — так его видно при правке; в собранном файле он разложен по местам
детерминированно, от хэша «урок + номер вопроса». Значит, порядок один и тот же
при каждой сборке и на каждом устройстве: урок не меняется от сессии к сессии,
как и задумано, но и не выдаёт ответ первой строкой.
"""
import hashlib, importlib, json, os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from translit_ka import translit                          # noqa: E402

# порядок тем в приложении: сверху вниз, как в утверждённом плане раздела
TOPICS = ['sounds', 'nouns', 'postpositions', 'pronouns', 'verb']

KA = re.compile('[Ⴀ-ჿ]')
errors = []


def permute(items, key):
    """Устойчивая перестановка: тот же ключ — тот же порядок, всегда."""
    h = hashlib.sha1(key.encode()).digest()
    order = sorted(range(len(items)), key=lambda i: (h[i % len(h)], i))
    return [items[i] for i in order], order


def build(mod):
    out = {'title': mod.TITLE, 'lead': mod.LEAD, 'lessons': []}
    for n, les in enumerate(mod.LESSONS, 1):
        if len(les['quiz']) != 10:
            errors.append(f"{les['id']}: вопросов {len(les['quiz'])}, а нужно 10")
        blocks = []
        for kind, body in les['blocks']:
            if kind == 'ex':
                rows = []
                for ka, ru in body:
                    if not KA.search(ka):
                        errors.append(f"{les['id']}: пример без грузинского текста — {ka!r}")
                    rows.append([ka, translit(ka), ru])
                blocks.append(['ex', rows])
            elif kind == 't':
                head, body_rows = body
                if any(len(r) != len(head) for r in body_rows):
                    errors.append(f"{les['id']}: в таблице «{head[0]}» строки разной длины")
                # каждая ячейка — [текст, 1 если родное письмо]: общий код не должен
                # сам распознавать алфавит, иначе в нём появляется привязка к языку
                marked = [[[c, 1 if KA.search(c) else 0] for c in row] for row in body_rows]
                blocks.append(['t', [head, marked]])
            else:
                blocks.append([kind, body])
        quiz = []
        for qi, (q, opts, a, why) in enumerate(les['quiz']):
            if len(set(opts)) != len(opts):
                errors.append(f"{les['id']} вопрос {qi + 1}: повторяющиеся варианты")
            if not 0 <= a < len(opts):
                errors.append(f"{les['id']} вопрос {qi + 1}: неверный номер ответа")
                continue
            right = opts[a]
            shuffled, _ = permute(list(opts), f"{les['id']}:{qi}")
            quiz.append({'q': q, 'o': [[o, 1 if KA.search(o) else 0] for o in shuffled],
                         'a': shuffled.index(right), 'why': why})
        out['lessons'].append({'id': les['id'], 'n': n, 'title': les['title'],
                               'short': les['short'], 'blocks': blocks, 'quiz': quiz})
    return out


built = {name: build(importlib.import_module(f'grammar.{name}')) for name in TOPICS}

# прогресс хранится по идентификатору урока, поэтому он уникален во всём разделе
ids = [l['id'] for t in built.values() for l in t['lessons']]
dup = sorted({i for i in ids if ids.count(i) > 1})
if dup:
    errors.append('повторяющиеся идентификаторы уроков: ' + ', '.join(dup))

cfg = open(f'{ROOT}/config.js', encoding='utf-8').read()
m = re.search(r'grammar:\s*\[(.*?)\]', cfg, re.S)
listed = re.findall(r"'([^']+)'", m.group(1)) if m else []
expected = [f'data/grammar/{name}.json' for name in TOPICS]
if listed != expected:
    errors.append(f'в config.js grammar = {listed}, а должно быть {expected}')

if errors:
    print('НЕ СОБРАНО:')
    for e in errors:
        print('  ·', e)
    sys.exit(1)

pos = [0, 0, 0, 0]
for name, out in built.items():
    path = f'{ROOT}/data/grammar/{name}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    phrases = {r[0] for l in out['lessons'] for k, b in l['blocks'] if k == 'ex' for r in b}
    print(f"{name}: {len(out['lessons'])} уроков, {sum(len(l['quiz']) for l in out['lessons'])} вопросов, "
          f"{len(phrases)} фраз с озвучкой, {os.path.getsize(path) // 1024} КБ")
    for l in out['lessons']:
        for q in l['quiz']:
            pos[q['a']] += 1
# места верного ответа — чтобы видеть, что он не залипает на одной позиции
print('верный ответ по позициям:', pos)
