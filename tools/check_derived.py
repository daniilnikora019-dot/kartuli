"""
Поиск ошибочных переводов вида «მაცივარია = мне холодно» (11.10.2026).

Паттерн: слово словаря — это ДРУГОЕ слово словаря плюс грамматическое
окончание (связка -ა/-ია «есть», падеж, множественное число), а перевод
не имеет ничего общего с переводом основы. მაცივარია = მაცივარ(ი) + ია
«это холодильник», а в словаре стояло «мне холодно» (это მცივა).
Такие ошибки рождаются, когда форму подбирают по звучанию.

Запуск: python3 tools/check_derived.py  → список подозрительных пар.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# окончания: связка, падежи, мн. число, послелоги, слитые с существительным
SUFFIXES = sorted(["ია", "ა", "ს", "ის", "ით", "ად", "ში", "ზე", "თან", "ისთვის", "ისგან",
                   "ები", "ებს", "ების", "ებში", "ებზე", "ებით", "მა", "მ", "ც", "ცა", "ო"],
                  key=len, reverse=True)
STOP = {"мне", "тебе", "это", "быть", "есть", "очень", "свой", "себя", "который"}


def stems(ru: str) -> set[str]:
    words = re.findall(r"[а-яё]+", ru.lower())
    return {w[:4] for w in words if len(w) >= 4 and w not in STOP}


def main() -> None:
    W = json.loads((ROOT / "data" / "words.json").read_text())["words"]
    by = {}
    for w in W:
        by.setdefault(w["ka"], []).append(w)
    found = []
    for w in W:
        ka = w["ka"]
        if " " in ka:
            continue
        for suf in SUFFIXES:
            if not ka.endswith(suf) or len(ka) - len(suf) < 3:
                continue
            stem = ka[: -len(suf)]
            # основа в словаре: как есть или с отпавшим именительным -ი
            bases = [b for k in (stem, stem + "ი", stem + "ა") if k != ka for b in by.get(k, [])]
            for b in bases:
                if b["pos"] not in ("noun", "adj"):
                    continue
                # связка «есть» (-ა/-ია) у фразы: перевод обязан содержать слово
                # основы целиком — по корню «холод» ловушка «холодильник ≈ холодно»
                # проходила проверку (так и прятался მაცივარია «мне холодно»)
                copula = suf in ("ა", "ია") and w["pos"] in ("phrase", "")
                if copula:
                    full = {x for x in re.findall(r"[а-яё]+", b["ru"].lower()) if len(x) >= 4}
                    if full & set(re.findall(r"[а-яё]+", w["ru"].lower())):
                        continue
                elif stems(w["ru"]) & stems(b["ru"]):
                    continue
                found.append((w, b, suf, copula))
            if bases:
                break
    seen = set()
    found.sort(key=lambda x: not x[3])
    for w, b, suf, copula in found:
        key = (w["ka"], b["ka"])
        if key in seen:
            continue
        seen.add(key)
        print(("!! " if copula else "   ") + f"{w['ka']} «{w['ru']}» [{w['pos']}, {w.get('src','')}]  =  {b['ka']} «{b['ru']}» + -{suf}")
    print(f"\nподозрительных: {len(seen)}", file=sys.stderr)


if __name__ == "__main__":
    main()
