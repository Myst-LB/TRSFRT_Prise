"""Schémas reliés au code : outil du skill schemas-main-levee (dépôt Myst-skills), utilisé par schemas.py et par
le gen.py du skill docs-wiki. Bibliothèque standard seulement.

Trois usages :

1. Relier un schéma écrit à la main au vrai code (lignes « %% », lues par schemas.lire()) :

       %% code C : check_backups.py | def classify(           boîte C reliée à la fonction (bloc par indentation)
       %% code C : check_backups.py | def classify( | n=30    … ou 30 lignes, ou « | repère de fin » (fin exclue)
       %% code M : controle/parcours.py                      fiche du module : rôle (docstring) + ses fonctions
       %% étape Tri : on écarte les liens | C | C : islink .. continue
                                                  l'étape surligne, dans le code de C, de la ligne qui contient
                                                  « islink » à celle qui contient « continue » (incluse)

   relier() vérifie chaque repère (sinon une erreur, donc « ATTENTION ») et prépare le panneau de code (clic sur la
   boîte, ou étape qui le surligne) et l'infobulle par défaut (signature + fichier + lignes).

2. carte(fichier) : carte d'un module Python (fonctions, qui appelle qui), en Mermaid, chaque boîte reliée à sa
   fonction. Options : « depuis main », « profondeur=1 » (avec depuis), « sans _prives », « max=12 ».

3. organigramme(fichier, fonction) : organigramme d'une fonction Python COURTE (if / for / while / try / return /
   raise), en Mermaid, infobulle = code et ligne de chaque boîte. Fonction trop longue : refusée (erreur).

Les deux derniers produisent du code Mermaid annoté, dessiné ensuite comme tout autre schéma.
"""
import ast
import html
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
# Coloration du skill docs-wiki : à côté (projet : docs/wiki/) ou dans le skill voisin (Myst-skills, installé)
for _d in (ICI, ICI.parent.parent / 'docs-wiki' / 'outil'):
    if (_d / 'couleurs.py').is_file() and str(_d) not in sys.path:
        sys.path.append(str(_d))
try:
    from couleurs import colorer as _colorer
except ImportError:   # schemas-main-levee seul : code affiché sans couleurs
    _colorer = None

RE_CODE = re.compile(r'^\s*%%\s*code\s+([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*$')
MAX_CARTE = 12          # boîtes d'une carte de module au-delà desquelles on demande de filtrer
MAX_ORGANIGRAMME = 22   # boîtes d'un organigramme : au-delà, la fonction n'est pas « courte »
LONGUEUR_LIBELLE = 38
LONGUEUR_CONDITION = 24  # losange : la forme grandit avec le texte


# ------------------------------------------------------------------ lecture du vrai fichier
def _langue(rel):
    """Langue de couleurs.py, ou None (texte sans couleurs : HTML, Jinja, Markdown…)."""
    ext = rel.rsplit('.', 1)[-1].lower()
    return {'py': 'py', 'js': 'js', 'mjs': 'js', 'ps1': 'ps1', 'sh': 'ps1', 'bash': 'ps1'}.get(ext)


def _bloc(ls, i):
    """Fin (exclue) du bloc qui commence à la ligne i : lignes plus indentées (ou vides) qui suivent, plus la
    accolade / parenthèse fermante au même retrait (JS). Bloc d'une ligne : la ligne seule."""
    retrait = len(ls[i]) - len(ls[i].lstrip())
    j = i + 1
    while j < len(ls) and (not ls[j].strip() or len(ls[j]) - len(ls[j].lstrip()) > retrait):
        j += 1
    if j < len(ls) and ls[j].strip()[:1] in '})]' and len(ls[j]) - len(ls[j].lstrip()) == retrait:
        j += 1
    while j > i + 1 and not ls[j - 1].strip():
        j -= 1
    return j


def lire_lignes(chemin):
    return Path(chemin).read_text(encoding='utf-8-sig').replace('\r', '').split('\n')


def situer(ls, debut, fin=''):
    """(i, j) des lignes [i, j) : première ligne qui contient debut, puis fin (exclue), « n=12 » ou le bloc."""
    i = next(k for k, l in enumerate(ls) if debut in l)
    if fin.startswith('n='):
        j = i + int(fin[2:])
    elif fin:
        j = next(k for k in range(i + 1, len(ls)) if fin in ls[k])
    else:
        j = _bloc(ls, i)
    while j > i + 1 and not ls[j - 1].strip():
        j -= 1
    return i, min(j, len(ls))


def _par_ligne(corps):
    """HTML coloré -> une <span class="l"> par ligne, en refermant / rouvrant les <span> qui chevauchent."""
    out, ouvertes = [], []
    for ligne in corps.split('\n'):
        tete = ''.join(ouvertes)
        for m in re.finditer(r'<span[^>]*>|</span>', ligne):
            if m.group().startswith('</'):
                if ouvertes:
                    ouvertes.pop()
            else:
                ouvertes.append(m.group())
        out.append(tete + ligne + '</span>' * len(ouvertes))
    return out


RE_DEFINITION = re.compile(r'^\s*(?:async\s+)?(?:def|class|function)\s+(\w+)')


def cible(rel, ligne):
    """« fichier:nom » si la ligne définit une fonction ou une classe, sinon '' : sert à retrouver, dans la page,
    les autres figures qui parlent de la même fonction (fiche -> son schéma)."""
    m = RE_DEFINITION.match(ligne)
    return f'{rel}:{m.group(1)}' if m else ''


def panneau(rel, ls, i, j, lien=None, colorer=None):
    """<figure class="code"> du code [i, j), une ligne = <span class="l" data-l="numéro">."""
    texte = '\n'.join(ls[i:j])
    colorer = colorer or _colorer
    corps = colorer(texte, _langue(rel)) if colorer and _langue(rel) else html.escape(texte)
    lignes = ''.join(f'<span class="l" data-l="{i + 1 + k}">{l or " "}</span>'
                     for k, l in enumerate(_par_ligne(corps)))
    titre = f'{html.escape(rel)} · lignes {i + 1}–{j}'
    href = lien(rel, i + 1, j) if lien else ''
    if href:
        titre = f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{titre}</a>'
    return f'<figure class="code"><figcaption>{titre}</figcaption><pre><code>{lignes}</code></pre></figure>'


def resume(rel, ls, i, j):
    """Infobulle par défaut : signature (1re ligne), 1re ligne de la docstring, fichier et lignes."""
    sig = ls[i].strip().rstrip(':{').strip()
    doc = ''
    for l in ls[i + 1:min(j, i + 6)]:
        m = re.match(r'\s*(?:[rRuU]?["\']{3}|/\*\*?|//|#)\s*(.*?)\s*(?:["\']{3}|\*/)?\s*$', l)
        if m and m.group(1):
            doc = m.group(1)
            break
        if l.strip():
            break
    return ' — '.join(x for x in (sig, doc, f'{rel}, lignes {i + 1}–{j}') if x)


# ------------------------------------------------------------------ 1. schéma relié au code
def relier(liens, etapes, survols, trouver, lien=None, colorer=None):
    """liens = {noeud: « chemin | début [| fin] »} (lus par schemas.lire()) ; trouver(rel) -> Path du fichier.
    Complète les étapes qui citent du code (etape['code'] = {noeud, de, a}) et les infobulles absentes.
    Renvoie ({noeud: {'html', 'de', 'a'}}, erreurs)."""
    codes, erreurs = {}, []
    for noeud, arg in liens.items():
        parts = [p.strip() for p in arg.split('|')]
        rel = parts[0]
        if len(parts) < 2 or not parts[1]:
            # « %% code M : module.py » sans repère : fiche du module (rôle + fonctions)
            try:
                codes[noeud] = fiche_module(rel, trouver(rel), lien, colorer)
            except (OSError, SyntaxError, ValueError) as e:
                erreurs.append(f'code {noeud} : fiche du module impossible : {arg} ({type(e).__name__})')
                continue
            survols.setdefault(noeud, codes[noeud].pop('resume'))
            continue
        try:
            ls = lire_lignes(trouver(rel))
            i, j = situer(ls, parts[1], parts[2] if len(parts) > 2 else '')
        except (OSError, StopIteration, ValueError) as e:
            erreurs.append(f'code {noeud} introuvable : {arg} ({type(e).__name__})')
            continue
        codes[noeud] = {'html': panneau(rel, ls, i, j, lien, colorer), 'de': i + 1, 'a': j,
                        'cible': cible(rel, ls[i]), '_ls': ls, 'resume': resume(rel, ls, i, j)}
        survols.setdefault(noeud, codes[noeud]['resume'])
    for e in etapes:
        spec = e.pop('lignes', None)
        if not spec:
            continue
        noeud, _, reperes = (x.strip() for x in spec.partition(':'))
        de, _, a = (x.strip() for x in reperes.partition('..'))
        c = codes.get(noeud)
        if not c:
            erreurs.append(f'étape « {e["titre"]} » : la boîte {noeud} n\'a pas de « %% code »')
            continue
        if '_ls' not in c:
            erreurs.append(f'étape « {e["titre"]} » : la boîte {noeud} montre une fiche de module, pas des lignes')
            continue
        bloc = c['_ls'][c['de'] - 1:c['a']]
        try:
            k = next(n for n, l in enumerate(bloc) if de in l)
            m = next(n for n in range(k, len(bloc)) if a in bloc[n]) if a else k
        except StopIteration:
            erreurs.append(f'étape « {e["titre"]} » : lignes « {reperes} » introuvables dans le code de {noeud}')
            continue
        e['code'] = {'noeud': noeud, 'de': c['de'] + k, 'a': c['de'] + m}
    for c in codes.values():
        c.pop('_ls', None)
        c.pop('resume', None)
    return codes, erreurs


def fiche_module(rel, chemin, lien=None, colorer=None):
    """Fiche d'un module Python : sa docstring (rôle), puis ses fonctions et classes, chacune avec le 1er paragraphe
    de sa docstring ; un clic sur le nom déplie son code (et, dans la page, mène à son schéma s'il y en a un).
    Pour un autre langage : ValueError (citer alors un repère)."""
    if not rel.endswith('.py'):
        raise ValueError('fiche de module : Python seulement')
    src = Path(chemin).read_text(encoding='utf-8-sig')
    arbre = ast.parse(src)
    ls = src.replace('\r', '').split('\n')
    doc = ast.get_docstring(arbre) or ''
    defs = [n for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    noms = {n.name for n in defs}
    # cité ailleurs dans le module (appel, thread target=, table de fonctions…) = pas un point d'entrée
    appelees = {e.id for n in defs for e in ast.walk(n)
                if isinstance(e, ast.Name) and e.id in noms and e.id != n.name}
    appelees |= {e.id for n in arbre.body if n not in defs for e in ast.walk(n)
                 if isinstance(e, ast.Name) and e.id in noms}
    # Points d'entrée d'abord (appelés de l'extérieur du module), puis le reste dans l'ordre du fichier
    defs.sort(key=lambda n: n.name in appelees)
    lignes_html = []
    for n in defs:
        resume_n = ' '.join((ast.get_docstring(n) or '').strip().split('\n\n')[0].split())
        nom = n.name + ('' if isinstance(n, ast.ClassDef) else '()')
        if n.name not in appelees:
            resume_n = '[entrée] ' + resume_n
        nom_html = (f'<button type="button" class="fiche-fn" aria-expanded="false" data-cle="{html.escape(rel)}:'
                    f'{html.escape(n.name)}"><code>{html.escape(nom)}</code></button>')
        debut = min([d.lineno for d in n.decorator_list] + [n.lineno]) - 1
        code_html = panneau(rel, ls, debut, n.end_lineno, lien, colorer)
        entree = resume_n.startswith('[entrée] ')
        texte = html.escape(resume_n[len('[entrée] '):] if entree else resume_n)
        if entree:
            texte = f'<span class="fiche-entree">point d\'entrée</span> {texte}'
        lignes_html.append(f'<tr><td>{nom_html}</td><td>{texte}</td></tr>'
                           f'<tr class="fiche-code" hidden><td colspan="2"><div class="fiche-voir"></div>{code_html}</td></tr>')
    total = len(src.splitlines())
    titre = f'{html.escape(rel)} · module, {len(defs)} fonction(s) ou classe(s)'
    href = lien(rel, 1, total) if lien else ''
    if href:
        titre = f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{titre}</a>'
    paragraphes = ''.join(f'<p>{html.escape(" ".join(p.split()))}</p>' for p in doc.split('\n\n') if p.strip())
    corps = (f'<figure class="code fiche"><figcaption>{titre}</figcaption><div class="fiche-doc">{paragraphes}</div>'
             f'<table class="fiche-fonctions"><tbody>{"".join(lignes_html)}</tbody></table></figure>')
    premier = doc.strip().split('\n')[0] if doc else ''
    return {'html': corps, 'de': 1, 'a': total,
            'resume': ' — '.join(x for x in (premier, f'{rel}, {len(defs)} fonction(s)') if x)}


# ------------------------------------------------------------------ outils Mermaid
def _id(nom):
    return 'n_' + re.sub(r'\W', '_', nom)


def _texte(s, longueur=LONGUEUR_LIBELLE):
    """Libellé Mermaid entre guillemets : une ligne, raccourci, caractères gênants en entités."""
    s = ' '.join(s.split())
    if len(s) > longueur:
        s = s[:longueur - 1] + '…'
    for a, b in (('#', '#35;'), ('"', '#quot;'), ('<', '#lt;'), ('>', '#gt;'), ('`', "'")):
        s = s.replace(a, b)
    return s


def _survol(s):
    return ' '.join(s.split())[:300]


def _arbre(fichier):
    src = Path(fichier).read_text(encoding='utf-8-sig')
    return src, ast.parse(src)


# ------------------------------------------------------------------ 2. carte d'un module
def _fonctions(arbre):
    """{nom: nœud ast} : fonctions du module et méthodes (Classe.methode)."""
    out = {}
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[n.name] = n
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f'{n.name}.{m.name}'] = m
    return out


def _appels(fonction, noms, classe=None):
    """Fonctions connues appelées dans le corps : f(), self.m() / cls.m() (même classe), Classe.m()."""
    vus = []
    for n in ast.walk(fonction):
        if not isinstance(n, ast.Call):
            continue
        f, nom = n.func, None
        if isinstance(f, ast.Name):
            nom = f.id if f.id in noms else (f'{f.id}.__init__' if f'{f.id}.__init__' in noms else None)
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if f.value.id in ('self', 'cls') and classe:
                nom = f'{classe}.{f.attr}'
            else:
                nom = f'{f.value.id}.{f.attr}'
        if nom in noms and nom not in vus:
            vus.append(nom)
    return vus


def carte(rel, chemin, options=''):
    """Code Mermaid (annoté) de la carte du module rel. Renvoie (code, erreurs)."""
    try:
        _, arbre = _arbre(chemin)
    except (OSError, SyntaxError) as e:
        return '', [f'carte-code {rel} : fichier illisible ({type(e).__name__})']
    if not rel.endswith('.py'):
        return '', [f'carte-code {rel} : Python seulement']
    fonctions = _fonctions(arbre)
    if 'sans _prives' in options or 'sans _privés' in options:
        fonctions = {k: v for k, v in fonctions.items() if not k.rsplit('.', 1)[-1].startswith('_')
                     or k.endswith('.__init__')}
    graphe = {k: [a for a in _appels(v, fonctions, k.split('.')[0] if '.' in k else None) if a != k]
              for k, v in fonctions.items()}
    m = re.search(r'depuis\s+([\w.]+)', options)
    if m:
        if m.group(1) not in graphe:
            return '', [f'carte-code {rel} : fonction « {m.group(1)} » introuvable']
        p = re.search(r'profondeur=(\d+)', options)
        limite = int(p.group(1)) if p else 10 ** 6
        garde, rang = {m.group(1)}, [m.group(1)]
        for _ in range(limite):   # en largeur : profondeur=1 = la fonction et ce qu'elle appelle
            rang = [a for n in rang for a in graphe[n] if a not in garde]
            garde.update(rang)
            if not rang:
                break
        graphe = {k: v for k, v in graphe.items() if k in garde}
    m = re.search(r'max=(\d+)', options)
    plafond = int(m.group(1)) if m else MAX_CARTE
    if not graphe:
        return '', [f'carte-code {rel} : aucune fonction']
    if len(graphe) > plafond:
        return '', [f'carte-code {rel} : {len(graphe)} fonctions (plus de {plafond}) ; filtrer avec '
                    f'« depuis <fonction> », « profondeur=1 », « sans _prives » ou « max=… »']
    appelees = {a for v in graphe.values() for a in v}
    lignes = ['flowchart LR']
    for k in graphe:
        n = fonctions[k]
        classe = ':::accent' if k not in appelees or k == 'main' else ''
        if not classe and k.rsplit('.', 1)[-1].startswith('_') and not k.endswith('.__init__'):
            classe = ':::discret'
        affiche = k[:-len('.__init__')] if k.endswith('.__init__') else k   # constructeur : Classe()
        lignes.append(f'  {_id(k)}["{_texte(affiche + "()")}"]{classe}')
    for k, v in graphe.items():
        for a in v:
            if a in graphe:
                lignes.append(f'  {_id(k)} --> {_id(a)}')
    for k in graphe:
        n = fonctions[k]
        nom = k.rsplit('.', 1)[-1]
        prefixe = 'async def ' if isinstance(n, ast.AsyncFunctionDef) else 'def '
        lignes.append(f'%% code {_id(k)} : {rel} | {prefixe}{nom}(')
    return '\n'.join(lignes), []


# ------------------------------------------------------------------ 3. organigramme d'une fonction courte
class _Organigramme:
    """Construit un flowchart TD depuis le corps d'une fonction. Chaque construction renvoie la liste des
    « sorties » (nœud, libellé de flèche) à relier à l'instruction suivante."""

    def __init__(self, src):
        self.src, self.noeuds, self.fleches, self.survols, self.n = src, [], [], {}, 0
        self.boucles = []   # (tête de boucle, sorties de break)

    def noeud(self, texte, forme='[]', classe='', survol='', ligne=None):
        self.n += 1
        nid = f'o{self.n}'
        a, b = {'[]': ('[', ']'), '{}': ('{', '}'), '()': ('([', '])'), '[[]]': ('[[', ']]')}[forme]
        libelle = _texte(texte, LONGUEUR_CONDITION) + ' ?' if forme == '{}' else _texte(texte)
        self.noeuds.append(f'  {nid}{a}"{libelle}"{b}{classe}')
        if survol or ligne:
            self.survols[nid] = _survol((f'ligne {ligne} : ' if ligne else '') + (survol or texte))
        return nid

    def relier(self, sorties, cible):
        for source, libelle in sorties:
            self.fleches.append(f'  {source} -->|{libelle}| {cible}' if libelle else f'  {source} --> {cible}')

    def segment(self, n):
        return ast.get_source_segment(self.src, n) or ''

    def bloc(self, instructions, entrees):
        """entrees : sorties à relier à la première instruction ; renvoie les sorties du bloc."""
        simples = []

        def vider(entrees):
            if not simples:
                return entrees
            textes = [self.segment(s).split('\n')[0] for s in simples]
            texte = textes[0] if len(textes) == 1 else f'{textes[0]} (+{len(textes) - 1})'
            nid = self.noeud(texte, survol=' ; '.join(textes), ligne=simples[0].lineno)
            self.relier(entrees, nid)
            simples.clear()
            return [(nid, '')]

        for s in instructions:
            if isinstance(s, ast.Expr) and isinstance(getattr(s, 'value', None), ast.Constant) \
                    and isinstance(s.value.value, str):
                continue   # docstring
            if isinstance(s, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith,
                              ast.Return, ast.Raise, ast.Break, ast.Continue)):
                entrees = self.instruction(s, vider(entrees))
            else:
                simples.append(s)
        return vider(entrees)

    def instruction(self, s, entrees):
        if isinstance(s, ast.If):
            nid = self.noeud(self.segment(s.test), '{}', survol='if ' + self.segment(s.test), ligne=s.lineno)
            self.relier(entrees, nid)
            sorties = self.bloc(s.body, [(nid, 'oui')])
            sorties += self.bloc(s.orelse, [(nid, 'non')]) if s.orelse else [(nid, 'non')]
            return sorties
        if isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            if isinstance(s, ast.While):
                texte = 'tant que ' + self.segment(s.test)
            else:
                texte = f'pour {self.segment(s.target)} dans {self.segment(s.iter)}'
            nid = self.noeud(texte, '[[]]', survol=self.segment(s).split('\n')[0], ligne=s.lineno)
            self.relier(entrees, nid)
            self.boucles.append((nid, []))
            fin_corps = self.bloc(s.body, [(nid, 'suivant')])
            self.relier(fin_corps, nid)   # retour en tête de boucle
            _, sorties_break = self.boucles.pop()
            return [(nid, 'fini')] + sorties_break
        if isinstance(s, ast.Try):
            nid = self.noeud('essayer', '[]', survol='try', ligne=s.lineno)
            self.relier(entrees, nid)
            sorties = self.bloc(s.body + s.orelse, [(nid, '')])
            for h in s.handlers:
                cas = 'si ' + (self.segment(h.type) if h.type else 'erreur')
                hid = self.noeud(cas, '{}', ':::alerte', survol='except ' + self.segment(h.type) if h.type else 'except',
                                 ligne=h.lineno)
                self.relier([(nid, 'erreur')], hid)
                sorties += self.bloc(h.body, [(hid, 'oui')])
            if s.finalbody:
                sorties = self.bloc(s.finalbody, sorties)
            return sorties
        if isinstance(s, (ast.With, ast.AsyncWith)):
            nid = self.noeud('avec ' + ', '.join(self.segment(i.context_expr) for i in s.items), ligne=s.lineno)
            self.relier(entrees, nid)
            return self.bloc(s.body, [(nid, '')])
        if isinstance(s, ast.Return):
            texte = 'renvoie ' + self.segment(s.value) if s.value else 'fin'
            nid = self.noeud(texte, '()', ':::accent', survol=self.segment(s), ligne=s.lineno)
            self.relier(entrees, nid)
            return []
        if isinstance(s, ast.Raise):
            nid = self.noeud('lève ' + (self.segment(s.exc) if s.exc else ''), '()', ':::alerte',
                             survol=self.segment(s), ligne=s.lineno)
            self.relier(entrees, nid)
            return []
        if isinstance(s, ast.Continue) and self.boucles:
            self.relier([(a, f'{b}, continue' if b else 'continue') for a, b in entrees], self.boucles[-1][0])
            return []
        if isinstance(s, ast.Break) and self.boucles:
            self.boucles[-1][1].extend((a, f'{b}, break' if b else 'break') for a, b in entrees)
            return []
        return entrees


def organigramme(rel, chemin, fonction):
    """Code Mermaid (annoté) de l'organigramme de la fonction (nom, Classe.methode ou repère « def nom( »).
    Renvoie (code, erreurs)."""
    if not rel.endswith('.py'):
        return '', [f'organigramme-code {rel} : Python seulement']
    try:
        src, arbre = _arbre(chemin)
    except (OSError, SyntaxError) as e:
        return '', [f'organigramme-code {rel} : fichier illisible ({type(e).__name__})']
    nom = re.sub(r'^\s*(?:async\s+)?def\s+|\s*\(.*$', '', fonction.strip())
    f = _fonctions(arbre).get(nom) or next((v for k, v in _fonctions(arbre).items() if k.rsplit('.', 1)[-1] == nom), None)
    if not f:
        return '', [f'organigramme-code {rel} : fonction « {nom} » introuvable']
    o = _Organigramme(src)
    debut = o.noeud(f'{nom}()', '()', ':::donnee', survol=src.split('\n')[f.lineno - 1].strip(), ligne=f.lineno)
    fin = o.bloc(f.body, [(debut, '')])
    if fin:
        o.relier(fin, o.noeud('fin', '()', ':::accent'))
    if o.n > MAX_ORGANIGRAMME:
        return '', [f'organigramme-code {rel} | {nom} : {o.n} boîtes (plus de {MAX_ORGANIGRAMME}) : fonction trop '
                    f'longue pour un organigramme ; découper la fonction ou faire un schéma à la main']
    lignes = ['flowchart TD', *o.noeuds, *o.fleches]
    lignes += [f'%% survol {k} : {v}' for k, v in o.survols.items()]
    lignes.append(f'%% code {debut} : {rel} | {"async def" if isinstance(f, ast.AsyncFunctionDef) else "def"} {nom}(')
    return '\n'.join(lignes), []
