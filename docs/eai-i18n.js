// Deploy-only translation overlay (published as eai-i18n.js by build.py).
//
// The Design project translates only Home and the shared header; every other page
// renders English whatever language the switcher shows. This overlay translates the
// rendered text in place from i18n/<lang>.json (English string -> translation).
//
// It follows <html lang>, which both Home and i18n-site.js set, so it never has its
// own idea of the current language. Text that Design already translated is not
// English any more, matches no key, and is left alone: the overlay goes inert on a
// page as soon as that page is translated in Design.
//
// Unit of translation: the text nodes that share the same nearest non-inline
// ancestor, in document order. A sentence with inline markup ("must be <b>secure</b>,
// protecting") is one unit of three segments; the key and the translation are the
// segments joined by "\n", so word order can change across segments while the DOM
// structure React owns is never touched (only nodeValue is written).
//
// ?eai_extract=1 dumps the page's units as JSON into <script id="eai-i18n-units">
// for extract-i18n.py (same code path as the runtime, so keys always agree).
(function () {
  var SEP = "\n";
  var SKIP = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, "IMAGE-SLOT": 1, CODE: 1, TEXTAREA: 1, HEADER: 1 };
  var ATTRS = ["placeholder", "aria-label", "title", "alt"];
  var base = document.currentScript.src.replace(/[^/]*$/, "");
  var EXTRACT = /[?&]eai_extract=1/.test(location.search);
  var texts = new WeakMap();  // text node -> { en, shown }
  var attrs = new WeakMap();  // element   -> { attr: { en, shown } }
  var head = {};              // "title" / "description" -> { en, shown }
  var cache = {}, dict = null, lang = "en", timer = null;

  function norm(s) { return s.replace(/\s+/g, " ").trim(); }
  function worth(s) {
    return /[A-Za-zÀ-ɏ]{2}/.test(s) && !/^(https?:\/\/|mailto:|www\.)\S+$/i.test(s) && !/^\S+@\S+\.\S+$/.test(s);
  }
  // English original of a value we may have overwritten: if what is on screen is not
  // what we last wrote, the app re-rendered it and that is the new original.
  function track(rec, now) {
    if (!rec || rec.shown !== now) rec = { en: now, shown: now };
    return rec;
  }
  function skipped(el, root) {
    for (; el && el !== root; el = el.parentNode) {
      if (SKIP[el.nodeName] || (el.getAttribute && el.getAttribute("translate") === "no")) return true;
    }
    return false;
  }
  function host(node, root) {
    var el = node.parentNode;
    while (el !== root && el.parentNode) {
      var d = getComputedStyle(el).display;
      if (d !== "inline" && d !== "contents") break;
      el = el.parentNode;
    }
    return el;
  }
  function split(en, tr) {
    var lead = en.match(/^\s*/)[0], trail = en.match(/\s*$/)[0];
    return lead + tr + (en.length > lead.length ? trail : "");
  }
  function lookup(key) { return dict && Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : null; }

  function pass(root, seen) {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), n, groups = new Map(), order = [];
    while ((n = w.nextNode())) {
      var rec = track(texts.get(n), n.nodeValue);
      texts.set(n, rec);
      if (!norm(rec.en) || skipped(n.parentNode, root)) continue;
      var h = host(n, root), g = groups.get(h);
      if (!g) { g = []; groups.set(h, g); order.push(g); }
      g.push(n);
    }
    order.forEach(function (g) {
      var segs = g.map(function (x) { return norm(texts.get(x).en); });
      if (!segs.some(worth)) return;
      var key = segs.join(SEP), tr = lookup(key), parts = tr ? tr.split(SEP) : null;
      if (parts && parts.length !== segs.length) parts = null;
      if (seen) seen.push({ k: key, ok: !!parts });
      g.forEach(function (x, i) {
        var rec = texts.get(x), one = parts ? parts[i] : lookup(segs[i]);
        var want = one != null ? split(rec.en, one) : rec.en;
        if (x.nodeValue !== want) { x.nodeValue = want; }
        rec.shown = want;
      });
    });
    var els = root.querySelectorAll("[" + ATTRS.join("],[") + "]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (skipped(el, root)) continue;
      var recs = attrs.get(el) || {};
      attrs.set(el, recs);
      ATTRS.forEach(function (a) {
        if (!el.hasAttribute(a)) return;
        var rec = recs[a] = track(recs[a], el.getAttribute(a)), key = norm(rec.en);
        if (!worth(key)) return;
        var tr = lookup(key), want = tr != null ? tr : rec.en;
        if (seen) seen.push({ k: key, ok: tr != null });
        if (el.getAttribute(a) !== want) el.setAttribute(a, want);
        rec.shown = want;
      });
    }
  }
  function headPass(seen) {
    var m = document.querySelector('meta[name="description"]');
    [["title", function () { return document.title; }, function (v) { document.title = v; }],
     ["description", function () { return m ? m.getAttribute("content") || "" : ""; }, function (v) { if (m) m.setAttribute("content", v); }]
    ].forEach(function (f) {
      var rec = head[f[0]] = track(head[f[0]], f[1]()), key = norm(rec.en);
      if (!key) return;
      var tr = lookup(key), want = tr != null ? tr : rec.en;
      if (seen) seen.push({ k: key, ok: tr != null });
      if (f[1]() !== want) f[2](want);
      rec.shown = want;
    });
  }
  function apply(seen) {
    timer = null;
    var root = document.getElementById("dc-root");
    if (!root) return;
    pass(root, seen);
    headPass(seen);
  }
  function schedule() { if (timer == null) timer = setTimeout(apply, 60); }
  function current() {
    var l = (document.documentElement.lang || "en").toLowerCase().slice(0, 2);
    return /^(fr|es|de|nl|it|pt|zh)$/.test(l) ? l : "en";
  }
  function sync() {
    var l = current();
    if (l === lang) return;
    lang = l;
    if (l === "en") { dict = null; schedule(); return; }
    (cache[l] || (cache[l] = fetch(base + "i18n/" + l + ".json").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; })))
      .then(function (d) { if (lang === l) { dict = d; schedule(); } });
  }

  new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  function start() {
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, characterData: true });
    sync();
    schedule();
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);

  if (EXTRACT) {
    window.addEventListener("load", function () {
      setTimeout(function () {
        var seen = [];
        apply(seen);
        var s = document.createElement("script");
        s.type = "application/json";
        s.id = "eai-i18n-units";
        s.textContent = JSON.stringify({ lang: lang, units: seen }).replace(/</g, "\\u003c");
        document.body.appendChild(s);
      }, 6000);
    });
  }
})();
