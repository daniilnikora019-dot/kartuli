// Напоминания тренажёра: push на телефон, если дневная норма новых слов
// ещё не взята. Вызывается двумя способами:
//   * расписанием pg_cron каждые 10 минут — с заголовком x-cron-secret;
//   * из приложения кнопкой «Прислать пробное» — с пропуском пользователя.
// Ключи VAPID, секрет расписания и список тех, кому напоминания разрешены,
// лежат в закрытой схеме private и читаются только служебным ключом.
import webpush from 'npm:web-push@3.6.7';
import { createClient } from 'npm:@supabase/supabase-js@2.45.4';

const db = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
const WINDOW_MIN = 180;          // опоздавшее напоминание (сервер, сеть) позже трёх часов не шлём

type Sub = {
  user_id: string; app: string; endpoint: string; p256dh: string; auth: string;
  enabled: boolean; remind_at: string; tz: string; last_day: string | null;
};
type Day = { ans?: number; rev?: number; drilled?: number; new?: number; started?: number };

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });

function plural(n: number, one: string, few: string, many: string) {
  const a = n % 10, b = n % 100;
  const w = a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
  return `${n} ${w}`;
}

// местные дата и минуты от полуночи в часовом поясе устройства
function localNow(tz: string) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date()).map(x => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, min: +p.hour * 60 + +p.minute };
}
const shift = (day: string, n: number) => {
  const d = new Date(day + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
// то же правило, что dayActive в app.js: день занятий — день, когда был ответ
const active = (r?: Day) => !!r && !!(r.ans || r.rev || r.drilled || r.new);

function summary(data: any, day: string) {
  const days: Record<string, Day> = data?.days || {};
  const norm = Math.max(1, +data?.set?.newPerDay || 12);
  const started = days[day]?.started || 0;
  let d = active(days[day]) ? day : shift(day, -1), streak = 0;
  while (active(days[d])) { streak++; d = shift(d, -1); }
  const now = Date.now();
  const due = Object.values<any>(data?.w || {}).filter(p => p.s === 'learning' && p.d <= now).length;
  return { norm, started, left: Math.max(0, norm - started), streak, due, best: +data?.best || 0 };
}

// Текст напоминания. Варианты чередуются по дню, чтобы не приедаться.
function message(s: ReturnType<typeof summary>, day: string) {
  const seed = Math.floor(Date.parse(day + 'T00:00:00Z') / 864e5);
  const pick = <T>(xs: T[]) => xs[seed % xs.length];
  const words = plural(s.left, 'новое слово', 'новых слова', 'новых слов');
  const wait = s.left % 10 === 1 && s.left % 100 !== 11 ? 'ждёт' : 'ждут';
  const tail = s.due ? ` И ${plural(s.due, 'слово ждёт', 'слова ждут', 'слов ждут')} повторения.` : '';

  if (s.started > 0) {
    return pick([
      { title: `Почти! Осталось ${s.left} из ${s.norm}`, body: `Начало положено — добери норму, пока слова свежие в голове.${tail}` },
      { title: `Ещё ${words} до нормы`, body: `Самое трудное — начать — уже позади. Пара минут, и день закрыт.${tail}` },
    ]);
  }
  if (s.streak >= 2) {
    const days = plural(s.streak, 'день', 'дня', 'дней');
    return pick([
      { title: `🔥 ${days} подряд — не дай серии прерваться`, body: `Сегодня занятий ещё не было. ${words} — и серия продолжится.${tail}` },
      { title: `Серия: ${days}. Сегодня — ${s.streak + 1}-й?`, body: `${words} ${wait}. Это минут пять, а привычка дороже любой порции.${tail}` },
      ...(s.best > s.streak ? [{ title: `До рекорда ${plural(s.best - s.streak, 'день', 'дня', 'дней')}`,
        body: `Рекорд — ${plural(s.best, 'день', 'дня', 'дней')} подряд. Сегодняшние ${words} приближают его.${tail}` }] : []),
    ]);
  }
  return pick([
    { title: 'გამარჯობა! 👋', body: `Новая порция готова: ${words}. Открой одну карточку — дальше пойдёт само.${tail}` },
    { title: `${words} на сегодня`, body: `Пять минут в день — и через месяц это ${s.norm * 30} слов в копилке.${tail}` },
    { title: 'Минутка грузинского?', body: `Сегодняшние ${words} ещё не взяты. Язык складывается из таких маленьких дней.${tail}` },
    s.streak === 1
      ? { title: 'Вчера было здорово 👏', body: `Сделай сегодня — и это уже серия из двух дней. ${words} ${wait}.${tail}` }
      : { title: 'Слова сами себя не выучат 🙂', body: `${words} ${wait}. Новая серия начинается с сегодняшнего дня.${tail}` },
  ]);
}

async function send(sub: Sub, msg: { title: string; body: string }) {
  try {
    await webpush.sendNotification(
      { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
      JSON.stringify({ ...msg, tag: `${sub.app}-reminder`, url: './' }),
      { TTL: 4 * 3600, urgency: 'normal' },
    );
    return 'sent';
  } catch (e: any) {
    // подписка умерла (приложение удалили, разрешение отозвали) — забываем её
    if (e?.statusCode === 404 || e?.statusCode === 410) {
      await db.from('push_subs').delete().eq('user_id', sub.user_id).eq('app', sub.app);
      return 'gone';
    }
    return `error ${e?.statusCode || ''} ${e?.body || e?.message || e}`.trim();
  }
}

async function progressOf(sub: Sub) {
  const { data } = await db.from('progress').select('data').eq('user_id', sub.user_id).eq('app', sub.app).maybeSingle();
  return data?.data || {};
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
  const { data: cfg, error } = await db.rpc('push_config');
  if (error) return json({ error: error.message }, 500);
  webpush.setVapidDetails(cfg.vapid_subject, cfg.vapid_public, cfg.vapid_private);
  const { data: allowedRows } = await db.rpc('push_allowed_users');
  const allowed = new Set((allowedRows || []).map((r: any) => `${r.user_id}/${r.app}`));

  // пробное — из приложения, только себе и только если разрешено
  if (req.headers.get('x-cron-secret') !== cfg.cron_secret) {
    const token = (req.headers.get('authorization') || '').replace(/^Bearer /, '');
    const { data: u } = await db.auth.getUser(token);
    if (!u?.user) return json({ error: 'нет входа' }, 401);
    const body = await req.json().catch(() => ({}));
    const app = body.app || 'kartuli';
    if (!allowed.has(`${u.user.id}/${app}`)) return json({ error: 'напоминания не разрешены' }, 403);
    const { data: sub } = await db.from('push_subs').select('*').eq('user_id', u.user.id).eq('app', app).maybeSingle();
    if (!sub) return json({ error: 'устройство не подписано' }, 404);
    const day = localNow(sub.tz).day;
    const s = summary(await progressOf(sub), day);
    if (!s.left) { s.left = s.norm; s.started = 0; }   // норма уже взята — покажем обычное напоминание
    return json({ result: await send(sub, message(s, day)) });
  }

  // по расписанию
  const { data: subs } = await db.from('push_subs').select('*').eq('enabled', true);
  const out: Record<string, string> = {};
  for (const sub of (subs || []) as Sub[]) {
    if (!allowed.has(`${sub.user_id}/${sub.app}`)) continue;
    const now = localNow(sub.tz);
    const [h, m] = sub.remind_at.split(':').map(Number);
    const at = h * 60 + m;
    if (sub.last_day === now.day || now.min < at || now.min >= at + WINDOW_MIN) continue;
    const s = summary(await progressOf(sub), now.day);
    const res = s.left ? await send(sub, message(s, now.day)) : 'норма выполнена';
    // ошибку доставки не отмечаем: следующий запуск попробует ещё раз
    if (res === 'sent' || !s.left) {
      await db.from('push_subs').update({ last_day: now.day, ...(res === 'sent' ? { last_sent_at: new Date().toISOString() } : {}) })
        .eq('user_id', sub.user_id).eq('app', sub.app);
    }
    out[sub.user_id.slice(0, 8)] = res;
  }
  return json(out);
});
