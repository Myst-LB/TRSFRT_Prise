// Dessine des schémas Mermaid en SVG (thème clair et sombre), une fois pour toutes. Outil du skill
// schemas-main-levee (dépôt Myst-skills), appelé par schemas.py (lui-même utilisé par le gen.py de docs-wiki) :
//   MERMAID_JS=/chemin/mermaid.min.js node schemas.js liste.json [dossier]
// liste.json = [{"cle": "abc123", "code": "flowchart LR …"}, …] ; écrit <dossier>/<cle>-clair.svg et -sombre.svg
// (dossier par défaut : schemas/ à côté de ce fichier).
// Prérequis : Node + Playwright (Chromium) + mermaid.min.js de Mermaid 11 (npm pack mermaid@11.17.2, dossier
// package/dist) : le trait « dessiné à la main » (look handDrawn, rough.js) n'existe qu'à partir de la 11.
//
// Style : trait à main levée (graine fixe : un même schéma donne toujours le même SVG), aplats doux, couleurs du
// wiki docs-wiki. Classes à mettre sur les nœuds dans le Markdown (N[NetBox]:::accent) :
//   accent   l'élément principal (1 ou 2 par schéma)      donnee   base, fichier, stockage
//   externe  hors de notre périmètre (Catalyst Center…)   alerte   refus, erreur, risque
//   discret  détail secondaire
// Les étapes et infobulles (%% étape / %% survol) sont lues par schemas.py, pas par Mermaid. Les pictogrammes sont
// lus ici (icones.json) et posés après la mise en page de Mermaid :
//   %% icône serveur : S1 S2     pastille « serveur » sur le coin des boîtes S1 et S2
//   %% icône script : C          étiquette de l'extension lue dans le nom de la boîte (check_backups.py -> « py »)
//   %% échange api : A->B        pictogramme « API » dans le libellé de la flèche A->B, trait en tirets ; légende
//                                ajoutée sous le schéma par schemas.py
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ICONES = JSON.parse(fs.readFileSync(path.join(__dirname, 'icones.json'), 'utf8'));
const RE_ICONE = /^\s*%%\s*ic[oô]ne\s+([\w-]+)\s*:\s*(.+?)\s*$/;
const RE_ECHANGE = /^\s*%%\s*[ée]change\s+([\w-]+)\s*:\s*(.+?)\s*$/;

function lirePictos(code) {
  // [{type, ids}] et [{type, fleches: [[A, B]]}] ; un type inconnu arrête le dessin (signalé par schemas.py)
  const icones = [], echanges = [];
  for (const ligne of code.split('\n')) {
    let m = RE_ICONE.exec(ligne);
    if (m) {
      if (m[1] !== 'script' && !ICONES.equipements[m[1]]) throw new Error(`icône inconnue « ${m[1]} » ; connues : ${Object.keys(ICONES.equipements).join(', ')}`);
      icones.push({ type: m[1], ids: m[2].split(/\s+/) });
      continue;
    }
    m = RE_ECHANGE.exec(ligne);
    if (m) {
      if (!ICONES.echanges[m[1]]) throw new Error(`échange inconnu « ${m[1]} » ; connus : ${Object.keys(ICONES.echanges).join(', ')}`);
      echanges.push({ type: m[1], fleches: m[2].split(/\s+/).map((f) => f.replace('-->', '->').split('->')) });
    }
  }
  return { icones, echanges };
}

// Couleurs accordées au modèle des wikis (charte « Craft » : surfaces neutres, accent indigo). Les SVG sont dessinés
// à la génération : ils ne suivent pas la couleur d'accent choisie par le lecteur dans « Apparence ».
const PALETTES = {
  clair: {
    fond: '#ffffff', encre: '#111827', etiquette: '#374151', trait: '#6b7280', groupe: '#f9fafb', bordGroupe: '#d1d5db',
    classes: {
      accent: ['#eef0fb', '#5e6ad2', '#2e3aa2'], donnee: ['#fffbeb', '#d97706', '#7c4a03'],
      externe: ['#f3f4f6', '#9ca3af', '#374151'], alerte: ['#fef2f2', '#dc2626', '#7f1d1d'],
      discret: ['#ffffff', '#d1d5db', '#6b7280'],
    },
  },
  sombre: {
    fond: '#181920', encre: '#f4f5f6', etiquette: '#c9ccd3', trait: '#9ba1ad', groupe: '#1d1e26', bordGroupe: '#3d4052',
    classes: {
      accent: ['#1e2038', '#7c86e8', '#dfe0ff'], donnee: ['#2a1f0b', '#f59e0b', '#fde6b8'],
      externe: ['#22232b', '#6b7180', '#c9ccd3'], alerte: ['#2d1517', '#f87171', '#ffd6d2'],
      discret: ['#181920', '#3d4052', '#9ba1ad'],
    },
  },
};

// Texte sur les flèches : plus petit et un peu plus discret que celui des boîtes (appliqué avant la mise en page,
// pour que Mermaid réserve la bonne place), et plus d'espace entre les rangs quand le schéma a des libellés.
const TAILLE_ETIQUETTE = '13px';
const ECART_RANGS = 58, ECART_RANGS_ETIQUETTES = 76;
// Libellé de flèche : « A -- texte --> B », « A -. texte .-> B », « A == texte ==> B », « A -->|texte| B »
const RE_ETIQUETTE = /(--|==|-\.)\s*[^\s>|-][^\n]*?(-->|==>|\.->|---)|\|[^|\n]+\|/;

function classDefs(p) {
  return Object.entries(p.classes)
    .map(([nom, [fond, bord, texte]]) => `  classDef ${nom} fill:${fond},stroke:${bord},color:${texte},stroke-width:1.6px`)
    .join('\n');
}

(async () => {
  const liste = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  // Aplats pleins au lieu des hachures que Mermaid impose en mode main levée (texte illisible sur les hachures).
  // Chaîne de Mermaid 11.17.2 : si elle change (autre version), on s'arrête plutôt que de dessiner autrement.
  const HACHURES = 'fillStyle:"hachure",fillWeight:4,hachureGap:5.2';
  const brut = fs.readFileSync(process.env.MERMAID_JS, 'utf8');
  if (!brut.includes(HACHURES)) throw new Error('mermaid.min.js inattendu : prendre Mermaid 11.17.2 (npm pack mermaid@11.17.2)');
  const mermaid = brut.split(HACHURES).join('fillStyle:"solid"');
  const sortie = process.argv[3] || path.join(__dirname, 'schemas');
  fs.mkdirSync(sortie, { recursive: true });
  const navigateur = await chromium.launch();
  const page = await navigateur.newPage();
  await page.setContent('<!doctype html><html><body></body></html>');
  await page.addScriptTag({ content: mermaid });
  for (const theme of ['clair', 'sombre']) {
    const p = PALETTES[theme];
    for (const { cle, code } of liste) {
      // classDef ajoutés seulement aux organigrammes (flowchart / graph) ; les séquences gardent le thème
      const organigramme = /^\s*(flowchart|graph)\b/.test(code);
      const complet = organigramme ? `${code}\n${classDefs(p)}` : code;
      const rangs = organigramme && RE_ETIQUETTE.test(code) ? ECART_RANGS_ETIQUETTES : ECART_RANGS;
      const pictos = lirePictos(code);
      const svg = await page.evaluate(async ({ code, p, id, rangs, taille, pictos, ICONES }) => {
        window.mermaid.initialize({
          startOnLoad: false, securityLevel: 'strict', theme: 'base', look: 'handDrawn', handDrawnSeed: 3,
          fontFamily: 'IBM Plex Sans, system-ui, Segoe UI, sans-serif',
          themeVariables: {
            fontFamily: 'IBM Plex Sans, system-ui, Segoe UI, sans-serif', fontSize: '15px',
            background: p.fond, primaryColor: p.fond, primaryBorderColor: p.encre, primaryTextColor: p.encre,
            secondaryColor: p.groupe, tertiaryColor: p.groupe, lineColor: p.trait, textColor: p.encre,
            clusterBkg: p.groupe, clusterBorder: p.bordGroupe, titleColor: p.trait,
            edgeLabelBackground: p.fond, noteBkgColor: p.groupe, noteBorderColor: p.bordGroupe,
            actorBkg: p.fond, actorBorder: p.encre, actorTextColor: p.encre, signalColor: p.trait,
            signalTextColor: p.encre, labelBoxBkgColor: p.groupe, labelBoxBorderColor: p.bordGroupe,
            sequenceNumberColor: p.fond,
          },
          themeCSS: `.edgeLabel .label text, .edgeLabel .label tspan { font-size: ${taille} !important; fill: ${p.etiquette} !important }`,
          flowchart: { htmlLabels: false, curve: 'basis', padding: 14, nodeSpacing: 46, rankSpacing: rangs },
          // Mermaid coupe un libellé de flèche au-delà d'environ 200 px (réglage sans effet en 11.17.2) : libellés
          // courts ; pour choisir la coupure, chaîne Markdown avec retour à la ligne : A -- "`un⏎deux`" --> B
          sequence: { useMaxWidth: true, mirrorActors: false },
        });
        const { svg } = await window.mermaid.render(id, code);
        // Fond des libellés de flèches : Mermaid le calcule pour une ligne et ne le peint pas (la flèche barre le
        // texte). Pastille arrondie redessinée sur le texte réel, toutes lignes comprises, couleur du fond.
        const hote = document.body.appendChild(document.createElement('div'));
        hote.innerHTML = svg;
        hote.querySelectorAll('.edgeLabel').forEach((etiquette) => {
          const texte = etiquette.querySelector('text'), fond = etiquette.querySelector('rect.background');
          if (!texte || !fond || !texte.textContent.trim()) return;
          const b = texte.getBBox();
          for (const [k, v] of Object.entries({ x: b.x - 7, y: b.y - 3, width: b.width + 14, height: b.height + 6, rx: 6, ry: 6 }))
            fond.setAttribute(k, +v.toFixed(2));
          fond.setAttribute('style', `fill:${p.fond};stroke:${p.bordGroupe};stroke-width:1;opacity:1`);
        });

        // ---- pictogrammes (%% icône / %% échange), posés sans toucher à la mise en page
        const NS = 'http://www.w3.org/2000/svg', racine = hote.querySelector('svg'), base = racine.id;
        const picto = (dessin, cx, cy, taille, couleur) => {
          const g = document.createElementNS(NS, 'g');
          g.setAttribute('transform', `translate(${(cx - taille / 2).toFixed(2)} ${(cy - taille / 2).toFixed(2)}) scale(${taille / 24})`);
          g.setAttribute('fill', 'none'); g.setAttribute('stroke', couleur); g.setAttribute('stroke-width', '1.9');
          g.setAttribute('stroke-linecap', 'round'); g.setAttribute('stroke-linejoin', 'round');
          g.innerHTML = dessin;
          // les classes de Mermaid (.accent path { … !important }) ne doivent pas repeindre le pictogramme
          g.querySelectorAll('*').forEach((el) => el.setAttribute('style', `fill:none !important;stroke:${couleur} !important`));
          return g;
        };
        const rond = (cx, cy, r, bord) => {
          const c = document.createElementNS(NS, 'circle');
          for (const [k, v] of Object.entries({ cx, cy, r })) c.setAttribute(k, +v.toFixed(2));
          c.setAttribute('style', `fill:${p.fond} !important;stroke:${bord} !important;stroke-width:1.4px !important`);
          return c;
        };
        for (const { type, ids } of pictos.icones) {
          for (const n of ids) {
            const noeud = racine.querySelector(`[id^="${base}-flowchart-${n}-"]`);
            if (!noeud) throw new Error(`icône ${type} : nœud « ${n} » introuvable`);
            const b = noeud.getBBox(), trait = noeud.querySelector('path');
            const bord = (trait && getComputedStyle(trait).stroke !== 'none' && getComputedStyle(trait).stroke) || p.encre;
            // pastille centrée sur le coin haut gauche de la boîte : loin du texte et des flèches (milieux des côtés)
            const g = document.createElementNS(NS, 'g');
            noeud.appendChild(g);
            if (type === 'script') {
              // étiquette de l'extension, couleur du langage (icones.json, « scripts »)
              const nom = (noeud.querySelector('text') || noeud).textContent.trim();
              const ext = (/\.([A-Za-z0-9]{1,5})\s*$/.exec(nom) || /\.([A-Za-z0-9]{1,5})\b/.exec(nom) || [])[1];
              if (!ext) throw new Error(`icône script : pas d'extension dans le nom de « ${n} » (${nom})`);
              const c = ICONES.scripts[ext.toLowerCase()] || ICONES.scripts._autre;
              g.setAttribute('class', 'picto-script');
              const txt = document.createElementNS(NS, 'text');
              txt.textContent = ext.toLowerCase();
              txt.setAttribute('style', `font: 700 12px 'IBM Plex Mono', ui-monospace, Consolas, monospace; fill: ${c.texte} !important; stroke: none !important`);
              txt.setAttribute('text-anchor', 'middle'); txt.setAttribute('dominant-baseline', 'central');
              txt.setAttribute('x', +(b.x + 6).toFixed(2)); txt.setAttribute('y', +b.y.toFixed(2));
              g.appendChild(txt);
              const lt = txt.getBBox().width + 12, cadre = document.createElementNS(NS, 'rect');
              for (const [k, v] of Object.entries({ x: b.x + 6 - lt / 2, y: b.y - 10, width: lt, height: 20, rx: 5, ry: 5 }))
                cadre.setAttribute(k, +v.toFixed(2));
              cadre.setAttribute('style', `fill:${c.fond} !important;stroke:${p.fond} !important;stroke-width:1.5px !important`);
              g.insertBefore(cadre, txt);
              continue;
            }
            g.setAttribute('class', 'picto-equipement');
            g.appendChild(rond(b.x, b.y, 17, bord));
            g.appendChild(picto(ICONES.equipements[type].svg, b.x, b.y, 22, bord));
          }
        }
        for (const { type, fleches } of pictos.echanges) {
          const e = ICONES.echanges[type];
          for (const [a, b] of fleches) {
            const chemin = racine.querySelector(`[id^="${base}-L_${a}_${b}_"]`);
            if (!chemin) throw new Error(`échange ${type} : flèche ${a}->${b} introuvable`);
            if (e.tirets) chemin.style.strokeDasharray = e.tirets;
            const label = racine.querySelector(`.edgeLabel [data-id^="L_${a}_${b}_"]`);
            const texte = label && label.querySelector('text'), fond = label && label.parentElement.querySelector('rect.background');
            if (texte && texte.textContent.trim() && fond) {
              // libellé : pictogramme à gauche du texte, dans la même pastille
              const t = texte.getBBox();
              texte.setAttribute('transform', 'translate(10 0)');
              const x = +fond.getAttribute('x'), w = +fond.getAttribute('width');
              fond.setAttribute('x', +(x - 10).toFixed(2)); fond.setAttribute('width', +(w + 20).toFixed(2));
              texte.parentNode.appendChild(picto(e.svg, t.x - 8, t.y + Math.min(t.height, 18) / 2, 15, p.etiquette));
            } else {
              // flèche sans libellé : pastille ronde au milieu de la flèche
              const l = chemin.getTotalLength(), pt = chemin.getPointAtLength(l / 2);
              let hoteEtiquette = label ? label : null;
              if (!hoteEtiquette) {
                const conteneur = racine.querySelector('.edgeLabels') || racine;
                const eti = conteneur.appendChild(document.createElementNS(NS, 'g')); eti.setAttribute('class', 'edgeLabel');
                hoteEtiquette = eti.appendChild(document.createElementNS(NS, 'g'));
                hoteEtiquette.setAttribute('class', 'label'); hoteEtiquette.setAttribute('data-id', `L_${a}_${b}_0`);
              }
              const m = hoteEtiquette.getScreenCTM().inverse().multiply(chemin.getScreenCTM());
              const q = new DOMPoint(pt.x, pt.y).matrixTransform(m);
              hoteEtiquette.appendChild(rond(q.x, q.y, 11, p.bordGroupe));
              hoteEtiquette.appendChild(picto(e.svg, q.x, q.y, 14, p.etiquette));
            }
          }
        }
        if (pictos.icones.length) {
          // les pastilles des coins débordent : agrandir le cadre du dessin
          const v = racine.viewBox.baseVal, c = racine.getBBox(), marge = 4;
          const x0 = Math.min(v.x, c.x - marge), y0 = Math.min(v.y, c.y - marge);
          const x1 = Math.max(v.x + v.width, c.x + c.width + marge), y1 = Math.max(v.y + v.height, c.y + c.height + marge);
          racine.setAttribute('viewBox', [x0, y0, x1 - x0, y1 - y0].map((n) => +n.toFixed(2)).join(' '));
          racine.style.maxWidth = `${(x1 - x0).toFixed(2)}px`;
        }
        const propre = hote.innerHTML;
        hote.remove();
        return propre;
      }, { code: complet, p, id: `sch-${cle}-${theme}`, rangs, taille: TAILLE_ETIQUETTE, pictos, ICONES });
      fs.writeFileSync(path.join(sortie, `${cle}-${theme}.svg`), svg);
    }
  }
  await navigateur.close();
  console.log(`${liste.length} schéma(s) dessiné(s)`);
})().catch(e => { console.error(e.message); process.exit(1); });
