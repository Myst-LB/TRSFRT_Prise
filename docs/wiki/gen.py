#!/usr/bin/env python3
"""Génère docs/wiki.html, le wiki du projet en UN fichier autonome, à partir de docs/WIKI.md.
Outil du skill docs-wiki (dépôt Myst-skills) : copié dans docs/wiki/ de chaque projet par installer_wiki.py ;
ne pas le modifier dans un projet (le corriger dans Myst-skills, puis réinstaller).

    pip install markdown-it-py mdit-py-plugins Pillow
    python docs/wiki/gen.py

On modifie toujours docs/WIKI.md (et les images de docs/img/), jamais le HTML, puis on relance ce script.
À côté, docs/wiki/etat.json (généré) résume le wiki pour le Hub : session, à valider, étapes, ATTENTION, titres.

Le Markdown est du Markdown normal (lisible sur GitHub), plus quelques blocs spéciaux :

    ```mermaid            schéma, dessiné en SVG (clair + sombre, trait à main levée) et gardé dans docs/wiki/schemas/ ;
                          lignes « %% survol ID : texte » et « %% étape Titre : texte | ID ID A->B » ; classes
                          :::accent, :::donnee, :::externe, :::alerte, :::discret (skill schemas-main-levee)
                          « %% code C : fichier.py | def f( » relie la boîte C au vrai code (clic = code, repère
                          vérifié) ; « %% étape T : texte | C | C : début .. fin » surligne ces lignes à l'étape
    ```carte-code f.py    carte du module (qui appelle qui), générée ; options « | depuis main | sans _prives »
    ```organigramme-code f.py | fonction    organigramme d'une fonction COURTE, généré
    ```extrait            un extrait du VRAI code : « chemin | début | fin » (fin exclue) ou « chemin | début | n=12 »
    ```valider            liste « - … » de points à valider : cases à cocher, progression en tête de page
    ```fichiers           tableau « chemin | rôle » avec liens vers les fichiers du dépôt
    ```cartes             rangée de cartes : une ligne « icône | titre | lien | description » (description facultative) ;
                          icône = pictogramme de icones.json, lien = « #ancre » ou chemin relatif
    ```onglets            un fichier par onglet : une ligne = l'argument d'un ```extrait (« chemin | début | fin »)
    ```chiffres           tuiles de chiffres clés : une ligne « valeur | libellé | précision » par tuile
    > [!NOTE]             encadré par type (syntaxe des alertes GitHub) : NOTE, TIP, IMPORTANT, WARNING, CAUTION
    ```bloc nom           insère docs/wiki/blocs/nom.html (HTML + style + script propres au projet, ex. une démo)
    ![légende](img/x.png "large")   capture (cliquer = agrandir) ; plusieurs captures d'un paragraphe = grille

Réglages de docs/wiki/wiki.json lus ici : titre, surtitre, cle, liens, hors_depot, accent, source, sortie, et (3.3.0)
« projet » (nom dans le pied de page, défaut : dossier racine) et « portail » (lien relatif « Retour au portail »).

Les schémas viennent du skill schemas-main-levee : docs/wiki/schemas.py (lecture des annotations, dessin, figure),
schemas.js (Node + Playwright + Mermaid 11.17.2 du skill), schemas.css et schemas-anim.js (insérés dans la page).
Sans Node ou sans Mermaid, le texte du schéma reste affiché ; les schémas déjà dessinés sont réutilisés.
"""
import base64
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import unquote

try:
    from markdown_it import MarkdownIt
except ImportError:
    sys.exit('Module manquant : pip install markdown-it-py')

VERSION_DOCS_WIKI = '3.4.0'   # = skills/docs-wiki/VERSION de Myst-skills (vérifié par test/test_docs_wiki.sh)
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parent.parent
# Réglages du projet : docs/wiki/wiki.json (titre, surtitre, cle, liens, hors_depot, accent), voir le skill docs-wiki
try:
    CONFIG = json.loads((DOSSIER / 'wiki.json').read_text(encoding='utf-8'))
except FileNotFoundError:
    CONFIG = {}
SOURCE = RACINE / CONFIG.get('source', 'docs/WIKI.md')
SORTIE = RACINE / CONFIG.get('sortie', 'docs/wiki.html')
SCHEMAS = DOSSIER / 'schemas'
BLOCS = DOSSIER / 'blocs'
# Liens « fichier » et « extrait » : relatifs au dépôt local par défaut (wiki.html est dans docs/), donc lisibles
# sans forge ; WIKI_LIENS (ou « liens » dans wiki.json) = https://forge…/blob/main/ pour pointer vers une forge.
GH = os.environ.get('WIKI_LIENS', CONFIG.get('liens', '../'))
# Fichiers hors dépôt cités par les extraits : {"nom": {"chemin": "docs/wiki/copie/x.js", "origine": "autre-projet"}}
HORS_DEPOT = {nom: (RACINE / v['chemin'], v.get('origine', 'hors dépôt'))
              for nom, v in CONFIG.get('hors_depot', {}).items()}

sys.path.insert(0, str(DOSSIER))
from couleurs import colorer  # noqa: E402
import schemas  # noqa: E402  (skill schemas-main-levee, copié dans docs/wiki/ par installer_wiki.py)

ERREURS = []
# Couleur d'accent du projet (« accent » de wiki.json) : un nom de palette du modèle, ou #rrggbb. Le lecteur peut
# en choisir une autre dans la fenêtre « Apparence » de la page (mémorisée dans son navigateur).
PALETTES = ('indigo', 'emeraude', 'violet', 'ambre', 'rose', 'cyan', 'ardoise')


def accent():
    valeur = str(CONFIG.get('accent', '')).strip().lower()
    if valeur and valeur not in PALETTES and not re.fullmatch(r'#[0-9a-f]{6}', valeur):
        ERREURS.append(f'wiki.json : accent « {valeur} » inconnu (palettes : {", ".join(PALETTES)}, ou #rrggbb) ; indigo utilisé')
        return ''
    return valeur


# ------------------------------------------------------------------ outils
def slug(texte):
    """Ancre lisible, accents gardés : « 3. Utiliser NetBox » -> 3-utiliser-netbox."""
    texte = unicodedata.normalize('NFC', html.unescape(re.sub(r'<[^>]+>', '', texte))).lower()
    return re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', texte).strip())


LANGUES = {'python': 'py', 'py': 'py', 'javascript': 'js', 'js': 'js', 'json': 'js', 'powershell': 'ps1',
           'ps1': 'ps1', 'bash': 'ps1', 'sh': 'ps1', 'yaml': 'ps1', 'yml': 'ps1'}
NOMS_LANGUES = {'py': 'Python', 'js': 'JavaScript', 'ps1': 'PowerShell', 'html': 'HTML'}


def colorer_jinja(texte):
    """Jinja / Django : balises {% %} et {{ }} colorées, le reste (CLI Cisco) tel quel."""
    morceaux = re.split(r'(\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\})', texte, flags=re.S)
    out = []
    for m in morceaux:
        if m.startswith('{#'):
            out.append(f'<span class="cm">{html.escape(m)}</span>')
        elif m.startswith('{%'):
            out.append('<span class="kw">' + html.escape(m) + '</span>')
        elif m.startswith('{{'):
            out.append('<span class="va">' + html.escape(m) + '</span>')
        else:
            out.append(re.sub(r'^(\s*!.*)$', r'<span class="cm">\1</span>', html.escape(m), flags=re.M))
    return ''.join(out)


def code_colore(texte, langue):
    langue = (langue or '').lower()
    if langue in ('jinja', 'django', 'j2'):
        return colorer_jinja(texte)
    if langue in LANGUES:
        return colorer(texte, LANGUES[langue])
    return html.escape(texte)


def gouttiere(nb, depart=1):
    """Numéros de ligne (3.3.0) : colonne à part, hors de <code> (ni copiée ni cherchée), un numéro par ligne du
    code ; depart = numéro de la première ligne (extrait : vraie ligne du fichier)."""
    return ('<span class="nums" aria-hidden="true">' + '\n'.join(str(depart + k) for k in range(nb)) + '</span>')


def bloc_code(corps_html, legende='', cible='', nb=0, depart=1, langue=''):
    """<figure class="code"> ; avec nb >= 2 lignes, une gouttière de numéros commençant à « depart »."""
    tete = f'<figcaption>{legende}</figcaption>' if legende else ''
    attr = f' data-cible="{html.escape(cible)}"' if cible else ''   # « fichier:fonction » : destination d'une fiche
    attr += f' data-langue="{html.escape(langue)}"' if langue else ''
    if nb >= 2:
        return (f'<figure class="code"{attr}>{tete}<pre class="num">{gouttiere(nb, depart)}'
                f'<code>{corps_html}</code></pre></figure>\n')
    return f'<figure class="code"{attr}>{tete}<pre><code>{corps_html}</code></pre></figure>\n'


# ------------------------------------------------------------------ blocs spéciaux
def extrait(arg):
    """« chemin | début | fin » : lignes du vrai fichier depuis la première qui contient début, jusqu'à fin (exclue)."""
    parts = [p.strip() for p in arg.split('|')]
    rel, debut = parts[0], parts[1]
    fin = parts[2] if len(parts) > 2 else 'n=20'
    chemin = HORS_DEPOT[rel][0] if rel in HORS_DEPOT else RACINE / rel
    try:
        ls = chemin.read_text(encoding='utf-8-sig').replace('\r', '').split('\n')
        i = next(k for k, l in enumerate(ls) if debut in l)
        if fin.startswith('n='):
            j = i + int(fin[2:])
        else:
            j = next(k for k in range(i + 1, len(ls)) if fin in ls[k])
    except (OSError, StopIteration) as e:
        ERREURS.append(f'extrait introuvable : {arg} ({type(e).__name__})')
        return f'<p class="erreur">Extrait introuvable : <code>{html.escape(arg)}</code></p>'
    bloc = ls[i:j]
    while bloc and not bloc[-1].strip():
        bloc.pop()
    ext = rel.rsplit('.', 1)[-1]
    langue = {'js': 'js', 'ps1': 'ps1', 'html': 'jinja', 'j2': 'jinja'}.get(ext, 'py')
    corps = colorer_jinja('\n'.join(bloc)) if langue == 'jinja' else colorer('\n'.join(bloc), langue)
    lignes = f'lignes {i + 1}–{i + len(bloc)}'
    if rel in HORS_DEPOT:
        legende = f'<span>{rel} ({html.escape(HORS_DEPOT[rel][1])}, hors dépôt) · {lignes}</span>'
    else:
        legende = (f'<a href="{GH}{rel}#L{i + 1}-L{i + len(bloc)}" target="_blank" rel="noopener">'
                   f'{rel} · {lignes}</a>')
    return bloc_code(corps, legende, schemas.schemas_code.cible(rel, ls[i]), nb=len(bloc), depart=i + 1)


COMPTEUR = {'n': 0}


def valider(texte, md):
    items, courant = [], None
    for ligne in texte.split('\n'):
        if ligne.startswith('- '):
            courant = [ligne[2:]]
            items.append(courant)
        elif ligne.strip() and courant is not None:
            courant.append(ligne.strip())
    lis = []
    for it in items:
        COMPTEUR['n'] += 1
        i = 'v' + hashlib.sha1(' '.join(it).encode()).hexdigest()[:8]   # stable : la case reste cochée après régénération
        lis.append(f'<li><input type="checkbox" id="{i}" class="v"><label for="{i}">{md.renderInline(" ".join(it))}</label></li>')
    total = len(lis)
    # barre « n / m validés » du bloc (3.3.0) : remplie par la fonction maj() du script de la page
    barre = (f'<div class="avalider-barre"><span class="avalider-jauge" role="progressbar" aria-label="Points validés" '
             f'aria-valuemin="0" aria-valuemax="{total}" aria-valuenow="0"><i></i></span>'
             f'<span class="avalider-texte"><b class="avalider-faits">0</b> / {total} validés</span></div>')
    return '<div class="avalider"><h4>À valider</h4>' + barre + '<ul>' + ''.join(lis) + '</ul></div>\n'


def lien_carte(lien):
    """Lien d'une carte : (« #ancre » | chemin relatif | http(s) | None, message d'erreur ou ''). Refuse les schémas
    qui exécutent ou embarquent du code (javascript:, data:, vbscript:…), « // » (hôte implicite) et tout schéma
    autre que http(s) ; les caractères de contrôle et espaces sont retirés avant le contrôle (« java\\tscript: »)."""
    lien = lien.strip()
    if not lien:
        return None, ''
    nu = re.sub(r'[\x00-\x20]', '', lien).lower()
    if nu.startswith('#'):
        return lien, ''
    if nu.startswith('//') or nu.startswith('\\'):
        return None, f'lien « {lien} » refusé (« // » ou « \\ » au début : hôte implicite)'
    m = re.match(r'^([a-z][a-z0-9+.-]*):', nu)
    if m and m.group(1) not in ('http', 'https'):
        return None, f'lien « {lien} » refusé (schéma « {m.group(1)}: » non permis ; http, https, « #ancre » ou chemin relatif)'
    return lien, ''


def icone_svg(nom):
    """Pictogramme de icones.json (équipements ou échanges, dessin 24 x 24) : balise <svg>, ou None."""
    for categorie in ('equipements', 'echanges'):
        d = schemas.ICONES.get(categorie, {}).get(nom)
        if isinstance(d, dict) and d.get('svg'):
            return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">{d["svg"]}</svg>'
    return None


LIENS_CARTES = {}   # n -> (ancre, ligne) : « #ancre » à vérifier une fois les titres calculés


def cartes(texte, md):
    """Rangée de cartes : « icône | titre | lien | description » par ligne (description facultative).
    Icône = pictogramme de icones.json (inconnu : ATTENTION, carte sans icône) ; lien = « #ancre » (vérifiée après le
    calcul des titres) ou chemin relatif ; un lien refusé donne une carte sans lien (ATTENTION)."""
    out = []
    for ligne in texte.strip().split('\n'):
        if not ligne.strip():
            continue
        icone, titre, lien, description = ([x.strip() for x in ligne.split('|', 3)] + ['', '', '', ''])[:4]
        if not titre:
            ERREURS.append(f'cartes : ligne « {ligne.strip()} » sans titre (attendu : icône | titre | lien | description)')
            continue
        svg = icone_svg(icone) if icone else None
        if icone and not svg:
            ERREURS.append(f'cartes : icône inconnue « {icone} » (pictogrammes de icones.json) ; carte sans icône')
        href, erreur = lien_carte(lien)
        if erreur:
            ERREURS.append(f'cartes : {erreur} ; carte sans lien')
        nom = html.escape(titre)
        if href and href.startswith('#'):
            n = len(LIENS_CARTES) + 1
            LIENS_CARTES[n] = (href[1:], ligne.strip())
            nom = f'<!--CL:{n}-->{nom}<!--/CL:{n}-->'
        elif href:
            ext = ' target="_blank" rel="noopener noreferrer"' if re.match(r'(?i)https?:', href) else ''
            nom = f'<a class="carte-lien" href="{html.escape(href)}"{ext}>{nom}</a>'
        ico = f'<span class="carte-ico">{svg}</span>' if svg else ''
        desc = f'<p>{md.renderInline(description)}</p>' if description else ''
        out.append(f'<div class="carte{" avec-ico" if svg else ""}">{ico}<div class="carte-corps">'
                   f'<b class="carte-titre">{nom}</b>{desc}</div></div>')
    return f'<div class="cartes">{"".join(out)}</div>\n'


def verifier_cartes(page):
    """Après le calcul des titres : « #ancre » connue -> <a>, inconnue -> ATTENTION et carte sans lien."""
    ids = set(re.findall(r'\bid="([^"]+)"', page))

    def un(m):
        ancre, ligne = LIENS_CARTES.get(int(m.group(1)), ('', ''))
        if ancre in ids or unquote(ancre) in ids:
            return f'<a class="carte-lien" href="#{html.escape(ancre)}">{m.group(2)}</a>'
        ERREURS.append(f'cartes : ancre « #{ancre} » inconnue (ligne « {ligne} ») ; carte sans lien')
        return m.group(2)
    return re.sub(r'<!--CL:(\d+)-->(.*?)<!--/CL:\1-->', un, page)


COMPTEUR_ONGLETS = {'n': 0}


def onglets(texte):
    """Un fichier par ligne, chaque ligne = argument d'un ```extrait ; tablist ARIA, un seul panneau visible.
    Ids stables : onglets-<n>, onglets-<n>-t<i> (onglet), onglets-<n>-p<i> (panneau)."""
    lignes = [l.strip() for l in texte.strip().split('\n') if l.strip()]
    if not lignes:
        ERREURS.append('onglets : bloc vide (attendu : une ligne « chemin | début | fin » par fichier)')
        return '<p class="erreur">Onglets : bloc vide</p>\n'
    COMPTEUR_ONGLETS['n'] += 1
    base = f'onglets-{COMPTEUR_ONGLETS["n"]}'
    tabs, panneaux = [], []
    for i, ligne in enumerate(lignes):
        nom = ligne.split('|')[0].strip().replace('\\', '/').rsplit('/', 1)[-1] or f'fichier {i + 1}'
        actif = i == 0
        tabs.append(f'<button type="button" role="tab" id="{base}-t{i}" aria-controls="{base}-p{i}" '
                    f'aria-selected="{"true" if actif else "false"}" tabindex="{0 if actif else -1}">{html.escape(nom)}</button>')
        panneaux.append(f'<div role="tabpanel" id="{base}-p{i}" aria-labelledby="{base}-t{i}" tabindex="0"'
                        f'{"" if actif else " hidden"}>{extrait(ligne)}</div>')
    return (f'<div class="onglets-code" id="{base}"><div role="tablist" aria-label="Fichiers">{"".join(tabs)}</div>'
            f'{"".join(panneaux)}</div>\n')


def fichiers(texte, md):
    lignes = []
    for ligne in texte.strip().split('\n'):
        chemin, _, role = (x.strip() for x in ligne.partition('|'))
        lien = (f'<a href="{GH}{chemin}" target="_blank" rel="noopener"><code>{html.escape(chemin)}</code></a>'
                if (RACINE / chemin).exists() else f'<code>{html.escape(chemin)}</code>')
        lignes.append(f'<tr><td>{lien}</td><td>{md.renderInline(role)}</td></tr>')
    return f'<div class="tbl"><table class="files"><tbody>{"".join(lignes)}</tbody></table></div>\n'


def chiffres(texte, md):
    """Tuiles de chiffres clés : « valeur | libellé | précision » (précision facultative), une ligne par tuile."""
    tuiles = []
    for ligne in texte.strip().split('\n'):
        if not ligne.strip():
            continue
        valeur, libelle, precision = ([x.strip() for x in ligne.split('|', 2)] + ['', ''])[:3]
        if not libelle:
            ERREURS.append(f'chiffres : ligne « {ligne.strip()} » sans libellé (attendu : valeur | libellé | précision)')
        tuiles.append(f'<div><dt>{md.renderInline(libelle)}</dt><dd>{md.renderInline(valeur)}</dd>'
                      + (f'<dd class="precision">{md.renderInline(precision)}</dd>' if precision else '') + '</div>')
    return f'<dl class="chiffres">{"".join(tuiles)}</dl>\n'


# Encadrés par type : syntaxe des alertes GitHub (« > [!NOTE] »), lisible aussi sur une forge.
ENCADRES = {'NOTE': ('info', 'Info'), 'TIP': ('astuce', 'Astuce'), 'IMPORTANT': ('important', 'Important'),
            'WARNING': ('attention', 'Attention'), 'CAUTION': ('danger', 'Danger')}


def encadres(page):
    def un(m):
        classe, nom = ENCADRES[m.group(1)]
        return f'<blockquote class="note t-{classe}"><p class="tete">{nom}</p><p>'
    page = re.sub(r'<blockquote class="note">\s*<p>\[!(' + '|'.join(ENCADRES) + r')\]\s*', un, page)
    return page.replace('<p></p>', '')


def bloc(nom):
    """Contenu de docs/wiki/blocs/<nom>.html, inséré tel quel (démo interactive propre au projet)."""
    f = BLOCS / f'{nom}.html'
    if not nom or not f.is_file():
        ERREURS.append(f'bloc introuvable : docs/wiki/blocs/{nom}.html')
        return f'<p class="erreur">Bloc introuvable : <code>{html.escape(nom)}</code></p>'
    return f.read_text(encoding='utf-8') + '\n'


SCHEMAS_A_DESSINER = []


def trouver(rel):
    """Fichier cité par un schéma (%% code, carte-code, organigramme-code) : dépôt, ou hors_depot de wiki.json."""
    chemin = HORS_DEPOT[rel][0] if rel in HORS_DEPOT else RACINE / rel
    if not chemin.is_file():
        raise FileNotFoundError(f'fichier introuvable : {rel}')
    return chemin


def lien_code(rel, de, a):
    return f'{GH}{rel}#L{de}-L{a}' if rel not in HORS_DEPOT else ''


def schema(code, genre='schema'):
    lu = schemas.lire(code)
    code, etapes, survols = lu['code'], lu['etapes'], lu['survols']
    codes, erreurs = schemas.schemas_code.relier(lu['liens'], etapes, survols, trouver, lien_code)
    ERREURS.extend(erreurs)
    cle = schemas.cle(code)
    if not schemas.dessine(cle, SCHEMAS):
        SCHEMAS_A_DESSINER.append({'cle': cle, 'code': code})
    donnees = base64.b64encode(json.dumps({'code': code, 'etapes': etapes, 'survols': survols,
                                           'codes': codes, 'genre': genre}).encode()).decode()
    return f'<!--SCHEMA:{cle}:{donnees}-->'


def schema_genere(langue, arg):
    """```carte-code fichier.py [| options]``` ou ```organigramme-code fichier.py | fonction``` : Mermaid généré
    depuis le code (schemas_code.py), puis dessiné comme un schéma écrit à la main."""
    code, erreurs = schemas.genere(langue, arg, trouver)
    ERREURS.extend(erreurs)
    if not code:
        return f'<p class="erreur">{html.escape(langue)} impossible : <code>{html.escape(arg)}</code></p>'
    return schema(code, 'carte' if langue == 'carte-code' else 'organigramme')


def dessiner_schemas():
    erreur = schemas.dessiner(SCHEMAS_A_DESSINER, SCHEMAS)
    if erreur:
        ERREURS.append(erreur)
    else:
        SCHEMAS_A_DESSINER.clear()


def inserer_schemas(page):
    utilises = set()

    def un(m):
        cle, d = m.group(1), json.loads(base64.b64decode(m.group(2)).decode())
        if schemas.dessine(cle, SCHEMAS):
            utilises.update(f.name for f in schemas.fichiers_svg(cle, SCHEMAS))
        return schemas.figure(cle, d['code'], d['etapes'], d['survols'], SCHEMAS, d.get('codes'), d.get('genre', 'schema'))
    page = re.sub(r'<!--SCHEMA:([0-9a-f]+):([A-Za-z0-9+/=]+)-->', un, page)
    # Schémas qui ne servent plus (code modifié ou supprimé) : effacés, pour ne pas encombrer le dépôt
    for f in SCHEMAS.glob('*.svg'):
        if f.name not in utilises and not SCHEMAS_A_DESSINER:
            f.unlink()
    return page


# ------------------------------------------------------------------ images
CACHE_IMG = {}


def data_uri(rel):
    if rel in CACHE_IMG:
        return CACHE_IMG[rel]
    chemin = (SOURCE.parent / rel).resolve()
    if not chemin.is_file():
        ERREURS.append(f'image introuvable : {rel}')
        return rel
    brut, mime = chemin.read_bytes(), 'image/png' if chemin.suffix == '.png' else 'image/jpeg'
    try:   # captures en JPEG, 1600 px de large au plus : le fichier reste léger
        from PIL import Image
        im = Image.open(io.BytesIO(brut)).convert('RGB')
        if im.width > 1600:
            im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
        tampon = io.BytesIO()
        im.save(tampon, 'JPEG', quality=80, optimize=True, progressive=True)
        if tampon.tell() < len(brut):
            brut, mime = tampon.getvalue(), 'image/jpeg'
    except ImportError:
        pass
    CACHE_IMG[rel] = f'data:{mime};base64,' + base64.b64encode(brut).decode()
    return CACHE_IMG[rel]


# ------------------------------------------------------------------ rendu Markdown
def creer_md():
    md = MarkdownIt('commonmark', {'html': True}).enable('table').enable('strikethrough')
    try:   # cases « - [ ] » des listes de tâches (facultatif)
        from mdit_py_plugins.tasklists import tasklists_plugin
        md.use(tasklists_plugin)
    except ImportError:
        pass

    def fence(self, tokens, idx, options, env):
        t = tokens[idx]
        langue, _, arg = t.info.strip().partition(' ')
        if langue == 'mermaid':
            return schema(t.content)
        if langue in schemas.BLOCS_GENERES:
            return schema_genere(langue, arg.strip() or t.content.strip())
        if langue == 'extrait':
            return extrait(arg or t.content.strip())
        if langue == 'valider':
            return valider(t.content, md)
        if langue == 'fichiers':
            return fichiers(t.content, md)
        if langue == 'cartes':
            return cartes(t.content, md)
        if langue == 'onglets':
            return onglets(t.content)
        if langue == 'chiffres':
            return chiffres(t.content, md)
        if langue == 'bloc':
            return bloc(arg.strip())
        brut = t.content.rstrip('\n')
        corps = code_colore(brut, langue)
        etiquette = {'py': 'Python', 'js': 'JavaScript', 'ps1': 'PowerShell'}.get(LANGUES.get(langue.lower()), langue)
        return bloc_code(corps, nb=brut.count('\n') + 1, langue=etiquette)

    def image(self, tokens, idx, options, env):
        t = tokens[idx]
        src, legende = t.attrGet('src'), md.renderer.renderInlineAsText(t.children or [], options, env)
        large = ' large' if (t.attrGet('title') or '') == 'large' else ''
        donnees = data_uri(src)
        return (f'<figure class="shot{large}"><button class="zoom" type="button" aria-label="Agrandir : {html.escape(legende)}">'
                f'<img src="{donnees}" alt="{html.escape(legende)}" loading="lazy"></button>'
                f'<figcaption>{html.escape(legende)}</figcaption></figure>')

    md.add_render_rule('fence', fence)
    md.add_render_rule('image', image)
    return md


def titres(page):
    """Ancres sur h1-h3 (uniques), et liste (niveau, id, texte) pour le sommaire."""
    vus, liste = {}, []

    def un(m):
        niveau, contenu = int(m.group(1)), m.group(2)
        base = slug(contenu) or 'section'
        vus[base] = vus.get(base, 0) + 1
        ident = base if vus[base] == 1 else f'{base}-{vus[base]}'
        liste.append((niveau, ident, re.sub(r'<[^>]+>', '', contenu)))
        return f'<h{niveau} id="{ident}">{contenu}</h{niveau}>'
    page = re.sub(r'<h([1-3])>(.*?)</h\1>', un, page)
    return page, liste


def mise_en_page(page):
    page = re.sub(r'<p>((?:\s*<figure class="shot[^"]*">.*?</figure>\s*)+)</p>', r'<div class="shots">\1</div>', page, flags=re.S)
    page = re.sub(r'(<table>.*?</table>)', r'<div class="tbl">\1</div>', page, flags=re.S)
    page = re.sub(r'(</h1>\s*)<p>', r'\1<p class="lead">', page)
    page = page.replace('<blockquote>', '<blockquote class="note">')
    return encadres(page)


def decouper(page, liste):
    """Intro (avant le premier h1) + une <section> par partie (h1)."""
    morceaux = re.split(r'(?=<h1 id=")', page)
    intro, parties = morceaux[0], morceaux[1:]
    # titre du wiki (premier « # » non numéroté) + texte d'accueil = l'intro ; les parties sont « # 1. … »
    if parties and liste and liste[0][0] == 1 and not re.match(r'\s*\d', liste[0][2]):
        titre_id = liste[0][1]
        intro += re.sub(r'^<h1[^>]*>.*?</h1>', '', parties.pop(0), flags=re.S)
        liste = [x for x in liste if x[1] != titre_id]
    corps = ''.join(f'<section class="partie">{p}</section>' for p in parties)
    toc, ouvert = [], False
    for niveau, ident, texte in liste:
        if niveau == 1:
            if ouvert:
                toc.append('</ol></li>')
            toc.append(f'<li class="p"><a href="#{ident}">{html.escape(texte)}</a><ol>')
            ouvert = True
        elif niveau == 2 and ouvert:
            toc.append(f'<li><a href="#{ident}">{html.escape(texte)}</a></li>')
    if ouvert:
        toc.append('</ol></li>')
    return intro, corps, ''.join(toc)


# ------------------------------------------------------------------ pied de page, contributeurs, portail (3.3.0)
def contributeurs():
    """Noms des auteurs des commits de la source du wiki (git log, format %an : JAMAIS d'adresse électronique),
    triés par nombre de commits décroissant puis par nom. Liste vide, sans message, si git manque, si le dossier
    n'est pas un dépôt, si la commande échoue ou n'a rien à dire."""
    try:
        rel = SOURCE.relative_to(RACINE).as_posix()
        r = subprocess.run(['git', 'log', '--format=%an', '--', rel], cwd=str(RACINE), capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=10)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    noms = Counter(n.strip() for n in r.stdout.splitlines() if n.strip())
    return [n for n, _ in sorted(noms.items(), key=lambda x: (-x[1], x[0]))]


def pied():
    """Pied de la page : source, projet, version de docs-wiki, contributeurs s'il y en a."""
    projet = str(CONFIG.get('projet', '') or '').strip() or RACINE.name
    texte = f'Source : {SOURCE.relative_to(RACINE).as_posix()} · {projet} · docs-wiki {VERSION_DOCS_WIKI}'
    noms = contributeurs()
    if noms:
        texte += ' · Contributeurs : ' + ', '.join(noms)
    return f'<footer class="pied">{html.escape(texte)}</footer>'


def portail():
    """Lien « Retour au portail » (réglage « portail » de wiki.json : chemin RELATIF, ex. ../portail.html). Refusé
    (ATTENTION, pas de lien) s'il est absolu (/, \\, lettre de lecteur), s'il contient « : » (schéma) ou commence par //."""
    valeur = CONFIG.get('portail')
    if valeur is None or valeur == '':
        return ''
    if not isinstance(valeur, str):
        ERREURS.append('wiki.json : portail doit être un chemin relatif (texte) ; lien absent')
        return ''
    chemin = valeur.strip()
    if (not chemin or chemin.startswith(('/', '\\')) or ':' in chemin or re.search(r'[\x00-\x1f]', chemin)
            or re.match(r'^[A-Za-z]:', chemin)):
        ERREURS.append(f'wiki.json : portail « {valeur} » refusé (chemin relatif attendu, ex. ../portail.html) ; lien absent')
        return ''
    return (f'<a class="retour" href="{html.escape(chemin)}"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true">'
            f'<path d="M9.5 3.5 5 8l4.5 4.5"/></svg>Retour au portail</a>')


# ------------------------------------------------------------------ résumé pour le Hub (docs/wiki/etat.json)
# Règles de suivi : les MÊMES que hub/wikimd.py du dépôt Myst-LB/Hub (repli quand etat.json manque) ; test de
# parité dans le Hub (tests/test_j2b_etat_json.py). Blocs de code ignorés, sauf ```valider pour le compte.
FENCE_SUIVI = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
TITRE_SUIVI = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$')


def suivi(texte):
    """Dernière « Session du AAAA-MM-JJ » (titres) et cases « - [ ] » des sections « Prochaines étapes »."""
    session, etapes, niveau_etapes, ouvert = None, 0, None, None
    for ligne in texte.splitlines():
        m = FENCE_SUIVI.match(ligne)
        if ouvert:
            if m and m.group(1)[0] == ouvert[0] and len(m.group(1)) >= ouvert[1] and not m.group(2).strip():
                ouvert = None
            continue
        if m and not (m.group(1)[0] == '`' and '`' in m.group(2)):
            ouvert = (m.group(1)[0], len(m.group(1)))
            continue
        m = TITRE_SUIVI.match(ligne)
        if m:
            niveau, titre = len(m.group(1)), (m.group(2) or '').strip()
            for d in re.findall(r'Session du (\d{4}-\d{2}-\d{2})', titre):
                session = max(session or d, d)
            if niveau_etapes is not None and niveau <= niveau_etapes:
                niveau_etapes = None
            if titre.lower().startswith('prochaines étapes'):
                niveau_etapes = niveau
        elif niveau_etapes is not None and re.match(r'^\s*[-*+] \[ \]', ligne):
            etapes += 1
    return session, etapes


def ecrire_etat(texte, liste, titre):
    """docs/wiki/etat.json : ce que le Hub affiche d'un wiki, sans relancer ce script ni markdown-it."""
    session, etapes = suivi(texte)
    etat = {'titre': titre, 'genere_le': date.today().isoformat(), 'docs_wiki': VERSION_DOCS_WIKI, 'derniere_session': session,
            'a_valider': COMPTEUR['n'], 'etapes_ouvertes': etapes, 'attention': len(ERREURS),
            'parties': sum(1 for n, _, t in liste if n == 1 and re.match(r'\s*\d', t)),
            'titres': [{'niveau': n, 'id': i, 'texte': html.unescape(t)} for n, i, t in liste]}
    (DOSSIER / 'etat.json').write_text(json.dumps(etat, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    md = creer_md()
    texte = SOURCE.read_text(encoding='utf-8')
    page = md.render(texte)
    dessiner_schemas()
    page = inserer_schemas(page)
    page, liste = titres(page)
    page = verifier_cartes(page)
    page = mise_en_page(page)
    intro, corps, toc = decouper(page, liste)
    modele = ((DOSSIER / 'modele.html').read_text(encoding='utf-8')
              .replace('{{SCHEMAS_CSS}}', schemas.css()).replace('{{SCHEMAS_JS}}', schemas.js()))
    titre = CONFIG.get('titre', 'Wiki')
    sortie = (modele.replace('{{PORTAIL}}', portail()).replace('{{PIED}}', pied())
              .replace('{{TITRE}}', html.escape(titre)).replace('{{SURTITRE}}', html.escape(CONFIG.get('surtitre', '')))
              .replace('{{CLE}}', re.sub(r'[^a-z0-9-]+', '-', CONFIG.get('cle', titre).lower()))
              .replace('{{ACCENT}}', accent())
              .replace('{{MINUTES}}', str(max(1, round(len(re.findall(r'\w+', re.sub(r'<[^>]+>', ' ', intro + corps))) / 220))))
              .replace('{{PARTIES}}', str(sum(1 for n, _, t in liste if n == 1 and re.match(r'\s*\d', t))))
              .replace('{{TOC}}', toc).replace('{{INTRO}}', intro).replace('{{CORPS}}', corps)
              .replace('{{TOTAL}}', str(COMPTEUR['n'])).replace('{{DATE}}', date.today().isoformat()))
    SORTIE.write_text(sortie, encoding='utf-8')
    ecrire_etat(texte, liste, titre)
    for e in ERREURS:
        print('ATTENTION :', e, file=sys.stderr)
    print(f'{SORTIE.relative_to(RACINE)} : {SORTIE.stat().st_size // 1024} Ko, '
          f'{sum(1 for n, _, t in liste if n == 1 and re.match(r'\s*\d', t))} parties, {COMPTEUR["n"]} points à valider')
    return 1 if ERREURS else 0


if __name__ == '__main__':
    sys.exit(main())
