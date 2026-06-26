/**
 * Shared header behaviors: live GitHub star counter.
 * Loaded by every page that includes the .header-github component.
 */
(function () {
  var REPO = 'ambicuity/course-computer-networks';
  var CACHE_KEY = 'gh:stars:' + REPO;
  var CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes

  function format(n) {
    if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return String(n);
  }

  function paint(n) {
    var els = document.querySelectorAll('.header-github .star-count, #starCount');
    for (var i = 0; i < els.length; i++) {
      els[i].textContent = format(n);
      els[i].removeAttribute('data-loading');
    }
  }

  function readCache() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (Date.now() - parsed.t > CACHE_TTL_MS) return null;
      return parsed.n;
    } catch (e) {
      return null;
    }
  }

  function writeCache(n) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ n: n, t: Date.now() }));
    } catch (e) {
      // localStorage may be disabled
    }
  }

  function load() {
    var cached = readCache();
    if (cached != null) {
      paint(cached);
      return;
    }
    if (location.hostname === '127.0.0.1' || location.hostname === 'localhost' || location.protocol === 'file:') {
      var els = document.querySelectorAll('.header-github .star-count, #starCount');
      for (var i = 0; i < els.length; i++) {
        els[i].textContent = 'GitHub';
        els[i].removeAttribute('data-loading');
      }
      return;
    }

    fetch('https://api.github.com/repos/' + REPO, {
      headers: { Accept: 'application/vnd.github+json' },
    })
      .then(function (r) {
        if (!r.ok) throw new Error('gh ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var n = data.stargazers_count;
        if (typeof n !== 'number') return;
        writeCache(n);
        paint(n);
      })
      .catch(function () {
        // Leave the placeholder; the link still works.
      });
  }

  /* Build a hamburger menu on small screens so the nav links stay reachable.
     Injected here (shared) so no per-page HTML edits are needed. */
  function buildMobileNav() {
    var header = document.querySelector('.site-header');
    var inner = header && header.querySelector('.header-inner');
    var nav = inner && inner.querySelector('.header-nav');
    if (!header || !inner || !nav) return;
    if (inner.querySelector('.nav-toggle')) return;

    var links = nav.querySelectorAll('a:not(.header-github)');
    if (!links.length) return;

    var menu = document.createElement('div');
    menu.className = 'mobile-menu';
    for (var i = 0; i < links.length; i++) {
      menu.appendChild(links[i].cloneNode(true));
    }

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'nav-toggle';
    toggle.setAttribute('aria-label', 'Toggle navigation menu');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<span></span><span></span><span></span>';

    function setOpen(open) {
      header.classList.toggle('nav-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!header.classList.contains('nav-open'));
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('click', function (e) {
      if (!header.classList.contains('nav-open')) return;
      if (!menu.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setOpen(false);
    });

    var themeBtn = inner.querySelector('.theme-toggle');
    if (themeBtn) inner.insertBefore(toggle, themeBtn);
    else inner.appendChild(toggle);
    header.appendChild(menu);
  }

  function init() {
    load();
    buildMobileNav();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
