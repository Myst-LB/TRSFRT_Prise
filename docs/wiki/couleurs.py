"""Coloration des extraits de code de la revue (Python, JavaScript, PowerShell), sans dépendance.

Classes produites (couleurs dans modele.html) :
    cm commentaire · kw mot-clé · st chaîne · nb nombre · bi constante (True, None, self, this…)
    fn fonction (définie ou appelée) · pa paramètre / argument nommé · va variable affectée ou $x PowerShell · de décorateur
"""
import html
import re

MOTS = {
    'py': 'def class return if elif else for in not and or try except finally raise import from as with while '
          'pass break continue lambda yield global nonlocal is del assert async await',
    'js': 'function return if else for of in const let var new try catch finally throw while do switch case break '
          'continue typeof instanceof class extends async await default',
    'ps1': 'function return if elseif else foreach for in try catch finally throw while param exit',
}
CONSTANTES = {
    'py': 'True False None self cls',
    'js': 'true false null undefined this',
    'ps1': '',
}
DEFINIT = {'def', 'class', 'function'}


def _motif(lang):
    commentaire = r'//.*$' if lang == 'js' else r'\#.*$'
    triple = r'[rbfRBF]{0,2}(?:"""|\'\'\')' if lang == 'py' else r'(?!x)x'
    return re.compile(rf'''
        (?P<cm>{commentaire})
      | (?P<tq>{triple})
      | (?P<st>[rbfRBF]{{0,2}}"(?:\\.|[^"\\])*"|[rbfRBF]{{0,2}}'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)
      | (?P<va>\$[A-Za-z_][\w:]*)
      | (?P<de>@[A-Za-z_][\w.]*)
      | (?P<nb>\b\d+(?:\.\d+)?\b)
      | (?P<id>[A-Za-z_]\w*)
      | (?P<op>==|!=|<=|>=|=>|->|[=(),\[\]{{}}:.])
      | (?P<autre>\s+|.)
    ''', re.X)


def _span(classe, texte):
    return f'<span class="{classe}">{html.escape(texte)}</span>' if texte else ''


def colorer(texte, lang):
    """Texte brut -> HTML coloré (lignes conservées). lang : 'py', 'js' ou 'ps1'."""
    lang = lang if lang in MOTS else 'py'
    mots, consts, motif = set(MOTS[lang].split()), set(CONSTANTES[lang].split()), _motif(lang)
    out, triple = [], None        # triple : délimiteur d'une chaîne Python ouverte sur plusieurs lignes
    for ligne in texte.split('\n'):
        res, pos = [], 0
        if triple:                # suite d'une docstring
            fin = ligne.find(triple)
            if fin < 0:
                out.append(_span('st', ligne))
                continue
            res.append(_span('st', ligne[:fin + 3]))
            pos, triple = fin + 3, None
        profondeur, dans_def, prec = 0, False, ''
        while pos < len(ligne):
            m = motif.match(ligne, pos)
            genre, val = m.lastgroup, m.group()
            if genre == 'tq':     # docstring : jusqu'au délimiteur fermant, ou fin de ligne
                d = val[-3:]
                fin = ligne.find(d, m.end())
                if fin < 0:
                    res.append(_span('st', ligne[pos:]))
                    triple = d
                    break
                res.append(_span('st', ligne[pos:fin + 3]))
                pos = fin + 3
                prec = '"'
                continue
            pos = m.end()
            if genre in ('cm', 'st', 'va', 'de', 'nb'):
                res.append(_span(genre, val))
            elif genre == 'id':
                reste = ligne[pos:].lstrip()
                if val in mots:
                    classe = 'kw'
                elif val in consts:
                    classe = 'bi'
                elif prec in DEFINIT or reste.startswith('('):
                    classe = 'fn'
                elif profondeur and (dans_def or (reste.startswith('=') and not reste.startswith('=='))):
                    classe = 'pa'
                elif not profondeur and reste[:1] == '=' and reste[:2] != '==' and lang != 'ps1':
                    classe = 'va'   # variable affectée (x = …)
                else:
                    classe = None
                res.append(_span(classe, val) if classe else html.escape(val))
                if prec in DEFINIT and val not in mots:
                    dans_def = lang != 'ps1'
            else:
                if val == '(':
                    profondeur += 1
                elif val == ')':
                    profondeur = max(0, profondeur - 1)
                    if not profondeur:
                        dans_def = False
                res.append(html.escape(val))
            if val.strip():
                prec = val
        out.append(''.join(res))
    return '\n'.join(out)
