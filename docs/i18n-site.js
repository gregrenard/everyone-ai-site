// Shared language runtime for every page except Home (which embeds the same logic).
// Language source order: ?lang= → localStorage 'eai_lang' → browser → 'en'. Persisted on switch.
export const LANGS = [
  { code: 'en', name: 'English' }, { code: 'fr', name: 'Français' }, { code: 'es', name: 'Español' }, { code: 'de', name: 'Deutsch' },
  { code: 'nl', name: 'Nederlands' }, { code: 'it', name: 'Italiano' }, { code: 'pt', name: 'Português' }, { code: 'zh', name: '中文' }
];
const ok = l => LANGS.some(x => x.code === l);
let current = null;
export function currentLang() {
  if (current) return current;
  let l = null;
  try { const q = new URLSearchParams(location.search).get('lang'); if (q) l = q.toLowerCase().slice(0, 2); } catch (e) {}
  if (!ok(l)) { try { l = localStorage.getItem('eai_lang'); } catch (e) {} }
  if (!ok(l)) { try { l = (navigator.languages || [navigator.language]).map(x => (x || '').slice(0, 2).toLowerCase()).find(ok); } catch (e) {} }
  if (!ok(l)) l = 'en';
  current = l; applyDoc(l);
  return l;
}
function applyDoc(l) { try { document.documentElement.lang = l === 'zh' ? 'zh-Hans' : l; } catch (e) {} }
export function setLang(l) {
  if (!ok(l)) return;
  current = l; applyDoc(l);
  try { localStorage.setItem('eai_lang', l); } catch (e) {}
  try { window.dispatchEvent(new CustomEvent('eai:lang', { detail: l })); } catch (e) {}
}
// Deep merge: translated values override EN; anything missing falls back to EN.
export function merge(en, tr) {
  if (!tr) return en;
  if (Array.isArray(en)) return en.map((v, i) => merge(v, tr[i]));
  if (en && typeof en === 'object') { const o = {}; for (const k in en) o[k] = merge(en[k], tr[k]); return o; }
  return tr == null || tr === '' ? en : tr;
}
export function setMeta(meta) {
  if (!meta) return;
  try {
    if (meta.title) document.title = meta.title;
    const d = document.querySelector('meta[name="description"]'); if (d && meta.description) d.setAttribute('content', meta.description);
  } catch (e) {}
}
// Page helper: subscribes a DC to language changes and lazy-loads its translation module.
export function bindPage(cmp, loader, EN) {
  const load = l => {
    const done = dict => { const t = l === 'en' ? EN : merge(EN, dict && dict[l]); cmp.setState({ lang: l, t, dict }); setMeta(t.meta); };
    if (l === 'en') return done(cmp.state.dict);
    if (cmp.state.dict) return done(cmp.state.dict);
    loader().then(m => done(m.translations)).catch(() => done(null));
  };
  const on = e => load(e.detail);
  window.addEventListener('eai:lang', on);
  load(currentLang());
  return () => window.removeEventListener('eai:lang', on);
}
