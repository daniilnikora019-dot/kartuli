# -*- coding: utf-8 -*-
"""Сборка data/lessons.json из tools/lessons_content.py.

Здесь же делается перестановка вариантов ответа. В исходнике верный ответ всегда
стоит первым — так его видно при правке; в собранном файле он разложен по местам
детерминированно, от хэша «урок + номер вопроса». Значит, порядок один и тот же
при каждой сборке и на каждом устройстве: урок не меняется от сессии к сессии,
как и задумано, но и не выдаёт ответ первой строкой.
"""
import hashlib, json, os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lessons_content import LESSONS, TITLE, LEAD          # noqa: E402
from translit_ka import translit                          # noqa: E402

KA = re.compile('[Ⴀ-ჿ]')
errors = []


def permute(items, key):
    """Устойчивая перестановка: тот же ключ — тот же порядок, всегда."""
    h = hashlib.sha1(key.encode()).digest()
    order = sorted(range(len(items)), key=lambda i: (h[i % len(h)], i))
    return [items[i] for i in order], order


out = {'title': TITLE, 'lead': LEAD, 'lessons': []}
voice = []                                    # грузинские фразы для озвучки

for n, les in enumerate(LESSONS, 1):
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
                voice.append(ka)
            blocks.append(['ex', rows])
        elif kind == 't':
            head, body_rows = body
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

ids = [l['id'] for l in out['lessons']]
if len(set(ids)) != len(ids):
    errors.append('повторяющиеся идентификаторы уроков')

if errors:
    print('НЕ СОБРАНО:')
    for e in errors:
        print('  ·', e)
    sys.exit(1)

with open(f'{ROOT}/data/lessons.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

size = os.path.getsize(f'{ROOT}/data/lessons.json')
print(f"собрано: {len(out['lessons'])} уроков, {sum(len(l['quiz']) for l in out['lessons'])} вопросов, "
      f"{len(set(voice))} фраз с озвучкой, {size // 1024} КБ")
# места верного ответа — чтобы видеть, что он не залипает на одной позиции
pos = [0, 0, 0, 0]
for l in out['lessons']:
    for q in l['quiz']:
        pos[q['a']] += 1
print('верный ответ по позициям:', pos)
