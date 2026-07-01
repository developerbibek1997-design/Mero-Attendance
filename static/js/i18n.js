/**
 * Mero Attendance — client-side i18n engine
 * Languages: en (default), ne, hi, ar, es, fr, pt, zh, ja, ko, id
 * Uses data-i18n / data-i18n-html / data-i18n-placeholder attributes.
 * Language persists via localStorage + cookie.
 * Arabic triggers dir="rtl" on <html>.
 */
(function () {
  'use strict';

  var SUPPORTED = ['en','ne','hi','ar','es','fr','pt','zh','ja','ko','id'];
  var RTL       = ['ar'];

  var LANG_LABELS = {
    en: { short:'EN',  label:'English',          flag:'🇺🇸' },
    ne: { short:'NE',  label:'नेपाली',           flag:'🇳🇵' },
    hi: { short:'HI',  label:'हिन्दी',           flag:'🇮🇳' },
    ar: { short:'AR',  label:'العربية',          flag:'🇸🇦' },
    es: { short:'ES',  label:'Español',          flag:'🇪🇸' },
    fr: { short:'FR',  label:'Français',         flag:'🇫🇷' },
    pt: { short:'PT',  label:'Português',        flag:'🇧🇷' },
    zh: { short:'中',  label:'中文',              flag:'🇨🇳' },
    ja: { short:'日',  label:'日本語',            flag:'🇯🇵' },
    ko: { short:'한',  label:'한국어',            flag:'🇰🇷' },
    id: { short:'ID',  label:'Bahasa Indonesia', flag:'🇮🇩' }
  };

  var currentLang  = 'en';
  var translations = {};

  /* ── persistence ─────────────────────────────────── */
  function saveLang(lang) {
    try { localStorage.setItem('ma_lang', lang); } catch(e){}
    document.cookie = 'ma_lang=' + lang + ';path=/;max-age=31536000;SameSite=Lax';
  }

  function getSavedLang() {
    try {
      var ls = localStorage.getItem('ma_lang');
      if (ls && SUPPORTED.indexOf(ls) !== -1) return ls;
    } catch(e){}
    var m = document.cookie.match(/(?:^|;\s*)ma_lang=([a-z]+)/);
    if (m && SUPPORTED.indexOf(m[1]) !== -1) return m[1];
    var bl = (navigator.language || 'en').split('-')[0];
    if (SUPPORTED.indexOf(bl) !== -1) return bl;
    return 'en';
  }

  /* ── DOM application ─────────────────────────────── */
  function applyToRoot(root) {
    root = root || document;

    /* plain text */
    root.querySelectorAll('[data-i18n]').forEach(function(el) {
      var key = el.getAttribute('data-i18n');
      if (translations[key] !== undefined) el.textContent = translations[key];
    });

    /* inner HTML (for lists, bold snippets) */
    root.querySelectorAll('[data-i18n-html]').forEach(function(el) {
      var key = el.getAttribute('data-i18n-html');
      if (translations[key] !== undefined) el.innerHTML = translations[key];
    });

    /* placeholder */
    root.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
      var key = el.getAttribute('data-i18n-placeholder');
      if (translations[key] !== undefined) el.placeholder = translations[key];
    });

    /* aria-label */
    root.querySelectorAll('[data-i18n-aria]').forEach(function(el) {
      var key = el.getAttribute('data-i18n-aria');
      if (translations[key] !== undefined) el.setAttribute('aria-label', translations[key]);
    });
  }

  function applyDirLang(lang) {
    var html = document.documentElement;
    html.setAttribute('lang', lang);
    if (RTL.indexOf(lang) !== -1) {
      html.setAttribute('dir', 'rtl');
      document.body && document.body.classList.add('ma-rtl');
    } else {
      html.setAttribute('dir', 'ltr');
      document.body && document.body.classList.remove('ma-rtl');
    }
  }

  /* ── load + apply ────────────────────────────────── */
  function applyLanguage(lang) {
    currentLang = lang;
    applyDirLang(lang);
    applyToRoot(document);
    updateSwitcherUI(lang);
  }

  function loadAndApply(lang) {
    if (lang === 'en') {
      translations = {};
      applyLanguage('en');
      return;
    }
    var base = (window.MA_STATIC || '/static/') + 'i18n/' + lang + '.json';
    var url  = base + '?v=2';
    fetch(url)
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(data) {
        translations = data;
        applyLanguage(lang);
      })
      .catch(function(err) {
        console.warn('[i18n] Could not load', lang, err);
        translations = {};
        applyLanguage('en');
      });
  }

  /* ── public API: switch language ────────────────── */
  function setLanguage(lang) {
    if (SUPPORTED.indexOf(lang) === -1) return;
    saveLang(lang);
    loadAndApply(lang);
  }

  /* ── switcher UI ─────────────────────────────────── */
  function updateSwitcherUI(lang) {
    var info = LANG_LABELS[lang] || LANG_LABELS['en'];

    /* update all current-language indicators */
    document.querySelectorAll('.ma-lang-current').forEach(function(el) {
      el.textContent = info.short;
    });

    /* mark active item */
    document.querySelectorAll('[data-lang]').forEach(function(el) {
      var active = el.getAttribute('data-lang') === lang;
      el.classList.toggle('ma-lang-active', active);
    });
  }

  /* ── init ────────────────────────────────────────── */
  function init() {
    var lang = getSavedLang();
    loadAndApply(lang);
  }

  /* run */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* re-apply after HTMX boost navigation */
  document.addEventListener('htmx:afterBoostSwap', function() {
    applyDirLang(currentLang);
    if (currentLang !== 'en') applyToRoot(document);
    updateSwitcherUI(currentLang);
  });

  /* close dropdown on outside click */
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.ma-lang-wrap')) {
      document.querySelectorAll('.ma-lang-menu').forEach(function(m) {
        m.classList.remove('ma-lang-open');
      });
    }
  });

  /* expose globally */
  window.MA_I18N = {
    setLanguage: setLanguage,
    getCurrentLang: function() { return currentLang; },
    getLangLabels: function() { return LANG_LABELS; }
  };
})();
