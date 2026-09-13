# -*- coding: utf-8 -*-
"""Примеры употребления: грузинское предложение + русский перевод.

Первый слой — Tatoeba: там обе стороны написаны людьми, переводить нечего
и ошибиться негде. Второй слой — Викисловарь, у него примеров мало, но они
качественные. Третий слой (предложения из корпуса с переводом вручную)
добавляется отдельным файлом data/examples-manual.json и имеет приоритет.

  python3 tools/build_examples.py
"""
import json, os, re, sys, collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = '/private/tmp/claude-501/-Users-daniilnikora/80cc56f5-30da-481e-a405-1437dcadb45d/scratchpad'
TAT = f'{SCRATCH}/tatoeba'
MANUAL = f'{BASE}/data/examples-manual.json'
OUT = f'{BASE}/data/examples.json'
MAX_PER_WORD = 3


def tatoeba_pairs():
    if not os.path.exists(f'{TAT}/kat.tsv'):
        return []
    def load(path):
        d = {}
        for line in open(path, encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 3: d[p[0]] = p[2].strip()
        return d
    kat, rus = load(f'{TAT}/kat.tsv'), load(f'{TAT}/rus.tsv')
    out = []
    for line in open(f'{TAT}/links.tsv', encoding='utf-8'):
        a, b = line.rstrip('\n').split('\t')[:2]
        if a in rus and b in kat: out.append((kat[b], rus[a]))
        elif b in rus and a in kat: out.append((kat[a], rus[b]))
    return out


def wiktionary_pairs():
    src = f'{SCRATCH}/ka_ru_wikt.jsonl'
    if not os.path.exists(src): return []
    out = []
    for line in open(src, encoding='utf-8'):
        e = json.loads(line)
        for s in e.get('senses', []):
            for ex in (s.get('examples') or []):
                t, tr = (ex.get('text') or '').strip(), (ex.get('translation') or '').strip()
                if t and tr: out.append((t, tr))
    return out


def good(ka, ru):
    """учебный пример: короткий, законченный, без ссылок и цифрового мусора"""
    if not (12 <= len(ka) <= 90) or not (8 <= len(ru) <= 120): return False
    if re.search(r'https?://|www\.|@|\d{4}', ka + ru): return False
    return ka.endswith(('.', '!', '?', '։'))


def main():
    words = json.load(open(f'{BASE}/data/words.json', encoding='utf-8'))['words']
    train = [w for w in words if w['q']]
    pairs = [(k, r) for k, r in tatoeba_pairs() + wiktionary_pairs() if good(k, r)]
    print(f'пригодных пар: {len(pairs)}')

    # Совпадение по подстроке даёт ложные примеры: короткое «და» (сестра)
    # находится внутри «მინდა» (хочу). Поэтому сверяем по целым словам, а
    # продолжение допускаем только у основ от четырёх букв — там это окончание.
    def tokens(t):
        return [x.strip('.,!?;:«»"\'()[]—-…') for x in t.lower().split()]

    idx = collections.defaultdict(list)
    tok_cache = [(ka, ru, tokens(ka)) for ka, ru in pairs]
    for ka, ru, toks in tok_cache:
        for w in train:
            base = w['ka'].lower()
            if ' ' in base:
                hit = base in ka.lower()
            else:
                hit = base in toks or (len(base) >= 4 and any(t.startswith(base) for t in toks))
            if hit:
                idx[w['id']].append((ka, ru))

    out = {}
    for w in train:
        got = idx.get(w['id'], [])
        # короткие примеры понятнее, и слово в них заметнее
        got.sort(key=lambda p: len(p[0]))
        seen, picked = set(), []
        for ka, ru in got:
            if ka in seen: continue
            seen.add(ka); picked.append([ka, ru])
            if len(picked) == MAX_PER_WORD: break
        if picked: out[w['id']] = picked

    if os.path.exists(MANUAL):          # ручной слой перекрывает собранный
        man = json.load(open(MANUAL, encoding='utf-8'))
        for wid, lst in man.items():
            out[wid] = [p for p in lst][:MAX_PER_WORD]
        print(f'ручных записей: {len(man)}')

    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    by_lvl = collections.Counter(w['lvl'] for w in train if w['id'] in out)
    total = collections.Counter(w['lvl'] for w in train)
    print(f'слов с примерами: {len(out)} из {len(train)}')
    for lvl in ['A1', 'A2', 'B1', 'B2', 'C1']:
        print(f'  {lvl}  {by_lvl[lvl]:5d} из {total[lvl]:5d}')
    print(f'всего предложений: {sum(len(v) for v in out.values())}')


if __name__ == '__main__':
    main()
