#!/usr/bin/env node
// Browser audit of the built or published site. Needs Google Chrome and Node 22+, nothing else.
//   node audit.mjs <baseUrl> [--pages slug,slug] [--json out.json]
// Serve a local build under the same path as production first (see SKILL.md).
// Exit code 1 if any FAIL. WARN lines need a human decision and do not fail the run.
// Read-only: it never submits a form, because a submit opens the mail app of this machine.
import { spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const here = path.dirname(new URL(import.meta.url).pathname);
const argv = process.argv.slice(2);
const base = argv[0].replace(/\/?$/, '/');
const opt = n => { const i = argv.indexOf(n); return i > 0 ? argv[i + 1] : null; };
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const VIEWPORTS = [[1280, 844, 'en'], [390, 844, 'fr'], [360, 640, 'de']];
const GENERIC = /^(learn more|read more|click here|more|here)$/i;
const CLS_MAX = 0.1, LCP_MAX = 2500;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const pages = JSON.parse(fs.readFileSync(path.join(here, '../sync-site/pages.json'), 'utf8')).pages.map(p => p.slug)
  .filter(s => !opt('--pages') || opt('--pages').split(',').includes(s));
const url = (slug, q = '') => base + (slug === 'index' ? '' : slug + '/') + q;

const fails = [], warns = [];
const FAIL = m => { fails.push(m); console.log('FAIL ' + m); };
const WARN = m => { if (!warns.includes(m)) { warns.push(m); console.log('WARN ' + m); } };

async function browser(port) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'eai-audit-'));
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, 'about:blank'], { stdio: 'ignore' });
  let ws, id = 0;
  const pending = new Map(), errors = [];
  for (let i = 0; i < 60; i++) {
    try {
      const t = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      ws = new WebSocket(t.find(x => x.type === 'page').webSocketDebuggerUrl);
      await new Promise((a, b) => { ws.onopen = a; ws.onerror = b; });
      break;
    } catch (e) { await sleep(250); }
  }
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === 'Network.responseReceived' && m.params.response.status >= 400) errors.push(m.params.response.status + ' ' + m.params.response.url);
    if (m.method === 'Runtime.exceptionThrown') errors.push('JS ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).slice(0, 120));
  };
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async expression => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.result.value;
  for (const d of ['Page', 'Network', 'Runtime']) await send(d + '.enable');
  return { send, ev, errors, close: () => { proc.kill(); try { fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 }); } catch (e) { /* Chrome still closing */ } } };
}

const PAGE = `(async () => {
  const root = document.getElementById('dc-root'), vw = innerWidth;
  document.documentElement.style.scrollBehavior = 'auto';
  for (let y = 0; y < document.documentElement.scrollHeight; y += 700) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
  scrollTo(0, Math.round(document.documentElement.scrollHeight / 2));
  await new Promise(r => setTimeout(r, 400));
  const header = root.querySelector('header'), hr = header.getBoundingClientRect();
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const imgs = [...root.querySelectorAll('img')].filter(vis);
  const lowres = imgs.filter(i => i.naturalWidth && i.getBoundingClientRect().width - parseFloat(getComputedStyle(i).paddingLeft) - parseFloat(getComputedStyle(i).paddingRight) > i.naturalWidth + 1 && getComputedStyle(i).objectFit !== 'cover').map(i => i.getAttribute('src'));
  const distorted = imgs.filter(i => { if (!i.naturalWidth || getComputedStyle(i).objectFit !== 'fill') return false; const c = getComputedStyle(i), r = i.getBoundingClientRect(); const w = r.width - parseFloat(c.paddingLeft) - parseFloat(c.paddingRight), h = r.height - parseFloat(c.paddingTop) - parseFloat(c.paddingBottom); return Math.abs(w / h - i.naturalWidth / i.naturalHeight) / (i.naturalWidth / i.naturalHeight) > 0.05; }).map(i => i.getAttribute('src'));
  return JSON.stringify({
    title: document.title, lang: document.documentElement.lang,
    docW: document.documentElement.scrollWidth, vw,
    h1: [...root.querySelectorAll('h1')].filter(vis).length,
    stickyTop: Math.round(hr.top), mirror: !!document.getElementById('dc-prerender'),
    broken: [...root.querySelectorAll('img')].filter(i => i.complete && !i.naturalWidth && i.getAttribute('src')).map(i => i.getAttribute('src')),
    noAlt: imgs.filter(i => !i.hasAttribute('alt')).map(i => i.getAttribute('src')), lowres, distorted,
    emptySlots: [...root.querySelectorAll('image-slot')].filter(s => !s.getAttribute('src')).length,
    leftovers: (root.innerText.match(/\\{\\{[^}]*\\}\\}/g) || []).slice(0, 3),
    small: [...root.querySelectorAll('*')].filter(e => vis(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim().length > 1) && parseFloat(getComputedStyle(e).fontSize) < 12).length,
    links: [...root.querySelectorAll('a')].map(a => ({ raw: a.getAttribute('href'), href: a.href, text: a.textContent.trim(), aria: a.getAttribute('aria-label'), vis: vis(a), img: !!a.querySelector('img,svg') })),
    ids: [...document.querySelectorAll('[id]')].map(e => e.id)
  });
})()`;

const b = await browser(9555);
const internal = new Map(), external = new Set();
for (const [w, h, lang] of VIEWPORTS) {
  await b.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 2, mobile: w < 800 });
  for (const slug of pages) {
    b.errors.length = 0;
    await b.send('Page.navigate', { url: url(slug, '?lang=' + lang) });
    await sleep(3200);
    let p;
    try { p = JSON.parse(await b.ev(PAGE)); } catch (e) { FAIL(`${slug} @${w}: page did not render`); continue; }
    const at = `${slug} @${w}/${lang}`;
    if (p.docW > p.vw) FAIL(`${at}: horizontal overflow ${p.docW} > ${p.vw}`);
    if (p.h1 !== 1) FAIL(`${at}: ${p.h1} visible H1`);
    if (p.stickyTop !== 0) FAIL(`${at}: menu not sticky (top ${p.stickyTop})`);
    if (p.mirror) FAIL(`${at}: pre-render mirror still present`);
    if (p.lang !== lang) FAIL(`${at}: <html lang> is ${p.lang}`);
    if (p.emptySlots) FAIL(`${at}: ${p.emptySlots} empty image slots`);
    if (p.small) FAIL(`${at}: ${p.small} text elements under 12 px`);
    if (!p.title) FAIL(`${at}: empty title`);
    for (const s of p.broken) FAIL(`${at}: broken image ${s}`);
    for (const s of p.noAlt) FAIL(`${at}: image without alt ${s}`);
    for (const s of p.leftovers) FAIL(`${at}: unresolved template ${s}`);
    for (const e of b.errors) FAIL(`${at}: console ${e}`);
    for (const s of p.distorted) WARN(`distorted image: ${s} on ${slug}`);
    for (const s of p.lowres) WARN(`image shown larger than its file: ${s} on ${slug}`);
    for (const l of p.links) {
      if (!l.raw) { FAIL(`${at}: link without href "${l.text}"`); continue; }
      if (l.vis && !l.text && !l.aria && !l.img) FAIL(`${at}: link without a name ${l.raw}`);
      if (lang === 'en' && GENERIC.test(l.text)) WARN(`generic button label "${l.text}" on ${slug}`);
      if (l.raw.startsWith('#')) { if (l.raw.length > 1 && l.raw !== '#top' && !p.ids.includes(l.raw.slice(1))) FAIL(`${at}: dead anchor ${l.raw}`); continue; }
      if (/^(mailto|tel):/.test(l.raw)) continue;
      if (l.href.startsWith(base)) internal.set(l.href.split('#')[0].split('?')[0], slug);
      else if (/^https?:/.test(l.href)) external.add(l.href);
    }
    console.log(`ok   ${at}`);
  }
}
for (const [u, from] of internal) {
  const r = await fetch(u).catch(() => null);
  if (!r || r.status >= 400) FAIL(`dead internal link ${u} (from ${from})`);
}
for (const u of external) if (/^https:\/\/(www\.)?everyone\.ai\//.test(u)) WARN(`link depends on the old site: ${u}`);

// Layout shift and LCP on a throttled mobile, with an empty cache, as PageSpeed loads a page.
const m = await browser(9556);
await m.send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__cls=0;window.__lcp=0;new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)__cls+=e.value}).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>{__lcp=l.getEntries().pop().startTime}).observe({type:'largest-contentful-paint',buffered:true});` });
await m.send('Network.setCacheDisabled', { cacheDisabled: true });
await m.send('Emulation.setDeviceMetricsOverride', { width: 412, height: 823, deviceScaleFactor: 2, mobile: true });
await m.send('Emulation.setCPUThrottlingRate', { rate: 4 });
await m.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: 204800, uploadThroughput: 90000 });
for (const slug of pages.filter(s => ['index', 'donate', 'contact', 'newsroom'].includes(s))) {
  await m.send('Page.navigate', { url: url(slug) });
  await sleep(25000);
  const [cls, lcp] = JSON.parse(await m.ev('JSON.stringify([__cls,__lcp])'));
  console.log(`perf ${slug}: CLS ${cls.toFixed(3)}, LCP ${Math.round(lcp)} ms`);
  if (cls > CLS_MAX) FAIL(`${slug}: CLS ${cls.toFixed(3)} > ${CLS_MAX}`);
  if (lcp > LCP_MAX) WARN(`${slug}: LCP ${Math.round(lcp)} ms > ${LCP_MAX} ms in this test (confirm on PageSpeed)`);
}
b.close(); m.close();
if (opt('--json')) fs.writeFileSync(opt('--json'), JSON.stringify({ fails, warns, external: [...external] }, null, 1));
console.log(`\n${pages.length} pages, ${VIEWPORTS.length} viewports, ${internal.size} internal URLs, ${external.size} external URLs: ${fails.length} FAIL, ${warns.length} WARN`);
process.exit(fails.length ? 1 : 0);
