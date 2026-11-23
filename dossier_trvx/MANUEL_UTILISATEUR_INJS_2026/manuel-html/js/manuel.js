/* ═══════════════════════════════════════════════════════════════════════════
   MANUEL UTILISATEUR OFFICIEL — INJS ABIDJAN
   Interactions : recherche, filtres, thème, navigation, progression
   Aucune dépendance externe · fonctionne hors ligne
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ─────────────────────────────────────────────── THÈME ──────────────── */
  const CLE_THEME = 'manuel-injs-theme';
  const racine = document.documentElement;

  function appliquerTheme(theme) {
    racine.setAttribute('data-theme', theme);
    const btn = $('#btnTheme');
    if (btn) {
      btn.textContent = theme === 'sombre' ? '☀' : '◐';
      btn.title = theme === 'sombre' ? 'Passer en mode clair' : 'Passer en mode sombre';
    }
    try { localStorage.setItem(CLE_THEME, theme); } catch (e) { /* stockage indisponible */ }
  }

  let themeInitial = 'clair';
  try {
    themeInitial = localStorage.getItem(CLE_THEME) ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'sombre' : 'clair');
  } catch (e) { /* ignore */ }
  appliquerTheme(themeInitial);

  $('#btnTheme').addEventListener('click', () => {
    appliquerTheme(racine.getAttribute('data-theme') === 'sombre' ? 'clair' : 'sombre');
  });

  /* ─────────────────────────────────────────── IMPRESSION ─────────────── */
  $('#btnImprimer').addEventListener('click', () => window.print());

  /* ───────────────────────────────────── MENU MOBILE ──────────────────── */
  const sommaire = $('#sommaire');
  $('#btnMenu').addEventListener('click', () => sommaire.classList.toggle('ouvert'));
  document.addEventListener('click', (e) => {
    if (window.innerWidth > 900) return;
    if (!sommaire.contains(e.target) && !e.target.closest('#btnMenu')) {
      sommaire.classList.remove('ouvert');
    }
  });

  /* ────────────────────────────────────── PROGRESSION ─────────────────── */
  const barre = $('#progression');
  const btnHaut = $('#btnHaut');
  function majProgression() {
    const h = document.documentElement;
    const total = h.scrollHeight - h.clientHeight;
    const pct = total > 0 ? (h.scrollTop / total) * 100 : 0;
    barre.style.width = pct + '%';
    btnHaut.classList.toggle('visible', h.scrollTop > 600);
  }
  window.addEventListener('scroll', majProgression, { passive: true });
  btnHaut.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  majProgression();

  /* ──────────────────────── CARTES DE PROFILS (accueil partie XIII) ───── */
  const fiches = $$('.fiche');
  const grille = $('#grilleProfils');
  if (grille) {
    fiches.forEach((f) => {
      const code = f.dataset.profil;
      const nom = $('.fiche-titres h1', f).textContent.trim();
      const fn = $('.fiche-titres p', f).textContent.trim();
      const n = f.dataset.ecrans;
      const a = document.createElement('a');
      a.href = '#profil-' + code;
      a.className = 'carte-profil';
      a.dataset.profil = code;
      const initiale = nom.charAt(0).toUpperCase();
      a.innerHTML =
        '<div class="cp-avatar">' + initiale + '</div>' +
        '<div class="cp-nom">' + nom + '</div>' +
        '<div class="cp-fn">' + fn + '</div>' +
        '<div class="cp-n">' + n + ' écrans</div>';
      a.addEventListener('click', () => {
        if (window.innerWidth <= 900) sommaire.classList.remove('ouvert');
      });
      grille.appendChild(a);
    });
  }

  /* ─────────────────────────── REMPLIR LES FILTRES ────────────────────── */
  const selProfil = $('#filtreProfil');
  fiches.forEach((f) => {
    const nom = $('.fiche-titres h1', f).textContent.trim();
    const o = document.createElement('option');
    o.value = f.dataset.profil;
    o.textContent = nom;
    selProfil.appendChild(o);
  });

  const selModule = $('#filtreModule');
  const vus = new Set();
  $$('.nav-partie > .nav-partie-lien, .sommaire .nav-partie').forEach(() => {});
  $$('.nav-partie-lien').forEach((lien) => {
    const t = lien.textContent.replace(/^[IVXLC]+/, '').trim();
    if (t && !vus.has(t)) {
      vus.add(t);
      const o = document.createElement('option');
      o.value = lien.getAttribute('href');
      o.textContent = t;
      selModule.appendChild(o);
    }
  });

  /* ──────────────────────────── RECHERCHE ─────────────────────────────── */
  const champ = $('#recherche');
  const chapitres = $$('.chapitre');
  let surlignages = [];

  function nettoyerSurlignage() {
    surlignages.forEach((m) => {
      const parent = m.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
    surlignages = [];
  }

  function surligner(racineEl, terme) {
    if (terme.length < 2) return;
    const motif = new RegExp('(' + terme.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    const parcours = document.createTreeWalker(racineEl, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (node.parentNode.closest('script,style,code')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const cibles = [];
    let n;
    while ((n = parcours.nextNode())) {
      if (motif.test(n.nodeValue)) cibles.push(n);
      motif.lastIndex = 0;
    }
    cibles.slice(0, 40).forEach((node) => {
      const frag = document.createDocumentFragment();
      let dernier = 0;
      let m;
      motif.lastIndex = 0;
      const txt = node.nodeValue;
      while ((m = motif.exec(txt))) {
        if (m.index > dernier) frag.appendChild(document.createTextNode(txt.slice(dernier, m.index)));
        const mark = document.createElement('mark');
        mark.className = 'surligne';
        mark.textContent = m[0];
        frag.appendChild(mark);
        surlignages.push(mark);
        dernier = m.index + m[0].length;
      }
      if (dernier < txt.length) frag.appendChild(document.createTextNode(txt.slice(dernier)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  function appliquerRecherche() {
    const terme = champ.value.trim().toLowerCase();
    nettoyerSurlignage();

    // 1. Chapitres et fiches : visibilité selon le texte
    let visibles = 0;
    const elements = $$('.chapitre, .fiche, .avant-propos, .couverture, .pied');

    if (terme.length < 2) {
      elements.forEach((el) => el.classList.remove('masque'));
      $$('.partie').forEach((p) => p.classList.remove('masque'));
      $$('.carte-profil').forEach((c) => c.classList.remove('masque'));
    } else {
      elements.forEach((el) => {
        const texte = el.textContent.toLowerCase();
        const ok = texte.includes(terme);
        el.classList.toggle('masque', !ok);
        if (ok) {
          visibles++;
          surligner(el, champ.value.trim());
        }
      });
      // masquer les parties vides
      $$('.partie').forEach((p) => {
        const dedans = $$('.chapitre:not(.masque), .fiche:not(.masque)', p);
        p.classList.toggle('masque', dedans.length === 0);
      });
      // cartes de profil filtrées
      $$('.carte-profil').forEach((c) => {
        const f = document.getElementById('profil-' + c.dataset.profil);
        c.classList.toggle('masque', f ? f.classList.contains('masque') : false);
      });
    }
    appliquerFiltreProfil();
  }

  /* ──────────────────────────── FILTRE PROFIL ─────────────────────────── */
  function appliquerFiltreProfil() {
    const code = selProfil.value;
    chapitres.forEach((ch) => {
      if (!code) {
        ch.classList.remove('masque-profil');
        return;
      }
      const profils = (ch.dataset.profils || '').split(/\s+/);
      const concerne = profils.includes('tous') || profils.includes(code);
      ch.classList.toggle('masque-profil', !concerne);
    });
    // la fiche du profil choisi reste toujours visible
    fiches.forEach((f) => {
      f.classList.toggle('fiche-mise-en-avant', code && f.dataset.profil === code);
    });
    $$('.carte-profil').forEach((c) => {
      c.classList.toggle('carte-active', code && c.dataset.profil === code);
    });
  }

  champ.addEventListener('input', appliquerRecherche);
  selProfil.addEventListener('change', () => {
    appliquerFiltreProfil();
    if (selProfil.value) {
      const cible = document.getElementById('profil-' + selProfil.value);
      if (cible) cible.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  selModule.addEventListener('change', () => {
    if (selModule.value) {
      const el = document.querySelector(selModule.value);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  /* ──────────────────────── RACCOURCIS CLAVIER ────────────────────────── */
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== champ) {
      e.preventDefault();
      champ.focus();
      champ.select();
    }
    if (e.key === 'Escape') {
      if (document.activeElement === champ) {
        champ.value = '';
        appliquerRecherche();
        champ.blur();
      }
      fermerApercu();
      sommaire.classList.remove('ouvert');
    }
  });

  /* ──────────────────────── APERÇU DES CAPTURES ────────────────────────── */
  const apercu = $('#apercu');
  const apercuImg = $('#apercuImg');
  const apercuLegende = $('#apercuLegende');

  window.ouvrirApercu = function (src, alt) {
    apercuImg.src = src;
    apercuImg.alt = alt || '';
    apercuLegende.textContent = alt || '';
    apercu.classList.add('ouvert');
    document.body.style.overflow = 'hidden';
  };

  function fermerApercu() {
    apercu.classList.remove('ouvert');
    document.body.style.overflow = '';
  }
  $('#apercuFermer').addEventListener('click', fermerApercu);
  apercu.addEventListener('click', (e) => { if (e.target === apercu) fermerApercu(); });

  /* ─────────────── SOMMAIRE : SECTION ACTIVE AU DÉFILEMENT ────────────── */
  const liensNav = $$('a[data-nav]');
  const cibles = liensNav
    .map((a) => ({ lien: a, el: document.querySelector(a.getAttribute('href')) }))
    .filter((x) => x.el);

  if ('IntersectionObserver' in window && cibles.length) {
    const obs = new IntersectionObserver(
      (entrees) => {
        entrees.forEach((e) => {
          if (!e.isIntersecting) return;
          liensNav.forEach((l) => l.classList.remove('actif'));
          const trouve = cibles.find((c) => c.el === e.target);
          if (trouve) {
            trouve.lien.classList.add('actif');
            const parent = trouve.lien.closest('.nav-partie');
            if (parent) {
              const chef = $('.nav-partie-lien', parent);
              if (chef) chef.classList.add('actif');
            }
          }
        });
      },
      { rootMargin: '-15% 0px -75% 0px', threshold: 0 }
    );
    cibles.forEach((c) => obs.observe(c.el));
  }

  liensNav.forEach((a) => {
    a.addEventListener('click', () => {
      if (window.innerWidth <= 900) sommaire.classList.remove('ouvert');
    });
  });

  /* ─────────────────── DÉPLIER TOUT / REPLIER (details) ───────────────── */
  $$('details').forEach((d, i) => {
    if (d.classList.contains('famille-roles') && i > 2) d.removeAttribute('open');
  });

  /* ─────────────────────── IMPRESSION : tout déplier ──────────────────── */
  window.addEventListener('beforeprint', () => {
    $$('details').forEach((d) => { d.dataset.etaitFerme = d.open ? '' : '1'; d.open = true; });
  });
  window.addEventListener('afterprint', () => {
    $$('details').forEach((d) => {
      if (d.dataset.etaitFerme === '1') d.open = false;
      delete d.dataset.etaitFerme;
    });
  });

  /* ─────────────── MARQUAGE DES ERREURS POUR LA RECHERCHE ─────────────── */
  $$('.probleme').forEach((p) => {
    p.setAttribute('data-indexable', '1');
  });

  console.log(
    'Manuel utilisateur INJS 2026 — ' + fiches.length + ' profils · ' +
    chapitres.length + ' chapitres · recherche locale active'
  );
})();
