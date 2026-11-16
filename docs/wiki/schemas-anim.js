  /* ---- schémas : étapes (stylo rouge + reste estompé) et infobulles au survol */
  function visibleSvg(fig) {
    var d = [].slice.call(fig.querySelectorAll('.clair, .sombre')).filter(function (x) { return x.offsetParent; })[0];
    return d && d.querySelector('svg');
  }
  function elementsDe(svg, ids, fleches) {
    var base = svg.id, out = [];
    ids.forEach(function (id) {
      var n = svg.querySelector('[id^="' + base + '-flowchart-' + id + '-"]') || svg.querySelector('[id="' + base + '-' + id + '"]');
      if (n) out.push(n);
    });
    (fleches || []).forEach(function (f) {
      svg.querySelectorAll('[id^="' + base + '-L_' + f[0] + '_' + f[1] + '_"]').forEach(function (e) { out.push(e); });
      svg.querySelectorAll('.edgeLabel [data-id^="L_' + f[0] + '_' + f[1] + '_"]').forEach(function (l) { out.push(l.closest('.edgeLabel')); });
    });
    return out;
  }
  function cercle(svg, el, graine) {
    // ellipse « à main levée » : deux tours légèrement décalés autour de la boîte de l'élément (repère du SVG)
    var b = el.getBBox(), m = svg.getScreenCTM().inverse().multiply(el.getScreenCTM());
    var cx = m.a * (b.x + b.width / 2) + m.c * (b.y + b.height / 2) + m.e;
    var cy = m.b * (b.x + b.width / 2) + m.d * (b.y + b.height / 2) + m.f;
    var rx = b.width * Math.abs(m.a) / 2 + 12, ry = b.height * Math.abs(m.d) / 2 + 10, d = '';
    for (var tour = 0; tour < 2; tour++) {
      for (var i = 0; i <= 36; i++) {
        var a = (i / 36) * Math.PI * 2 + tour * 0.35 + graine;
        var bruit = 1 + 0.035 * Math.sin(a * 3 + graine * 7 + tour);
        d += (i ? 'L' : 'M') + (cx + Math.cos(a) * rx * bruit).toFixed(1) + ' ' + (cy + Math.sin(a) * ry * bruit).toFixed(1);
      }
    }
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); return p;
  }
  /* ---- place de chaque schéma : il déborde de la colonne de texte quand il lui faut plus de largeur (gros schéma,
     ou code à mettre à droite), dans la zone libre de la page hôte (.wrap du wiki, sinon le parent) ; le texte garde
     sa largeur de lecture. Code à droite dès SEUIL_COTE px de largeur libre, dessous sinon. */
  var SEUIL_COTE = 1000, CODE_CONFORT = 760, MARGES = 42;
  function placer(fig) {
    var parent = fig.parentElement, pr = parent.getBoundingClientRect();
    if (!pr.width) return;                                   // partie cachée : replacé quand elle s'affiche
    var cs = getComputedStyle(parent), pg = pr.left + parseFloat(cs.paddingLeft), pl = pr.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    var zone = fig.closest('.wrap'), g = pg, d = pg + pl;
    if (zone) {
      var zr = zone.getBoundingClientRect(), zs = getComputedStyle(zone);
      g = Math.min(g, zr.left + parseFloat(zs.paddingLeft)); d = Math.max(d, zr.right - parseFloat(zs.paddingRight));
    }
    var svg = fig.querySelector('.schema-dessin svg'), nat = svg && svg.viewBox.baseVal ? svg.viewBox.baseVal.width : 0;
    var code = !!fig.querySelector('.schema-cote'), libre = d - g, cote = code && libre >= SEUIL_COTE;
    var voulu = nat + MARGES + (cote ? CODE_CONFORT + 20 : 0);
    var large = Math.max(pl, Math.min(libre, voulu));
    fig.classList.toggle('cote', cote);
    if (large <= pl + 1) { fig.style.width = ''; fig.style.marginLeft = ''; fig.classList.remove('deborde'); }
    else {
      var gauche = Math.max(g, Math.min(pg, d - large));     // aligné sur le texte, glissé à gauche s'il le faut
      fig.style.width = large + 'px'; fig.style.marginLeft = (gauche - pg) + 'px'; fig.classList.add('deborde');
    }
    // bouton « Agrandir » seulement si le schéma est réduit par la hauteur de l'écran
    var b = fig.querySelector('.schema-taille'), vu = visibleSvg(fig);
    if (b && vu && !fig.classList.contains('agrandi')) {
      var bb = vu.viewBox.baseVal, r = vu.getBoundingClientRect();
      b.hidden = !(bb && bb.width && r.width && r.height < Math.min(r.width, bb.width) * bb.height / bb.width - 2);
    }
    document.dispatchEvent(new CustomEvent('schemas-places'));
  }
  var figures = [].slice.call(document.querySelectorAll('figure.schema'));
  figures.forEach(function (fig) {
    if (!fig.querySelector('.schema-dessin')) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'schema-taille'; b.hidden = true;
    b.textContent = 'Agrandir le schéma';
    b.addEventListener('click', function () {
      var grand = fig.classList.toggle('agrandi');
      b.textContent = grand ? 'Réduire le schéma' : 'Agrandir le schéma';
      placer(fig);
    });
    var dessin = fig.querySelector('.schema-dessin'); dessin.insertBefore(b, dessin.firstChild);   // dans la zone du dessin
    var cote = fig.querySelector('.schema-cote');
    if (cote) {
      var vide = document.createElement('p'); vide.className = 'schema-cote-vide';
      vide.textContent = 'Cliquer une boîte du schéma pour voir son code ici.';
      cote.insertBefore(vide, cote.firstChild);
    }
  });
  function placerTout() { figures.forEach(placer); }
  var largeurs = new WeakMap();
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(function (es) {
      var change = false;
      es.forEach(function (e) {
        var l = Math.round(e.contentRect.width); if (largeurs.get(e.target) !== l) { largeurs.set(e.target, l); change = true; }
      });
      if (change) placerTout();
    });
    var vus = [];
    figures.forEach(function (fig) { if (vus.indexOf(fig.parentElement) < 0) { vus.push(fig.parentElement); ro.observe(fig.parentElement); } });
  }
  window.addEventListener('resize', placerTout);
  document.addEventListener('wiki-apparence', function () { setTimeout(placerTout, 0); });
  placerTout();

  var bulle = null;
  document.querySelectorAll('figure.schema[data-anim]').forEach(function (fig) {
    var anim = JSON.parse(fig.dataset.anim), etapes = anim.etapes || [], courante = 0, codes = anim.codes || {};
    // ---- boîtes reliées au code (%% code) : clic = panneau du code sous le schéma
    var parEtape = null;
    function panneau(id) { return fig.querySelector('.schema-code[data-noeud="' + id + '"]'); }
    // Un seul panneau ouvert à la fois ; la boîte dont le code est affiché est marquée sur le schéma.
    function basculer(id, ouvrir) {
      var p = panneau(id); if (!p) return;
      var ouvre = ouvrir === undefined ? p.hidden : ouvrir;
      fig.querySelectorAll('.schema-code').forEach(function (x) { x.hidden = true; });
      fig.querySelectorAll('.code-ouvert').forEach(function (x) { x.classList.remove('code-ouvert'); });
      fig.classList.toggle('a-code', !!ouvre);
      if (!ouvre) return;
      p.hidden = false;
      fig.querySelectorAll('svg').forEach(function (svg) {
        elementsDe(svg, [id]).forEach(function (n) { n.classList.add('code-ouvert'); });
      });
    }
    fig._ouvrirCode = function (id) { basculer(id, true); };   // utilisé par les fiches de module (plus bas)
    // En-tête de chaque panneau : nom de la boîte (lu sur le schéma) et bouton Fermer
    Object.keys(codes).forEach(function (id) {
      var p = panneau(id), svg = fig.querySelector('svg'), n = svg && elementsDe(svg, [id])[0];
      if (!p) return;
      var tete = document.createElement('div'); tete.className = 'schema-code-tete';
      tete.innerHTML = '<span>Code de la boîte <strong></strong></span>' +
        '<button type="button" aria-label="Fermer le code">Fermer ✕</button>';
      tete.querySelector('strong').textContent = n ? n.textContent.trim() : id;
      tete.querySelector('button').addEventListener('click', function () {
        basculer(id, false); if (parEtape === id) parEtape = null;
      });
      p.insertBefore(tete, p.firstChild);
    });
    Object.keys(codes).forEach(function (id) {
      fig.querySelectorAll('svg').forEach(function (svg) {
        elementsDe(svg, [id]).forEach(function (n) {
          n.classList.add('code-lie'); n.setAttribute('tabindex', '0'); n.setAttribute('role', 'button');
          n.addEventListener('click', function () { basculer(id); if (parEtape === id) parEtape = null; });
          n.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') { basculer(id); ev.preventDefault(); ev.stopPropagation(); }
          });
        });
      });
    });
    // infobulles : sur les deux versions (clair / sombre)
    Object.keys(anim.survols || {}).forEach(function (id) {
      fig.querySelectorAll('svg').forEach(function (svg) {
        elementsDe(svg, [id]).forEach(function (n) {
          n.classList.add('survolable');
          n.addEventListener('mouseenter', function () {
            bulle = bulle || document.body.appendChild(document.createElement('div'));
            bulle.className = 'schema-bulle'; bulle.textContent = anim.survols[id]; bulle.hidden = false;
            if (codes[id]) {
              var ind = bulle.appendChild(document.createElement('div'));
              ind.className = 'indice'; ind.textContent = 'Cliquer : voir le code';
            }
          });
          n.addEventListener('mousemove', function (e) { bulle.style.left = (e.clientX + 14) + 'px'; bulle.style.top = (e.clientY + 14) + 'px'; });
          n.addEventListener('mouseleave', function () { bulle.hidden = true; });
        });
      });
    });
    if (!etapes.length) return;
    var barre = document.createElement('div'); barre.className = 'schema-barre';
    barre.innerHTML = '<button type="button" data-d="-1" aria-label="Étape précédente">◀</button>' +
      '<div class="txt" aria-live="polite"></div><button type="button" data-d="1" aria-label="Étape suivante">▶</button>';
    // la barre des étapes reste collée au dessin (au-dessus du code, ou à sa gauche sur un écran large)
    (fig.querySelector('.schema-dessin') || fig).appendChild(barre); fig.tabIndex = 0;
    var txt = barre.querySelector('.txt'), avant = barre.querySelector('[data-d="-1"]'), apres = barre.querySelector('[data-d="1"]');
    function montrer() {
      fig.querySelectorAll('svg').forEach(function (svg) {
        svg.classList.toggle('etapes-on', courante > 0);
        svg.querySelectorAll('.en-avant').forEach(function (e) { e.classList.remove('en-avant'); });
        svg.querySelectorAll('.stylo').forEach(function (e) { e.remove(); });
      });
      avant.disabled = courante === 0; apres.disabled = courante === etapes.length;
      // lignes de code de l'étape : panneau ouvert, lignes surlignées ; le panneau ouvert par l'étape précédente
      // se referme (pas celui qu'on a ouvert d'un clic)
      fig.querySelectorAll('.schema-code .l.surligne').forEach(function (l) { l.classList.remove('surligne'); });
      var ec = courante > 0 && etapes[courante - 1].code;
      if (parEtape && (!ec || ec.noeud !== parEtape)) { basculer(parEtape, false); parEtape = null; }
      if (ec) {
        var p = panneau(ec.noeud);
        if (p) {
          if (p.hidden) { basculer(ec.noeud, true); parEtape = ec.noeud; }
          var premiere = null;
          p.querySelectorAll('.l').forEach(function (l) {
            var n = +l.dataset.l;
            if (n >= ec.de && n <= ec.a) { l.classList.add('surligne'); premiere = premiere || l; }
          });
          var pre = p.querySelector('pre');
          // le code défile jusqu'aux lignes surlignées (trois lignes de contexte au-dessus)
          if (premiere && pre) pre.scrollTop = Math.max(0, pre.scrollTop + premiere.getBoundingClientRect().top - pre.getBoundingClientRect().top - 64);
        }
      }
      if (courante === 0) {
        txt.innerHTML = '<div class="num">Vue d\'ensemble · ' + etapes.length + ' étapes</div>Suivez le parcours avec ▶ ou les flèches du clavier.';
        return;
      }
      var e = etapes[courante - 1];
      txt.innerHTML = '<div class="num">Étape ' + courante + ' / ' + etapes.length + '</div><strong></strong> <span></span>';
      txt.querySelector('strong').textContent = e.titre + ' :'; txt.querySelector('span').textContent = e.texte;
      fig.querySelectorAll('svg').forEach(function (svg) {
        // un groupe (subgraph) cité dans l'étape reste net, mais ses nœuds sont à citer aussi
        elementsDe(svg, e.noeuds, e.fleches).forEach(function (el) { el.classList.add('en-avant'); });
      });
      var svg = visibleSvg(fig);
      if (svg) {
        var g = document.createElementNS('http://www.w3.org/2000/svg', 'g'); g.setAttribute('class', 'stylo');
        elementsDe(svg, e.noeuds).forEach(function (el, i) { g.appendChild(cercle(svg, el, courante + i * 1.7)); });
        svg.appendChild(g);
      }
    }
    barre.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b || b.disabled) return;
      courante += +b.dataset.d; montrer();
    });
    fig.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowRight' && courante < etapes.length) { courante++; montrer(); ev.preventDefault(); }
      if (ev.key === 'ArrowLeft' && courante > 0) { courante--; montrer(); ev.preventDefault(); }
    });
    var boutonTheme = document.getElementById('theme');   // bouton de thème de la page hôte, s'il existe
    if (boutonTheme) boutonTheme.addEventListener('click', function () { setTimeout(montrer, 0); });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', montrer);
    document.addEventListener('wiki-apparence', function () { setTimeout(montrer, 0); });   // fenêtre « Apparence » de la page hôte
    montrer();
  });
  placerTout();   // la barre des étapes est posée : hauteur du dessin à revoir

  /* ---- fiches de module : un nom de fonction déplie son code, et mène à la figure de la page qui l'explique
     (organigramme, puis schéma écrit à la main, puis extrait, puis carte) */
  var RANG = { organigramme: 0, schema: 1, extrait: 2, carte: 3 };
  var NOM_GENRE = { organigramme: 'organigramme', schema: 'schéma', extrait: 'extrait de code', carte: 'carte' };
  function destinations(cle, sauf) {
    var out = [];
    document.querySelectorAll('figure.schema[data-anim]').forEach(function (f) {
      if (f === sauf) return;
      var c = JSON.parse(f.dataset.anim).cibles || {};
      Object.keys(c).forEach(function (n) {
        if (c[n] === cle) out.push({ el: f, genre: f.dataset.genre || 'schema', noeud: n, taille: Object.keys(c).length });
      });
    });
    document.querySelectorAll('figure.code[data-cible]').forEach(function (f) {
      if (f.dataset.cible === cle && !f.closest('.schema-code')) out.push({ el: f, genre: 'extrait', taille: 1 });
    });
    // à genre égal, la figure la plus ciblée d'abord (le moins de boîtes reliées : celle consacrée à la fonction)
    out.sort(function (a, b) { return RANG[a.genre] - RANG[b.genre] || a.taille - b.taille; });
    return out;
  }
  function titreAvant(el) {
    // titre de partie le plus proche au-dessus de la figure
    for (var n = el; n; n = n.parentElement) {
      for (var s = n.previousElementSibling; s; s = s.previousElementSibling) {
        if (/^H[1-3]$/.test(s.tagName)) return s;
      }
    }
    return null;
  }
  function aller(d) {
    d.el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    d.el.classList.add('cible-vue');
    setTimeout(function () { d.el.classList.remove('cible-vue'); }, 1800);
    if (d.noeud && d.el._ouvrirCode) d.el._ouvrirCode(d.noeud);
  }
  function remplirVoir(zone, cle, sauf) {
    var ds = destinations(cle, sauf);
    if (!ds.length) { zone.textContent = 'Pas d\'autre figure sur cette fonction dans cette page.'; return; }
    zone.appendChild(document.createTextNode('Expliqué dans : '));
    ds.slice(0, 4).forEach(function (d, i) {
      var h = titreAvant(d.el), a = document.createElement('a');
      a.href = h && h.id ? '#' + h.id : '#';
      var titre = h ? h.textContent.replace(/#\s*$/, '').trim() : 'plus bas';   // sans l'ancre « # » du titre
      a.textContent = '« ' + titre + ' » (' + NOM_GENRE[d.genre] + ')';
      a.addEventListener('click', function (ev) { ev.preventDefault(); aller(d); });
      if (i) zone.appendChild(document.createTextNode(' · '));
      zone.appendChild(a);
    });
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('.fiche-fn');
    if (!b) return;
    var ligne = b.closest('tr').nextElementSibling, ouvre = ligne.hidden;
    ligne.hidden = !ouvre;
    b.setAttribute('aria-expanded', String(ouvre));
    if (ouvre && !ligne.dataset.pret) {
      ligne.dataset.pret = '1';
      remplirVoir(ligne.querySelector('.fiche-voir'), b.dataset.cle, b.closest('figure.schema'));
    }
  });
