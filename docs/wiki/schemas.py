#!/usr/bin/env python3
"""Schémas Mermaid « à main levée » : SVG clair + sombre, étapes pas à pas au stylo rouge, infobulles.
Outil du skill schemas-main-levee (dépôt Myst-skills). Deux usages :

1. Seul, sans autre outil que Node + Playwright (Chromium) :

       python schemas.py schema.mmd                   -> schema.html (page autonome, à ouvrir dans un navigateur)
       python schemas.py notes.md -o schemas.html     -> tous les blocs ```mermaid d'un Markdown, sous leur titre
       python schemas.py schema.mmd --svg dossier/    -> seulement les SVG (dossier/<clé>-clair.svg, -sombre.svg)

2. Comme module, par le gen.py du skill docs-wiki (copié dans docs/wiki/ des projets) :
   lire_annotations(), cle(), dessiner(), figure(), css(), js().

Syntaxe ajoutée à Mermaid (lignes « %% », ignorées par Mermaid) :

    N[NetBox]:::accent                         classes : accent, donnee, externe, alerte, discret (schemas.js)
    %% survol N : texte                        infobulle au survol du nœud N
    %% étape Titre : texte | N M A->B          nœuds N, M entourés au stylo, flèche A->B nette, le reste estompé
    %% icône serveur : N M                     pictogramme sur le coin des boîtes (types : icones.json) ;
                                               « script » : extension lue dans le nom (check_backups.py -> py)
    %% échange api : A->B                      pictogramme et trait du type d'échange sur la flèche, légende sous
                                               le schéma (config, fichier, sauvegarde, api, interne, courriel…)
    %% code C : fichier.py | def f(            boîte C reliée au vrai code (clic = panneau du code, infobulle par
                                               défaut = signature) ; repère vérifié à chaque génération
    %% étape T : texte | C | C : début .. fin  l'étape surligne aussi ces lignes du code de C (incluses)

Blocs générés depuis le code Python (schemas_code.py) : ```carte-code fichier.py [| depuis main | sans _prives]```
(qui appelle qui dans un module) et ```organigramme-code fichier.py | fonction``` (fonction courte).

Le dessin passe par schemas.js et Mermaid 11.17.2 (fourni dans vendor/) ; un SVG déjà dessiné (même code, même
STYLE) est réutilisé : modifier une étape ou une infobulle ne redessine rien.
"""
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schemas_code  # noqa: E402

ICI = Path(__file__).resolve().parent
NOM_SKILL = 'schemas-main-levee'
MERMAID = 'mermaid-11.17.2.min.js'
# Changer STYLE_SCHEMAS redessine tous les schémas (nouvelle version du style de schemas.js)
STYLE_SCHEMAS = 'main-levee-4'   # 4 : couleurs de la charte « Craft » (indigo, surfaces neutres) ; 3 : texte des flèches
RE_ETAPE = re.compile(r'^\s*%%\s*étape\s+(.+?)\s*:\s*(.+?)\s*\|\s*(.+?)\s*$')
RE_SURVOL = re.compile(r'^\s*%%\s*survol\s+([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*$')
# %% icône / %% échange restent dans le code : ils changent le dessin (donc la clé) et sont lus par schemas.js
RE_ECHANGE = re.compile(r'^\s*%%\s*[ée]change\s+([\w-]+)\s*:', re.M)
ICONES = json.loads((ICI / 'icones.json').read_text(encoding='utf-8'))


def lire(code):
    """Comme lire_annotations(), plus les liens vers le code (« %% code N : chemin | repère ») et, dans une
    étape, un 2e « | N : début .. fin » (lignes à surligner, gardé dans etape['lignes'] pour schemas_code.relier).
    Renvoie {'code', 'etapes', 'survols', 'liens'}."""
    liens, lignes = {}, []
    for ligne in code.splitlines():
        m = schemas_code.RE_CODE.match(ligne)
        if m:
            liens[m.group(1)] = m.group(2)
        else:
            lignes.append(ligne)
    code, etapes, survols = lire_annotations('\n'.join(lignes))
    return {'code': code, 'etapes': etapes, 'survols': survols, 'liens': liens}


def lire_annotations(code):
    """Retire du code Mermaid les lignes « %% étape Titre : texte | ids » et « %% survol id : texte ».
    Renvoie (code sans ces lignes, étapes, survols). Dans les ids d'une étape, « A->B » désigne la flèche de A
    vers B ; les autres mots sont des nœuds ou des groupes (subgraph)."""
    etapes, survols, lignes = [], {}, []
    for ligne in code.splitlines():
        m = RE_ETAPE.match(ligne)
        if m:
            ids, _, lignes_code = m.group(3).partition('|')
            ids = ids.split()
            etapes.append({'titre': m.group(1), 'texte': m.group(2),
                           'noeuds': [i for i in ids if '->' not in i],
                           'fleches': [i.replace('-->', '->').split('->') for i in ids if '->' in i]})
            if lignes_code.strip():
                etapes[-1]['lignes'] = lignes_code.strip()
            continue
        m = RE_SURVOL.match(ligne)
        if m:
            survols[m.group(1)] = m.group(2)
        else:
            lignes.append(ligne)
    return '\n'.join(lignes).strip(), etapes, survols


def cle(code):
    """Clé du SVG : dépend du code Mermaid (sans annotations) et du style, pas des étapes ni des infobulles."""
    return hashlib.sha1((STYLE_SCHEMAS + code).encode()).hexdigest()[:12]


def fichiers_svg(cle_schema, dossier):
    dossier = Path(dossier)
    return dossier / f'{cle_schema}-clair.svg', dossier / f'{cle_schema}-sombre.svg'


def dessine(cle_schema, dossier):
    return all(f.exists() for f in fichiers_svg(cle_schema, dossier))


def trouver_mermaid():
    """mermaid.min.js : MERMAID_JS, sinon vendor/ de ce skill, installé (~/.claude/skills) ou copié dans un
    dépôt (.claude/skills, en remontant depuis le dossier courant), ou dans un clone de Myst-skills voisin
    (Myst-skills/skills/ en remontant, 1.7.1), sinon l'ancien emplacement (docs-wiki 1.x)."""
    if os.environ.get('MERMAID_JS'):
        return os.environ['MERMAID_JS']
    candidats = [ICI / 'vendor' / MERMAID, Path.home() / '.claude' / 'skills' / NOM_SKILL / 'outil' / 'vendor' / MERMAID]
    for base in (Path.cwd(), *Path.cwd().parents, ICI, *ICI.parents):
        candidats.append(base / '.claude' / 'skills' / NOM_SKILL / 'outil' / 'vendor' / MERMAID)
        for depot in ('Myst-skills', 'myst-skills'):   # clone voisin (minuscules : nom donné par certains clones)
            candidats.append(base / depot / 'skills' / NOM_SKILL / 'outil' / 'vendor' / MERMAID)
    candidats.append(Path.home() / '.claude' / 'skills' / 'docs-wiki' / 'outil' / 'vendor' / MERMAID)
    return next((str(c) for c in candidats if c.is_file()), '')


def dessiner(liste, dossier):
    """Dessine [{'cle', 'code'}] dans dossier (clair + sombre). Renvoie None, ou le message d'erreur."""
    if not liste:
        return None
    mermaid_js = trouver_mermaid()
    if not Path(mermaid_js).is_file():
        return f'{len(liste)} schéma(s) non dessiné(s) : Mermaid introuvable, définir MERMAID_JS (voir schemas.js)'
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(liste, f)
    try:
        r = subprocess.run(['node', str(ICI / 'schemas.js'), f.name, str(dossier)], capture_output=True, text=True,
                           env={**os.environ, 'MERMAID_JS': mermaid_js})
    except FileNotFoundError:
        return f'{len(liste)} schéma(s) non dessiné(s) : Node introuvable (Node + Playwright requis)'
    finally:
        os.unlink(f.name)
    if r.returncode:
        return 'schemas.js : ' + (r.stderr or r.stdout).strip()
    return None


def figure(cle_schema, code, etapes, survols, dossier, codes=None, genre='schema'):
    """<figure class="schema"> avec les deux SVG (et data-anim pour étapes / infobulles / code), ou le texte du
    schéma s'il n'est pas dessiné. codes = {noeud: {'html', 'de', 'a'}} (schemas_code.relier) : panneaux du code,
    ouverts au clic sur la boîte ou par une étape. genre : schema (écrit à la main), organigramme ou carte ; avec les
    cibles des boîtes (« fichier:fonction »), il permet à une fiche de module de mener au schéma d'une fonction."""
    clair, sombre = fichiers_svg(cle_schema, dossier)
    codes = codes or {}
    panneaux = ''.join(f'<div class="schema-code" data-noeud="{html.escape(n)}" hidden>{c["html"]}</div>'
                       for n, c in codes.items())
    if not (clair.exists() and sombre.exists()):
        return f'<pre class="schema-texte">{html.escape(code)}</pre>{panneaux}'
    attrs, legende = '', legende_echanges(code)
    if etapes or survols or codes:
        anim = {'etapes': etapes, 'survols': survols, 'codes': {n: [c['de'], c['a']] for n, c in codes.items()},
                'cibles': {n: c['cible'] for n, c in codes.items() if c.get('cible')}}
        attrs = f' data-anim="{html.escape(json.dumps(anim))}" data-genre="{html.escape(genre)}"'
    # deux zones : le dessin (SVG, légende, barre des étapes) et le code, à droite sur un écran large (schemas.css)
    cote = f'<div class="schema-cote">{panneaux}</div>' if panneaux else ''
    return (f'<figure class="schema"{attrs}><div class="schema-dessin">'
            f'<div class="clair">{clair.read_text(encoding="utf-8")}</div>'
            f'<div class="sombre">{sombre.read_text(encoding="utf-8")}</div>{legende}</div>{cote}</figure>')


def legende_echanges(code):
    """Légende des types d'échange utilisés (%% échange), dans l'ordre : trait + pictogramme + nom."""
    vus = []
    for t in RE_ECHANGE.findall(code):
        if t in ICONES['echanges'] and t not in vus:
            vus.append(t)
    if not vus:
        return ''
    items = []
    for t in vus:
        e = ICONES['echanges'][t]
        tirets = f' stroke-dasharray="{e["tirets"]}"' if e['tirets'] else ''
        dessin = e['svg'].replace("'", '"')
        items.append(f'<span><svg viewBox="0 0 52 20" width="52" height="20" aria-hidden="true" fill="none" '
                     f'stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">'
                     f'<path d="M2 10h28"{tirets} stroke-width="1.6"/>'
                     f'<g transform="translate(33 1) scale(.75)" stroke-width="1.9">{dessin}</g></svg>'
                     f'{html.escape(e["nom"])}</span>')
    return f'<div class="schema-legende">{"".join(items)}</div>'


def css():
    """Styles des schémas (variables --surface, --rule, --paper, --ink, --accent, --f-display de la page hôte)."""
    return (ICI / 'schemas.css').read_text(encoding='utf-8')


def js():
    """Script des étapes et infobulles (à placer dans un bloc <script>, après le contenu)."""
    return (ICI / 'schemas-anim.js').read_text(encoding='utf-8')


# ------------------------------------------------------------------ usage autonome
def genere(langue, arg, trouver):
    """Code Mermaid d'un bloc ```carte-code``` / ```organigramme-code``` (arg = « fichier [| options] »).
    Renvoie (code, erreurs)."""
    rel, _, reste = (x.strip() for x in arg.partition('|'))
    try:
        chemin = trouver(rel)
    except OSError as e:
        return '', [f'{langue} {rel} : {e}']
    if langue == 'carte-code':
        return schemas_code.carte(rel, chemin, reste)
    return schemas_code.organigramme(rel, chemin, reste)


BLOCS_GENERES = ('carte-code', 'organigramme-code')


def blocs_markdown(texte):
    """[(titre le plus proche au-dessus, code)] pour chaque bloc ```mermaid d'un Markdown ; un bloc
    ```carte-code …``` ou ```organigramme-code …``` donne (titre, ('carte-code', arg))."""
    out, titre = [], ''
    dans, code = False, []
    for ligne in texte.splitlines():
        m = re.match(r'^\s*```(carte-code|organigramme-code)\s+(.+?)\s*$', ligne)
        if not dans and m:
            dans, code = 'genere', (m.group(1), m.group(2))
        elif not dans and re.match(r'^\s*```mermaid\s*$', ligne):
            dans, code = True, []
        elif dans and re.match(r'^\s*```\s*$', ligne):
            out.append((titre, code if dans == 'genere' else '\n'.join(code)))
            dans = False
        elif dans is True:
            code.append(ligne)
        elif re.match(r'^#{1,6}\s', ligne):
            titre = re.sub(r'^#+\s*', '', ligne).strip()
    return out


def page(titre, schemas_html):
    modele = (ICI / 'page.html').read_text(encoding='utf-8')
    return (modele.replace('{{CSS}}', css()).replace('{{JS}}', js())
            .replace('{{TITRE}}', html.escape(titre)).replace('{{CONTENU}}', schemas_html))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Schémas Mermaid à main levée : page autonome ou SVG.')
    ap.add_argument('entree', help='fichier .mmd (un schéma) ou .md (tous ses blocs ```mermaid)')
    ap.add_argument('-o', '--sortie', help='page HTML à écrire (défaut : même nom, .html)')
    ap.add_argument('--svg', metavar='DOSSIER', help='seulement dessiner les SVG dans ce dossier')
    ap.add_argument('--titre', help='titre de la page (défaut : nom du fichier)')
    ap.add_argument('--racine', help='dossier des fichiers cités par « %% code » et les blocs générés '
                                     '(défaut : celui de l\'entrée)')
    a = ap.parse_args(argv)

    entree = Path(a.entree)
    texte = entree.read_text(encoding='utf-8')
    blocs = blocs_markdown(texte) if entree.suffix.lower() in ('.md', '.markdown') else [('', texte)]
    if not blocs:
        sys.exit(f'Aucun schéma dans {entree}')
    dossier = Path(a.svg) if a.svg else (Path(a.sortie) if a.sortie else entree.with_suffix('.html')).parent / 'schemas'
    racine = Path(a.racine) if a.racine else entree.parent
    sortie = Path(a.sortie) if a.sortie else entree.with_suffix('.html')

    def trouver(rel):
        f = racine / rel
        if not f.is_file():
            raise FileNotFoundError(f'fichier introuvable : {rel}')
        return f

    def lien(rel, de, a_):
        return os.path.relpath(racine / rel, sortie.parent).replace(os.sep, '/') + f'#L{de}-L{a_}'
    lus, erreurs = [], []
    for titre, code in blocs:
        genre = 'schema'
        if isinstance(code, tuple):
            genre = 'carte' if code[0] == 'carte-code' else 'organigramme'
            code, err = genere(*code, trouver)
            erreurs += err
            if not code:
                continue
        lu = lire(code)
        codes, err = schemas_code.relier(lu['liens'], lu['etapes'], lu['survols'], trouver, lien)
        erreurs += err
        lus.append((titre, cle(lu['code']), lu['code'], lu['etapes'], lu['survols'], codes, genre))
    erreur = dessiner([{'cle': k, 'code': c} for _, k, c, *_ in lus if not dessine(k, dossier)], dossier)
    if erreur:
        erreurs.append(erreur)
    for e in erreurs:
        print('ATTENTION :', e, file=sys.stderr)
    erreur = bool(erreurs)
    if a.svg:
        print(f'{len(lus)} schéma(s) dans {dossier}')
        return 1 if erreur else 0
    corps = ''.join((f'<h2>{html.escape(t)}</h2>' if t else '') + figure(k, c, e, s, dossier, cs, g)
                    for t, k, c, e, s, cs, g in lus)
    sortie.write_text(page(a.titre or entree.stem, corps), encoding='utf-8')
    print(f'{sortie} : {len(lus)} schéma(s) (SVG gardés dans {dossier})')
    return 1 if erreur else 0


if __name__ == '__main__':
    sys.exit(main())
