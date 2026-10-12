# -*- coding: utf-8 -*-
"""Отсев примеров, которые достались слову из-за совпадения букв.

Слово ищется в предложении целиком или как начало более длинного слова: так
находятся падежные формы. Но начало совпадает и у совсем других слов:
რაში «конь» — რაშია «в чём (есть)», ყვავი «ворона» — ყვავილი «цветок»,
ლამა «лама» — ლამაზი «красивый», ქალა «череп» — ქალაქი «город». В карточке
это выглядело как перевод «конь» под примером «Скажите, в чём проблема».

Пример остаётся, если выполнено хотя бы одно:
  • слово стоит в предложении целиком;
  • за словом идёт обычное падежное окончание (-ს, -ით, -ზე, -ში, -დან…);
  • в русском переводе предложения есть начало одного из переводов слова.
Связка -ა («есть») сама по себе не спасает: именно она даёт რაშია.
Бывает, что так теряется верный пример (ლურჯია «голубое» при переводе
«синий»), но ложный пример хуже, чем никакого.

  python3 tools/example_check.py     # чистит data/examples.json на месте
Тот же фильтр стоит в build_examples.py. Ручной слой (examples-manual.json)
не трогается.
"""
import json, os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{BASE}/data/examples.json'
MANUAL = f'{BASE}/data/examples-manual.json'

CASE_ENDINGS = {'ს', 'თ', 'ზე', 'ში', 'დან', 'მდე', 'ც', 'მ', 'სთვის', 'სთან', 'სგან',
                'საც', 'ზეც', 'შიც', 'თაც'}
STOP = {'разг', 'перен', 'устар', 'книжн', 'что', 'кто', 'как', 'быть', 'для', 'или',
        'себя', 'свой', 'который', 'это', 'тот'}


def _tokens(t):
    return [x.strip('.,!?;:«»"\'()[]—-…') for x in t.lower().split()]


def _stems(ru):
    ru = re.sub(r'\([^)]*\)', '', ru.lower().replace('ё', 'е'))
    return {t[:3] if len(t) <= 5 else t[:4]
            for t in re.findall(r'[а-я]+', ru) if len(t) >= 3 and t not in STOP}


def plausible(word_ka, word_ru, ka, ru):
    base = word_ka.lower()
    if ' ' in base:
        return True
    toks = _tokens(ka)
    if base in toks or any(t.startswith(base) and t[len(base):] in CASE_ENDINGS for t in toks):
        return True
    r = ru.lower().replace('ё', 'е')
    return any(re.search(r'(?<![а-я])' + re.escape(s), r) for s in _stems(word_ru))


def main():
    words = {w['id']: w for w in json.load(open(f'{BASE}/data/words.json', encoding='utf-8'))['words']}
    data = json.load(open(OUT, encoding='utf-8'))
    keep = set(json.load(open(MANUAL, encoding='utf-8'))) if os.path.exists(MANUAL) else set()
    dropped = emptied = 0
    for wid in list(data):
        if wid in keep or wid not in words:
            continue
        w = words[wid]
        good = [p for p in data[wid] if plausible(w['ka'], w['ru'], p[0], p[1])]
        dropped += len(data[wid]) - len(good)
        if good:
            data[wid] = good
        else:
            del data[wid]; emptied += 1
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'убрано примеров: {dropped}, слов осталось без примеров: {emptied}')


if __name__ == '__main__':
    main()
