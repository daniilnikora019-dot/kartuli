"""Пользовательские сценарии: порции новых слов, дневная норма, перерывы, вкладки.

Человек с телефоном проходит норму целиком, уходит посреди порции (перезапуск,
«Словарь», «Меню», статистика, главная), жмёт «Назад», ошибается в первом
повторении, смахивает карточки, нажимает дважды, закрывает приложение сразу
после нажатия, возвращается через 13 часов. После каждой порции сверяется:
размер порции, «взято в изучение» на экране, прирост дневной нормы, что ничего
не осталось недоповторённым и что сохранённая порция убрана.

Появился 12.10.2026, когда порция из 20 слов обрывалась после перезапуска.

  python3 tools/serve.py &                      # локально синхронизация отключена
  python3 -m venv /tmp/pwv && /tmp/pwv/bin/pip install playwright
  /tmp/pwv/bin/python tools/check_scenarios.py              # все сценарии
  /tmp/pwv/bin/python tools/check_scenarios.py expired-12h  # один
Нужен установленный Google Chrome.
"""
import asyncio, json, random, re, sys
from playwright.async_api import async_playwright

URL = 'http://127.0.0.1:8777/'
ISSUES = []

def issue(scn, msg):
    ISSUES.append(f'[{scn}] {msg}')
    print(f'   !! {msg}', flush=True)


class U:
    """Человек с телефоном: нажимает только то, что видно на экране."""
    def __init__(self, pg, scn, rnd):
        self.pg, self.scn, self.rnd = pg, scn, rnd
        self.log = []

    async def boot(self):                 # «закрыл и открыл приложение»
        await self.pg.goto(URL)
        await self.pg.wait_for_function("typeof S !== 'undefined' && S.words && S.words.length > 0 && document.querySelector('#main').children.length")
        await self.pg.wait_for_timeout(300)

    async def ev(self, js):
        return await self.pg.evaluate(js)

    async def screen(self):
        pg = self.pg
        if await pg.locator('.new-card').count(): return 'intro'
        if await pg.locator('.after-answer').count(): return 'after'
        if await pg.locator('.opt').count(): return 'choice'
        if await pg.locator('.review-card').count(): return 'review'
        txt = await pg.locator('#main').inner_text()
        if 'Порция пройдена' in txt: return 'done'
        if 'Дневная норма выполнена' in txt: return 'norm'
        if 'Сколько слов возьмём' in txt: return 'picker'
        if 'Сколько новых слов учить в день' in txt: return 'welcome'
        if await pg.locator('[data-act=learn]').count(): return 'home'
        return 'other:' + txt[:80].replace('\n', ' ')

    async def title(self):
        loc = self.pg.locator('.trainer-head .sub')
        return (await loc.text_content()).strip() if await loc.count() else ''

    async def tap(self, sel):
        await self.pg.locator(sel).first.click()
        await self.pg.wait_for_timeout(120)

    async def tab(self, name):            # нижняя панель
        await self.tap(f'.tab[data-go={name}]')

    async def home_learn(self):
        if await self.screen() != 'home':
            await self.tab('home')
        await self.tap('[data-act=learn]')

    async def pick_batch(self, n=None):
        """n=None — «Как по норме»"""
        if n is None:
            btns = self.pg.locator('.cat-card', has_text='Как по норме')
            if await btns.count():
                await btns.first.click()
            else:
                await self.tap('#own-go')
        else:
            await self.pg.fill('#own', str(n))
            await self.tap('#own-go')
        await self.pg.wait_for_timeout(150)

    async def intro_act(self, act, swipe=False):
        await self.pg.wait_for_timeout(520)
        if swipe:
            card = self.pg.locator('.new-card')
            bb = await card.bounding_box()
            x, y = bb['x'] + bb['width'] / 2, bb['y'] + 60
            await self.pg.mouse.move(x, y); await self.pg.mouse.down()
            d = 1 if act == 'learn' else -1
            for k in range(1, 9):
                await self.pg.mouse.move(x + d * k * 18, y); await self.pg.wait_for_timeout(15)
            await self.pg.mouse.up(); await self.pg.wait_for_timeout(400)
        else:
            await self.tap(f'[data-a={act}]')

    async def choice_answer(self, want_right=True):
        await self.pg.wait_for_timeout(520)
        w = await self.ev("(() => { const s = S.session; const w = s.drill ? s.drill[s.i] : null; return w && {id: w.id, ru: w.ru, ka: w.ka}; })()")
        title = await self.title()
        field = 'ru' if 'перевод' in title and 'по-грузински' not in title else 'ka'
        opts = self.pg.locator('.opt')
        texts = [re.sub(r'^\d+\.\s*', '', t.split('\n')[0]).strip() for t in await opts.all_inner_texts()]
        right = [i for i, t in enumerate(texts) if t == w[field]]
        if len(right) != 1:
            issue(self.scn, f'среди вариантов правильный встречается {len(right)} раз: {texts} / {w[field]}')
        if want_right and right:
            idx = right[0]
        else:
            idx = next(i for i in range(len(texts)) if i not in right)
        await opts.nth(idx).click(); await self.pg.wait_for_timeout(120)
        got_right = await opts.nth(idx).evaluate("b => b.classList.contains('right')")
        return got_right

    async def after_next(self, again=False):
        if again or not await self.pg.locator('[data-a=next]').count():
            await self.tap('[data-a=again]')
        else:
            await self.tap('[data-a=next]')

    async def state(self):
        return await self.ev("""(() => ({
          started: dayRec(today()).started, known: dayRec(today()).known,
          pend: (S.prog.pend || []).length, saved: localStorage.getItem(L.key + '_learn_v1'),
          norm: S.prog.set.newPerDay,
          learning: Object.values(S.prog.w).filter(p => p.s === 'learning').length,
        }))()""")


async def interrupt(u, kind):
    """Разные способы уйти посреди порции и вернуться."""
    if kind == 'reload':
        await u.boot()
        await u.home_learn()
    elif kind == 'dict':
        await u.tab('dict'); await u.pg.wait_for_timeout(150)
        await u.home_learn()
    elif kind == 'menu':
        await u.tab('menu'); await u.pg.wait_for_timeout(150)
        await u.tab('home'); await u.home_learn()
    elif kind == 'stats':
        await u.tab('menu'); await u.pg.wait_for_timeout(100)
        await u.ev("go('stats')"); await u.pg.wait_for_timeout(150)
        await u.tab('home'); await u.home_learn()
    elif kind == 'home':
        await u.tab('home'); await u.home_learn()
    elif kind == 'reload-home-check':
        await u.boot()
        if await u.screen() != 'home':
            await u.tab('home')
        row = (await u.pg.locator('[data-act=learn]').inner_text()).replace('\n', ' | ')
        await u.tap('[data-act=learn]')
        return row


async def run_portion(u, *, n=None, known_p=0.15, wrong_p=0.15, again_p=0.05, swipe_p=0.2,
                      interrupts=(), back_p=0.0, pre=0):
    """Проходит одну порцию от выбора размера до «Порция пройдена». Возвращает,
    сколько слов взято в изучение по счёту приложения и по нашему счёту."""
    scn = u.scn
    scr = await u.screen()
    if scr == 'picker':
        await u.pick_batch(n)
    st0 = await u.state()
    target = None
    taken = set()
    acts = []                              # стопка действий — «Назад» снимает последнее
    last_k = 0
    steps = 0
    intr = list(interrupts)
    seen_drill = False
    while True:
        steps += 1
        if steps > 400:
            issue(scn, 'порция не заканчивается за 400 шагов'); break
        scr = await u.screen()
        title = await u.title()
        if intr and u.rnd.random() < 0.12 and scr in ('intro', 'choice', 'after'):
            kind = intr.pop(0)
            before = title
            row = await interrupt(u, kind)
            after = await u.title()
            ok_same = (before.split('·')[0].strip() == after.split('·')[0].strip()) if 'Новое слово' in before else ('Первое повторение' in after or await u.screen() == 'done')
            u.log.append(f'{kind}: «{before}» → «{after}»' + (f' (главная: {row})' if row else ''))
            if 'Новое слово' in before and not ok_same:
                issue(scn, f'после «{kind}» порция не продолжилась: было «{before}», стало «{after}» [{await u.screen()}]')
            continue
        if scr == 'intro':
            m = re.match(r'Новое слово (\d+) из (\d+)', title)
            if not m:
                issue(scn, f'странный заголовок карточки: {title}')
                break
            k, t = int(m.group(1)), int(m.group(2))
            if target is None: target = t
            if t != target: issue(scn, f'размер порции поменялся: {target} → {t}')
            if seen_drill: issue(scn, 'после первого повторения снова пошли новые слова')
            if k < last_k and 'back' not in u.log[-2:]:
                issue(scn, f'счётчик новых слов пошёл назад: {last_k} → {k}')
            last_k = k
            if back_p and k > 1 and u.rnd.random() < back_p and await u.pg.locator('.back-btn:not([disabled])').count():
                await u.tap('.back-btn'); u.log.append('back')
                if acts:
                    wid0, a0 = acts.pop()
                    if a0 == 'learn': taken.discard(wid0)
                t2 = await u.title()
                continue
            wid = await u.ev("S.session.queue[S.session.i].id")
            act = 'known' if u.rnd.random() < known_p else 'learn'
            await u.intro_act(act, swipe=u.rnd.random() < swipe_p)
            if await u.ev("S.session && S.session.queue[S.session.i] ? S.session.queue[S.session.i].id : null") != wid:
                acts.append((wid, act))
                if act == 'learn': taken.add(wid)
        elif scr == 'choice':
            if 'Первое повторение' not in title:
                issue(scn, f'неожиданный экран выбора: {title}')
            if not seen_drill:
                seen_drill = True
                if target and last_k < target:
                    # первое повторение может начаться раньше только если запас новых слов кончился
                    issue(scn, f'первое повторение началось на слове {last_k} из {target}')
            await u.choice_answer(want_right=u.rnd.random() >= wrong_p)
        elif scr == 'after':
            await u.after_next(again=u.rnd.random() < again_p)
        elif scr == 'done':
            txt = await u.pg.locator('#main').inner_text()
            m = re.search(r'Взято в изучение: (\d+)', txt)
            shown = int(m.group(1)) if m else -1
            st1 = await u.state()
            return {'target': target, 'shown': shown, 'taken': len(taken) + pre, 'pre': pre,
                    'started_delta': st1['started'] - st0['started'], 'state': st1, 'steps': steps}
        else:
            issue(scn, f'неожиданный экран посреди порции: {scr} / {title}')
            return None


async def new_user(b, norm=20, seed=1):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
    pg = await ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    return ctx, pg, errs


async def onboard(u, norm):
    await u.boot()
    if await u.screen() == 'welcome':
        await u.pg.fill('#own', str(norm)); await u.tap('#own-go')


def check_portion(scn, r, expect_target=None):
    if not r: return
    print(f'   порция: размер {r["target"]}, на экране «взято {r["shown"]}», по нашему счёту {r["taken"]}, '
          f'норма +{r["started_delta"]}, ждут повторения {r["state"]["pend"]}, сохранено: {bool(r["state"]["saved"])}')
    if expect_target is not None and r['target'] != expect_target:
        issue(scn, f'размер порции {r["target"]}, ожидали {expect_target}')
    if r['shown'] != r['taken']:
        issue(scn, f'на экране «взято {r["shown"]}», а взято {r["taken"]}')
    if r['started_delta'] + r.get('pre', 0) != r['taken']:
        issue(scn, f'дневная норма выросла на {r["started_delta"]}, а взято {r["taken"]}')
    if r['taken'] != r['target']:
        issue(scn, f'взято {r["taken"]} при порции {r["target"]} («уже знаю» должно подменяться следующим словом)')
    if r['state']['pend']:
        issue(scn, f'после порции {r["state"]["pend"]} слов всё ещё ждут первого повторения')
    if r['state']['saved']:
        issue(scn, 'после конца порции осталась сохранённая порция')


async def main():
    only = sys.argv[1:]
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', headless=True)

        async def scenario(name, fn):
            if only and name not in only: return
            print(f'\n== {name}', flush=True)
            ctx, pg, errs = await new_user(b)
            u = U(pg, name, random.Random(hash(name) & 0xffff))
            try:
                await fn(u)
            except Exception as e:
                issue(name, f'сценарий упал: {type(e).__name__}: {str(e)[:300]}')
                try: issue(name, f'экран: {await u.screen()} / {await u.title()}')
                except Exception: pass
            for l in u.log: print('   ·', l)
            for e in errs: issue(name, f'ошибка JS: {e[:200]}')
            await ctx.close()

        # 1. Полная дневная норма одной порцией, без перерывов
        async def s1(u):
            await onboard(u, 20)
            await u.home_learn()
            r = await run_portion(u, n=None)
            check_portion(u.scn, r, 20)
            await u.tap('[data-a]') if False else None
            await u.home_learn()
            scr = await u.screen()
            print('   после нормы:', scr)
            if scr != 'norm': issue(u.scn, f'после нормы ожидали «Дневная норма выполнена», а экран {scr}')
            row = (await u.pg.locator('[data-act=learn]').inner_text()).replace('\n', ' | ') if await u.screen() == 'home' else ''
        await scenario('norm-straight', s1)

        # 2. Норма 20 с перерывами всех видов посреди знакомства и повторения
        async def s2(u):
            await onboard(u, 20)
            await u.home_learn()
            r = await run_portion(u, n=None, interrupts=['reload', 'dict', 'menu', 'reload', 'stats', 'home',
                                                          'reload', 'dict', 'reload', 'menu', 'reload', 'home'])
            check_portion(u.scn, r, 20)
            await u.home_learn()
            if await u.screen() != 'norm': issue(u.scn, f'после нормы экран {await u.screen()}')
        await scenario('norm-interrupted', s2)

        # 3. Норма двумя порциями: 5, затем «как по норме» должно предложить 15
        async def s3(u):
            await onboard(u, 20)
            await u.home_learn()
            r = await run_portion(u, n=5, interrupts=['reload'])
            check_portion(u.scn, r, 5)
            await u.tap('.btn.primary')            # «Следующая порция»
            sug = await u.pg.locator('.cat-card', has_text='Как по норме').inner_text()
            print('   предложено:', sug.replace('\n', ' '))
            if not sug.startswith('15'): issue(u.scn, f'после 5 из 20 предложено: {sug!r}')
            r = await run_portion(u, n=None, interrupts=['dict', 'reload'])
            check_portion(u.scn, r, 15)
            await u.home_learn()
            if await u.screen() != 'norm': issue(u.scn, f'после нормы экран {await u.screen()}')
        await scenario('norm-two-portions', s3)

        # 4. Кнопка «Назад» в знакомстве и в повторении, потом перезапуск
        async def s4(u):
            await onboard(u, 10)
            await u.home_learn()
            r = await run_portion(u, n=None, back_p=0.25, interrupts=['reload', 'reload'])
            check_portion(u.scn, r, 10)
        await scenario('back-button', s4)

        # 5. Главная показывает «Продолжить порцию» после перезапуска
        async def s5(u):
            await onboard(u, 20)
            await u.home_learn(); await u.pick_batch(None)
            for _ in range(4): await u.intro_act('learn')
            row = await interrupt(u, 'reload-home-check')
            print('   главная:', row, '→', await u.title())
            if 'Продолжить порцию' not in row or 'Новое слово 5 из 20' not in row:
                issue(u.scn, f'на главной: {row}')
            if not (await u.title()).startswith('Новое слово 5 из 20'):
                issue(u.scn, f'после «Продолжить порцию»: {await u.title()}')
            r = await run_portion(u, pre=4)
            check_portion(u.scn, r, 20)
        await scenario('home-continue', s5)

        # 6. Перерыв дольше 12 часов: порция не продолжается, взятые слова идут в первое повторение
        async def s6(u):
            await onboard(u, 20)
            await u.home_learn(); await u.pick_batch(None)
            for _ in range(6): await u.intro_act('learn')
            await u.ev("(() => { const k = L.key + '_learn_v1'; const d = JSON.parse(localStorage.getItem(k)); d.at -= 13 * 3600e3; localStorage.setItem(k, JSON.stringify(d)); })()")
            await u.boot(); await u.home_learn()
            print('   через 13 часов:', await u.screen(), await u.title())
            if 'Первое повторение' not in await u.title():
                issue(u.scn, f'через 13 часов ожидали первое повторение 6 слов: {await u.title()}')
            r = await run_portion(u)
            if r:
                print(f'   экран: «взято {r["shown"]}»')
                if r['shown'] != 6: issue(u.scn, f'после старых 6 слов на экране «взято {r["shown"]}»')
                if r['state']['pend']: issue(u.scn, 'остались слова без первого повторения')
            await u.tap('.btn.primary')
            sug = await u.pg.locator('.cat-card', has_text='Как по норме').inner_text()
            if not sug.startswith('14'): issue(u.scn, f'после 6 из 20 предложено {sug!r}')
        await scenario('expired-12h', s6)

        # 7. Сверх нормы
        async def s7(u):
            await onboard(u, 5)
            await u.home_learn()
            check_portion(u.scn, await run_portion(u, n=None), 5)
            await u.home_learn()
            if await u.screen() != 'norm': issue(u.scn, f'экран {await u.screen()}'); return
            await u.pg.locator('button', has_text='Учить сверх нормы').click(); await u.pg.wait_for_timeout(150)
            print('   сверх нормы:', await u.screen())
            r = await run_portion(u, n=5, interrupts=['reload'])
            check_portion(u.scn, r, 5)
        await scenario('over-norm', s7)

        # 8. Взятые слова подошли к повторению, человек ушёл в «Повторить» посреди порции
        async def s8(u):
            await onboard(u, 20)
            await u.home_learn(); await u.pick_batch(10)
            for _ in range(5): await u.intro_act('learn')
            await u.ev("Object.values(S.prog.w).forEach(p => { if (p.s === 'learning') p.d = Date.now() - 1000; }); saveProgress()")
            await u.tab('home'); await u.tap('[data-act=review]'); await u.pg.wait_for_timeout(200)
            print('   повторение:', await u.screen(), await u.title())
            await u.tab('home'); await u.home_learn()
            print('   вернулись:', await u.title())
            if not (await u.title()).startswith('Новое слово 6 из 10'):
                issue(u.scn, f'после захода в повторение: {await u.title()}')
            check_portion(u.scn, await run_portion(u, pre=5), 10)
        await scenario('review-detour', s8)

        # 9. Двойные нажатия и много «уже знаю»
        async def s9(u):
            await onboard(u, 10)
            await u.home_learn(); await u.pick_batch(None)
            for _ in range(5):
                await u.pg.wait_for_timeout(600)
                await u.pg.locator('[data-a=learn]').dblclick(); await u.pg.wait_for_timeout(100)
            print('   после 5 двойных нажатий:', await u.title())
            st = await u.state()
            if st['started'] != 5: issue(u.scn, f'двойные нажатия: взято {st["started"]} вместо 5')
            r = await run_portion(u, known_p=0.6, pre=5)
            check_portion(u.scn, r, 10)
        await scenario('double-tap-known', s9)

        # 10. Двойное касание «Я вспомнил» в повторении оценивает одно слово
        async def s10(u):
            await onboard(u, 5)
            await u.home_learn(); check_portion(u.scn, await run_portion(u, n=None, wrong_p=0), 5)
            await u.ev("Object.values(S.prog.w).forEach(p => { if (p.s === 'learning') p.d = Date.now() - 1000; }); saveProgress()")
            await u.tab('home'); await u.tap('[data-act=review]'); await u.pg.wait_for_timeout(300)
            before = await u.ev("dayRec(today()).ans")
            done = 0
            for _ in range(5):
                if not await u.pg.locator('[data-g=yes]').count(): break
                await u.pg.wait_for_timeout(600)
                await u.pg.locator('[data-g=yes]').dblclick(); await u.pg.wait_for_timeout(100)
                done += 1
            after = await u.ev("dayRec(today()).ans")
            print(f'   двойных касаний: {done}, оценок: {after - before}, экран: {await u.screen()}')
            if after - before != done: issue(u.scn, f'{done} двойных касаний дали {after - before} оценок')
        await scenario('review-double-tap', s10)

        # 11. Только смахивания
        async def s11(u):
            await onboard(u, 10)
            await u.home_learn()
            check_portion(u.scn, await run_portion(u, n=None, swipe_p=1.0, known_p=0.3), 10)
        await scenario('swipe-only', s11)

        # 12. Закрыл приложение сразу после нажатия (без паузы)
        async def s12(u):
            await onboard(u, 20)
            await u.home_learn(); await u.pick_batch(None)
            for k in range(6):
                await u.pg.wait_for_timeout(520)
                await u.pg.locator('[data-a=learn]').click()
                await u.boot()                    # ни миллисекунды на запись
                await u.home_learn()
            st = await u.state()
            print(f'   после 6 «учить» с мгновенным закрытием: взято {st["started"]}, экран «{await u.title()}»')
            if st['started'] != 6: issue(u.scn, f'взято {st["started"]} из 6')
            if not (await u.title()).startswith('Новое слово 7 из 20'): issue(u.scn, f'экран {await u.title()}')
            check_portion(u.scn, await run_portion(u, pre=6), 20)
        await scenario('instant-close', s12)

        await b.close()
    print('\n==== ИТОГ ====')
    print('\n'.join(ISSUES) if ISSUES else 'замечаний нет')

asyncio.run(main())
