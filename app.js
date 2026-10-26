/* ============================================================
   AGENTIVA — app.js
   i18n switching, theme toggle, nav drawer, FAQ accordion,
   chat demo animation, sticky header behaviour, client login.
   Theme/lang state is in-memory only (sandboxed iframe previews
   block storage access). The login/auth modal is the one
   exception — it needs localStorage to persist a Supabase
   session, matching the live site's client portal auth.
   ============================================================ */
(function () {
  'use strict';

  /* --------------------------------------------------------
     0. Config — REPLACE before going live
     -------------------------------------------------------- */
  var WHATSAPP_NUMBER = '5491156090300'; // Agentiva WhatsApp Business number
  var WHATSAPP_MESSAGE = {
    es: 'Hola! Quiero agendar un diagnóstico gratis para automatizar la atención por WhatsApp de mi negocio.',
  };

  // Spanish-only since 2026-10-22 (.com.ar targets Argentina; Italy gets its own brand)
  var SUPPORTED_LANGS = ['es'];
  var currentLang = 'es';

  function buildWaLink(lang) {
    var text = encodeURIComponent(WHATSAPP_MESSAGE[lang] || WHATSAPP_MESSAGE.es);
    return 'https://wa.me/' + WHATSAPP_NUMBER + '?text=' + text;
  }

  function updateWhatsappLinks() {
    var links = document.querySelectorAll('.cta-whatsapp, #cta-nav');
    var href = buildWaLink(currentLang);
    links.forEach(function (a) {
      a.setAttribute('href', href);
    });
  }

  /* --------------------------------------------------------
     1. i18n
     -------------------------------------------------------- */
  function applyLang(lang) {
    if (SUPPORTED_LANGS.indexOf(lang) === -1) lang = 'es';
    currentLang = lang;
    var dict = window.AGENTIVA_I18N[lang] || window.AGENTIVA_I18N.es;

    document.documentElement.setAttribute('lang', 'es-AR');

    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      if (dict[key]) el.textContent = dict[key];
    });

    document.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      var spec = el.getAttribute('data-i18n-attr'); // "content:meta.description"
      var parts = spec.split(':');
      var attr = parts[0];
      var key = parts[1];
      if (dict[key]) el.setAttribute(attr, dict[key]);
    });

    if (dict['meta.title']) document.title = dict['meta.title'];

    updateWhatsappLinks();
  }

  /* --------------------------------------------------------
     2. Theme toggle (light/dark) — in-memory only,
        default from prefers-color-scheme
     -------------------------------------------------------- */
  function initTheme() {
    var root = document.documentElement;
    var prefersDark =
      window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    var theme = prefersDark ? 'dark' : 'light';
    root.setAttribute('data-theme', theme);

    var toggles = document.querySelectorAll('.theme-toggle');
    if (!toggles.length) return;
    toggles.forEach(function (toggle) {
      toggle.addEventListener('click', function () {
        theme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', theme);
      });
    });
  }

  /* --------------------------------------------------------
     3. Mobile nav drawer
     -------------------------------------------------------- */
  function initNavDrawer() {
    var toggle = document.getElementById('nav-toggle');
    var drawer = document.getElementById('mobile-drawer');
    if (!toggle || !drawer) return;

    function closeDrawer() {
      drawer.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function () {
      var isOpen = drawer.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      toggle.classList.toggle('is-open', isOpen);
    });

    drawer.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', closeDrawer);
    });
  }

  /* --------------------------------------------------------
     4. FAQ accordion
     -------------------------------------------------------- */
  function initFaq() {
    var itemEls = document.querySelectorAll('.faq-item');
    var entries = [];

    itemEls.forEach(function (item) {
      var question = item.querySelector('.faq-question');
      var answer = item.querySelector('.faq-answer');
      if (!question || !answer) return;

      var entry = {
        item: item,
        answer: answer,
        setOpen: function (open) {
          item.setAttribute('data-open', open ? 'true' : 'false');
          if (open) {
            answer.style.height = answer.scrollHeight + 'px';
          } else {
            answer.style.height = '0px';
          }
        },
      };
      entries.push(entry);

      // initial state
      entry.setOpen(item.getAttribute('data-open') === 'true');

      question.addEventListener('click', function () {
        var willOpen = item.getAttribute('data-open') !== 'true';
        entries.forEach(function (other) {
          if (other.item !== item) other.setOpen(false);
        });
        entry.setOpen(willOpen);
      });
    });

    // re-measure open answers on resize (font reflow)
    window.addEventListener('resize', function () {
      entries.forEach(function (entry) {
        if (entry.item.getAttribute('data-open') === 'true') {
          entry.answer.style.height = 'auto';
          var h = entry.answer.scrollHeight;
          entry.answer.style.height = h + 'px';
        }
      });
    });
  }

  /* --------------------------------------------------------
     5. Scroll reveal
     -------------------------------------------------------- */
  function initReveal() {
    var els = document.querySelectorAll('[data-reveal]');
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) {
        el.classList.add('is-visible');
      });
      return;
    }
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -60px 0px' }
    );
    els.forEach(function (el) {
      observer.observe(el);
    });
  }

  /* --------------------------------------------------------
     6. Chat demo animation (sequential bubble fade-in)
     -------------------------------------------------------- */
  function initChatDemo() {
    var phone = document.querySelector('.phone-frame');
    var body = document.getElementById('chat-body');
    if (!phone || !body) return;

    var bubbles = Array.prototype.slice.call(body.querySelectorAll('.chat-bubble'));
    var typing = body.querySelector('.chat-typing');
    var played = false;

    function playSequence() {
      if (played) return;
      played = true;
      var delay = 300;
      var step = 850;

      bubbles.forEach(function (bubble, i) {
        var showTyping = i > 0 && i < bubbles.length; // brief typing pulse before each reply after the first
        var thisDelay = delay + i * step;

        if (showTyping && typing) {
          setTimeout(function () {
            typing.classList.add('is-visible');
          }, thisDelay - 260);
          setTimeout(function () {
            typing.classList.remove('is-visible');
          }, thisDelay + 40);
        }

        setTimeout(function () {
          bubble.classList.add('is-visible');
          body.scrollTop = body.scrollHeight;
        }, thisDelay);
      });
    }

    if (!('IntersectionObserver' in window)) {
      playSequence();
      return;
    }
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            playSequence();
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.35 }
    );
    observer.observe(phone);
  }

  /* --------------------------------------------------------
     7. Case study video modal
     Each .case-video button has a data-embed attribute.
     Empty data-embed = "coming soon" placeholder (no-op on click).
     Once a real YouTube/Vimeo embed URL is set, clicking opens
     the video in a lightbox and autoplays it.
     -------------------------------------------------------- */
  function initCaseVideos() {
    var modal = document.getElementById('video-modal');
    var frameWrap = document.getElementById('video-modal-frame');
    if (!modal || !frameWrap) return;

    function openModal(embedUrl) {
      if (!embedUrl) return;
      var iframe = document.createElement('iframe');
      iframe.src = embedUrl;
      iframe.title = 'Video testimonial';
      iframe.setAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
      iframe.setAttribute('allowfullscreen', '');
      iframe.setAttribute('frameborder', '0');
      frameWrap.innerHTML = '';
      frameWrap.appendChild(iframe);
      modal.hidden = false;
      document.body.classList.add('modal-open');
    }

    function closeModal() {
      modal.hidden = true;
      frameWrap.innerHTML = ''; // stop playback
      document.body.classList.remove('modal-open');
    }

    document.querySelectorAll('.case-video').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openModal(btn.getAttribute('data-embed'));
      });
    });

    modal.querySelectorAll('[data-close-modal]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !modal.hidden) closeModal();
    });
  }

  /* --------------------------------------------------------
     8. Login / auth modal (direct Supabase REST, no library)
     -------------------------------------------------------- */
  var _SB_URL = 'https://cyczjwnqrzxbngiqhzcj.supabase.co';
  var _SB_KEY =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5Y3pqd25xcnp4Ym5naXFoemNqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg1MjAwODAsImV4cCI6MjA5NDA5NjA4MH0.udWSMR11I7qayYnML1qxoukYK719QospuEZFKd-YZxE';
  var PORTAL_URL = '/portal/';
  var _SESS_KEY = 'agentiva_portal_v1';
  var _MEMBER_DOMAIN = 'team.agentiva.com.ar';

  // Restaurant platform clients — authenticated against platform Supabase too, still redirected to PORTAL_URL
  var _PLATFORM_SB_URL = 'https://etetlzcsqucujqjkzsvm.supabase.co';
  var _PLATFORM_SB_KEY =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0ZXRsemNzcXVjdWpxamt6c3ZtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2OTU3MzUsImV4cCI6MjA5NDI3MTczNX0.KMo40WJKxsLMu7OK5ksblxSkg61gTZLjpA4DIJOMJ8c';
  var _PLATFORM_SESS = 'restaurant_platform_v1';
  var _RESTAURANT_EMAILS = new Set(['campasosrl@gmail.com', 'cofi@mail.com']);

  function _getSession() {
    try {
      var s = JSON.parse(localStorage.getItem(_SESS_KEY));
      if (!s || !s.access_token) return null;
      if (s.expires_at && s.expires_at < Math.floor(Date.now() / 1000)) {
        localStorage.removeItem(_SESS_KEY);
        return null;
      }
      return s;
    } catch (err) {
      return null;
    }
  }

  function updateNavAuth() {
    var session = _getSession();
    var dict = window.AGENTIVA_I18N[currentLang] || window.AGENTIVA_I18N.es;
    document.querySelectorAll('#nav-signin').forEach(function (el) {
      if (session) {
        var nombre = (session.user && (session.user.user_metadata && session.user.user_metadata.nombre || session.user.email)) || 'Mi cuenta';
        el.innerHTML =
          '<span class="nav-user"><a href="' + PORTAL_URL + '" class="nav-user-name">' + nombre + '</a>' +
          '<button type="button" class="nav-logout" data-auth-logout>' + (dict['auth.logoutLabel'] || 'Salir') + '</button></span>';
      } else {
        el.innerHTML =
          '<a href="#" class="nav-signin-link" data-open-auth data-i18n="auth.navSignin">' + (dict['auth.navSignin'] || 'Ingresar') + '</a>';
      }
    });
  }

  function doLogout() {
    var s = _getSession();
    if (s) {
      fetch(_SB_URL + '/auth/v1/logout', {
        method: 'POST',
        headers: { apikey: _SB_KEY, Authorization: 'Bearer ' + s.access_token },
      }).catch(function () {});
    }
    localStorage.removeItem(_SESS_KEY);
    updateNavAuth();
  }

  function openAuthModal() {
    var modal = document.getElementById('auth-modal');
    if (!modal) return;
    var drawer = document.getElementById('mobile-drawer');
    var toggle = document.getElementById('nav-toggle');
    if (drawer) drawer.classList.remove('is-open');
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
      toggle.classList.remove('is-open');
    }
    modal.hidden = false;
    document.body.classList.add('modal-open');
    var emailInput = document.getElementById('login-email');
    if (emailInput) emailInput.focus();
  }

  function closeAuthModal() {
    var modal = document.getElementById('auth-modal');
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove('modal-open');
  }

  function handleLogin(e) {
    e.preventDefault();
    var email = document.getElementById('login-email').value.trim().toLowerCase();
    // Team members log in with a bare username → synthetic email (see api/team.py)
    if (email && email.indexOf('@') === -1) email = email + '@' + _MEMBER_DOMAIN;
    var pass = document.getElementById('login-pass').value;
    var errEl = document.getElementById('login-error');
    var dict = window.AGENTIVA_I18N[currentLang] || window.AGENTIVA_I18N.es;
    var fallback = dict['auth.errorFallback'] || 'Email o contraseña incorrectos.';
    errEl.textContent = '';

    // Restaurant platform clients → authenticate both platform + portal, redirect to PORTAL_URL
    if (_RESTAURANT_EMAILS.has(email)) {
      fetch(_PLATFORM_SB_URL + '/auth/v1/token?grant_type=password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', apikey: _PLATFORM_SB_KEY },
        body: JSON.stringify({ email: email, password: pass }),
      })
        .then(function (platRes) {
          return platRes.json().then(function (platData) {
            if (!platRes.ok) throw new Error(platData.error_description || fallback);
            localStorage.setItem(
              _PLATFORM_SESS,
              JSON.stringify({ access_token: platData.access_token, user_id: platData.user.id, email: platData.user.email })
            );
            return fetch(_SB_URL + '/auth/v1/token?grant_type=password', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', apikey: _SB_KEY },
              body: JSON.stringify({ email: email, password: pass }),
            });
          });
        })
        .then(function (portalRes) {
          return portalRes.json().then(function (portalData) {
            if (portalRes.ok) localStorage.setItem(_SESS_KEY, JSON.stringify(portalData));
          });
        })
        .then(function () {
          closeAuthModal();
          window.location.href = PORTAL_URL;
        })
        .catch(function (err) {
          errEl.textContent = err.message || fallback;
        });
      return;
    }

    // Standard portal auth
    fetch(_SB_URL + '/auth/v1/token?grant_type=password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: _SB_KEY },
      body: JSON.stringify({ email: email, password: pass }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.error_description || fallback);
          localStorage.setItem(_SESS_KEY, JSON.stringify(data));
        });
      })
      .then(function () {
        closeAuthModal();
        window.location.href = PORTAL_URL;
      })
      .catch(function (err) {
        errEl.textContent = err.message || fallback;
      });
  }

  function initAuthModal() {
    var modal = document.getElementById('auth-modal');
    if (!modal) return;

    // Event delegation: #nav-signin's contents get replaced by updateNavAuth(), and there are
    // two trigger locations (desktop header + mobile drawer), so a single delegated listener
    // avoids orphaned bindings after innerHTML swaps.
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest && e.target.closest('[data-open-auth]');
      if (trigger) {
        e.preventDefault();
        openAuthModal();
        return;
      }
      var logoutBtn = e.target.closest && e.target.closest('[data-auth-logout]');
      if (logoutBtn) {
        e.preventDefault();
        doLogout();
        return;
      }
      var passToggle = e.target.closest && e.target.closest('[data-pass-toggle]');
      if (passToggle) {
        var input = document.getElementById(passToggle.getAttribute('data-pass-toggle'));
        if (input) {
          var nowVisible = input.type === 'password';
          input.type = nowVisible ? 'text' : 'password';
          passToggle.classList.toggle('is-visible', nowVisible);
          var dict = window.AGENTIVA_I18N[currentLang] || window.AGENTIVA_I18N.es;
          passToggle.setAttribute('aria-label', nowVisible ? (dict['auth.passHide'] || 'Ocultar contraseña') : (dict['auth.passShow'] || 'Mostrar contraseña'));
        }
      }
    });

    modal.querySelectorAll('[data-close-modal]').forEach(function (el) {
      el.addEventListener('click', closeAuthModal);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !modal.hidden) closeAuthModal();
    });

    var loginForm = document.getElementById('login-form');
    if (loginForm) loginForm.addEventListener('submit', handleLogin);

    updateNavAuth();
  }

  /* --------------------------------------------------------
     9. Sticky header hide-on-scroll
     -------------------------------------------------------- */
  function initHeaderScroll() {
    var header = document.getElementById('site-header');
    if (!header) return;
    var lastY = window.scrollY;
    var ticking = false;

    function onScroll() {
      var y = window.scrollY;
      header.classList.toggle('header--scrolled', y > 24);

      if (y > lastY && y > 160) {
        header.classList.add('header--hidden');
      } else {
        header.classList.remove('header--hidden');
      }
      lastY = y;
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(onScroll);
        ticking = true;
      }
    });
  }

  /* --------------------------------------------------------
     Init
     -------------------------------------------------------- */
  document.addEventListener('DOMContentLoaded', function () {
    applyLang('es');
    initTheme();
    initNavDrawer();
    initFaq();
    initReveal();
    initChatDemo();
    initCaseVideos();
    initHeaderScroll();
    initAuthModal();
  });
})();
