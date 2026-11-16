# -*- coding: utf-8 -*-
"""Mini-ecrivain / mini-lecteur XLSX, stdlib uniquement (zipfile + xml).

Pourquoi pas openpyxl : les formules du gabarit sont des formules matricielles
modernes (LET/LAMBDA/MAP/TEXTSPLIT) avec prefixes _xlfn./_xlpm. et attribut
t="array". Les passer dans une lib generique, c'est prendre le risque de les
voir reecrites ou perdues -- or elles sont tout l'interet du classeur. Ici on
ecrit le XML nous-memes : ce qui entre ressort a l'identique.

Toutes les chaines sont ecrites en <is> (inline string) : pas de table
sharedStrings a maintenir, et Excel s'en accommode sans broncher.
"""
import re
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Index des styles produits par _STYLES ci-dessous.
S_DEFAUT, S_ENTETE, S_MONO, S_MONO_WRAP, S_CENTRE = 0, 1, 2, 3, 4


def col_lettre(n):
    """1 -> A, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


class Cellule:
    """Une cellule. `formule` gagne sur `valeur`; `array` -> <f t="array">.

    `garder` force l'ecriture d'une cellule sans contenu, uniquement pour son
    style. C'est ce qui maintient le quadrillage : dans le gabarit les traits
    viennent des bordures des styles de cellule, pas du quadrillage de la
    feuille -- une colonne sans cellule ecrite est donc une colonne sans
    bordures, et le tableau parait troue.
    """

    __slots__ = ("valeur", "formule", "array", "style", "nombre", "garder")

    def __init__(self, valeur=None, formule=None, array=False, style=S_DEFAUT,
                 nombre=False, garder=False):
        self.valeur, self.formule, self.array = valeur, formule, array
        self.style, self.nombre, self.garder = style, nombre, garder


def num(v, style=S_DEFAUT):
    return Cellule(valeur=v, style=style, nombre=True)


def txt(v, style=S_DEFAUT):
    return Cellule(valeur=v, style=style)


def form(f, array=False, style=S_DEFAUT):
    return Cellule(formule=f, array=array, style=style)


def vide(style):
    """Cellule sans contenu, ecrite quand meme pour porter son style."""
    return Cellule(style=style, garder=True)


class Feuille:
    def __init__(self, nom, cols=None, fige_entete=True, autofiltre=True,
                 couleur_onglet=None, cols_xml=None, sheetpr_xml=None,
                 queue_xml=None, fige_colonnes=0):
        self.nom = nom
        self.lignes = []              # liste de listes de (Cellule | None)
        self.cols = cols or []        # (premiere, derniere, largeur, cachee)
        self.fige_entete = fige_entete
        self.fige_colonnes = fige_colonnes   # colonnes figees a gauche
        self.autofiltre = autofiltre
        self.couleur_onglet = couleur_onglet
        # Blocs repris verbatim du gabarit (voir gabarit.Modele). Quand ils
        # sont fournis ils remplacent les equivalents construits ici.
        self.cols_xml = cols_xml
        self.sheetpr_xml = sheetpr_xml
        self.queue_xml = queue_xml
        # {numero de ligne (base 1) -> hauteur en points}. Excel n'ajuste pas
        # la hauteur d'une ligne a l'ouverture : sans ht explicite il applique
        # defaultRowHeight, et un bloc de config sur 15 lignes reste illisible
        # dans une cellule d'une ligne de haut.
        self.hauteurs = {}
        # [(plage, [valeurs])] : listes deroulantes. La plage est une sqref
        # Excel, donc peut enumerer plusieurs cellules separees d'un espace.
        self.listes = []
        # [(plage, dxf, formule)] : mise en forme conditionnelle de type
        # « expression ». La formule est relative a la cellule en haut a gauche
        # de la plage -- d'ou une seule plage contigue par regle.
        self.mef = []
        # Numeros de ligne SOUS lesquels couper la page a l'impression.
        self.sauts = []
        # Lignes repetees en haut de chaque page imprimee (« $1:$1 »).
        self.titres = None
        # Zone d'impression (« $A$2:$K$90 »), None = toute la feuille.
        self.zone_impression = None
        # Nombre de lignes figees en haut (si fige_entete).
        self.lignes_figees = 1
        self.quadrillage = True       # False : quadrillage masque a l'ecran
        # Filtre automatique pre-applique : (ref, colonne 0-based, [valeurs]).
        # Remplace l'autofiltre simple. Excel n'evalue pas le filtre a
        # l'ouverture : les lignes a masquer sont donc listees dans `cachees`.
        self.filtre = None
        self.cachees = set()          # numeros de ligne (base 1) masques

    def ajouter(self, cellules, hauteur=None):
        self.lignes.append(cellules)
        if hauteur:
            self.hauteurs[len(self.lignes)] = hauteur

    def _xml(self):
        nb_col = max((len(l) for l in self.lignes), default=1)
        ref = "A1:%s%d" % (col_lettre(max(nb_col, 1)), max(len(self.lignes), 1))
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/'
               'spreadsheetml/2006/main">']
        if self.sheetpr_xml:
            out.append(self.sheetpr_xml)
        elif self.couleur_onglet:
            out.append('<sheetPr><tabColor rgb="%s"/></sheetPr>'
                       % self.couleur_onglet)
        out.append('<dimension ref="%s"/>' % ref)
        out.append('<sheetViews><sheetView%s workbookViewId="0">'
                   % ("" if self.quadrillage else ' showGridLines="0"'))
        if self.fige_entete and self.fige_colonnes:
            n = self.fige_colonnes
            out.append('<pane xSplit="%d" ySplit="1" topLeftCell="%s2" '
                       'activePane="bottomRight" state="frozen"/>'
                       % (n, col_lettre(n + 1)))
        elif self.fige_entete:
            n = self.lignes_figees
            out.append('<pane ySplit="%d" topLeftCell="A%d" '
                       'activePane="bottomLeft" state="frozen"/>' % (n, n + 1))
        out.append("</sheetView></sheetViews>")
        out.append('<sheetFormatPr defaultRowHeight="15"/>')
        if self.cols_xml:
            out.append(self.cols_xml)
        elif self.cols:
            out.append("<cols>")
            for prem, dern, larg, cachee in self.cols:
                out.append('<col min="%d" max="%d" width="%s" customWidth="1"%s/>'
                           % (prem, dern, larg, ' hidden="1"' if cachee else ""))
            out.append("</cols>")
        out.append("<sheetData>")
        for i, ligne in enumerate(self.lignes, 1):
            morceaux = []
            for j, c in enumerate(ligne, 1):
                if c is None:
                    continue
                creuse = c.valeur is None and c.formule is None
                if creuse and not (c.garder and c.style):
                    continue
                r = "%s%d" % (col_lettre(j), i)
                st = ' s="%d"' % c.style if c.style else ""
                if creuse:
                    morceaux.append('<c r="%s"%s/>' % (r, st))
                    continue
                if c.formule is not None:
                    # cm="1" pointe sur l'unique bloc de xl/metadata.xml et
                    # marque la formule comme matricielle *dynamique*. Sans lui
                    # Excel la degrade en matricielle heritee (CSE), ou
                    # _xlfn.SINGLE et les fonctions a plage (MAP, TEXTSPLIT)
                    # ne se comportent pas pareil. C'est l'encodage exact du
                    # classeur d'origine, aca/ca compris.
                    meta = ' cm="1"' if c.array else ""
                    fa = ' t="array" aca="1" ref="%s" ca="1"' % r if c.array else ""
                    morceaux.append('<c r="%s"%s%s><f%s>%s</f></c>'
                                    % (r, st, meta, fa, esc(c.formule)))
                elif c.nombre:
                    morceaux.append('<c r="%s"%s><v>%s</v></c>' % (r, st, c.valeur))
                else:
                    morceaux.append('<c r="%s"%s t="inlineStr"><is><t '
                                    'xml:space="preserve">%s</t></is></c>'
                                    % (r, st, esc(c.valeur)))
            if morceaux:
                h = self.hauteurs.get(i)
                attrs = (' ht="%s" customHeight="1"' % h) if h else ""
                if i in self.cachees:
                    attrs += ' hidden="1"'
                out.append('<row r="%d"%s>%s</row>'
                           % (i, attrs, "".join(morceaux)))
        out.append("</sheetData>")
        # L'ordre des elements de fin est impose par le schema OOXML :
        # autoFilter, puis printOptions/pageMargins/pageSetup/headerFooter.
        if self.filtre:
            ref, col, valeurs = self.filtre
            out.append('<autoFilter ref="%s"><filterColumn colId="%d"><filters>'
                       '%s</filters></filterColumn></autoFilter>'
                       % (ref, col, "".join('<filter val="%s"/>' % esc(v)
                                            for v in valeurs)))
        elif self.autofiltre and len(self.lignes) > 1:
            out.append('<autoFilter ref="A1:%s%d"/>'
                       % (col_lettre(nb_col), len(self.lignes)))
        # conditionalFormatting : apres autoFilter, avant dataValidations.
        for prio, (plage, dxf, formule) in enumerate(self.mef, 1):
            out.append('<conditionalFormatting sqref="%s"><cfRule '
                       'type="expression" dxfId="%d" priority="%d"><formula>'
                       '%s</formula></cfRule></conditionalFormatting>'
                       % (plage, dxf, prio, esc(formule)))
        # dataValidations : apres autoFilter, avant la queue d'impression.
        listes = [(plage, v) for plage, v in self.listes if plage]
        if listes:
            out.append('<dataValidations count="%d">' % len(listes))
            for plage, valeurs in listes:
                out.append('<dataValidation type="list" allowBlank="1" '
                           'showInputMessage="1" showErrorMessage="1" '
                           'sqref="%s"><formula1>%s</formula1>'
                           '</dataValidation>'
                           % (plage, esc('"%s"' % ",".join(valeurs))))
            out.append("</dataValidations>")
        out.append(self.queue_xml if self.queue_xml else
                   '<pageMargins left="0.7" right="0.7" top="0.75" '
                   'bottom="0.75" header="0.3" footer="0.3"/>')
        # rowBreaks : apres headerFooter, dernier element de la queue.
        if self.sauts:
            out.append('<rowBreaks count="%d" manualBreakCount="%d">%s'
                       '</rowBreaks>' % (len(self.sauts), len(self.sauts), "".join(
                           '<brk id="%d" max="16383" man="1"/>' % r
                           for r in self.sauts)))
        out.append("</worksheet>")
        return "".join(out)


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><sz val="9"/><name val="Consolas"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E79"/>
<bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top/><bottom style="thin">
<color rgb="FF1F4E79"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
</cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1"
 applyFill="1" applyBorder="1" applyAlignment="1">
 <alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"
 applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"
 applyAlignment="1"><alignment horizontal="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>
</cellStyles>
</styleSheet>"""


# Partie « sheetMetadata » recopiee telle quelle du classeur d'origine : un seul
# bloc XLDAPR (dynamicArrayProperties), reference par cm="1" sur les cellules.
_METADATA = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<metadata xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:xlrd="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"'
    ' xmlns:xda="http://schemas.microsoft.com/office/spreadsheetml/2017/'
    'dynamicarray"><metadataTypes count="1"><metadataType name="XLDAPR"'
    ' minSupportedVersion="120000" copy="1" pasteAll="1" pasteValues="1"'
    ' merge="1" splitFirst="1" rowColShift="1" clearFormats="1"'
    ' clearComments="1" assign="1" coerce="1" cellMeta="1"/></metadataTypes>'
    '<futureMetadata name="XLDAPR" count="1"><bk><extLst>'
    '<ext uri="{bdbb8cdc-fa1e-496e-a857-3c3f30c029c3}">'
    '<xda:dynamicArrayProperties fDynamic="1" fCollapsed="0"/></ext></extLst>'
    '</bk></futureMetadata><cellMetadata count="1"><bk><rc t="1" v="0"/></bk>'
    '</cellMetadata></metadata>')


def ecrire(chemin, feuilles, styles_xml=None, theme_xml=None):
    """Ecrit le classeur. `feuilles` : liste de Feuille, dans l'ordre voulu.

    `styles_xml` / `theme_xml` : parties reprises du gabarit. Les index de
    style portes par les cellules s'y referent, donc les deux vont ensemble --
    le styles.xml du gabarit designe ses couleurs par index de theme.
    """
    n = len(feuilles)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
          '-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
          '<Override PartName="/xl/metadata.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml"/>']
    if theme_xml:
        ct.append('<Override PartName="/xl/theme/theme1.xml" ContentType='
                  '"application/vnd.openxmlformats-officedocument.theme+xml"/>')
    for i in range(1, n + 1):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType='
                  '"application/vnd.openxmlformats-officedocument.'
                  'spreadsheetml.worksheet+xml"/>' % i)
    ct.append("</Types>")

    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
          '2006/main" xmlns:r="http://schemas.openxmlformats.org/'
          'officeDocument/2006/relationships"><sheets>']
    for i, f in enumerate(feuilles, 1):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                  % (esc(f.nom), i, i))
    wb.append("</sheets>")
    # Print_Titles : lignes repetees en haut de chaque page imprimee. Les noms
    # de feuille ne contiennent jamais d'apostrophe (retiree a l'attribution).
    titres = ['<definedName name="_xlnm.Print_Titles" localSheetId="%d">'
              "'%s'!%s</definedName>" % (i, esc(f.nom), f.titres)
              for i, f in enumerate(feuilles) if f.titres]
    titres += ['<definedName name="_xlnm.Print_Area" localSheetId="%d">'
               "'%s'!%s</definedName>" % (i, esc(f.nom), f.zone_impression)
               for i, f in enumerate(feuilles) if f.zone_impression]
    # Nom cache qu'Excel associe a tout filtre automatique pre-regle ; sans
    # lui, « Reappliquer » peut ne pas retrouver la plage filtree.
    titres += ['<definedName name="_xlnm._FilterDatabase" localSheetId="%d" '
               'hidden="1">\'%s\'!%s</definedName>'
               % (i, esc(f.nom), "$" + re.sub(r"([A-Z]+)(\d+)", r"\1$\2",
                                              f.filtre[0]).replace(":", ":$"))
               for i, f in enumerate(feuilles) if f.filtre]
    if titres:
        wb.append("<definedNames>%s</definedNames>" % "".join(titres))
    # fullCalcOnLoad : les formules matricielles n'ont pas de valeur en cache,
    # Excel doit tout recalculer a l'ouverture sinon les cellules restent vides.
    wb.append('<calcPr calcId="191028" fullCalcOnLoad="1"/></workbook>')

    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships">']
    for i in range(1, n + 1):
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxml'
                    'formats.org/officeDocument/2006/relationships/worksheet" '
                    'Target="worksheets/sheet%d.xml"/>' % (i, i))
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.'
                'org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>' % (n + 1))
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.'
                'org/officeDocument/2006/relationships/sheetMetadata" '
                'Target="metadata.xml"/>' % (n + 2))
    if theme_xml:
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxml'
                    'formats.org/officeDocument/2006/relationships/theme" '
                    'Target="theme/theme1.xml"/>' % (n + 3))
    rels.append("</Relationships>")

    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/relationships"><Relationship Id="rId1" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/'
                   '2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", styles_xml or _STYLES)
        if theme_xml:
            z.writestr("xl/theme/theme1.xml", theme_xml)
        z.writestr("xl/metadata.xml", _METADATA)
        for i, f in enumerate(feuilles, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, f._xml())


def lire(chemin):
    """Relit un classeur -> {nom_feuille: {(ligne, col_lettre): texte}}.

    Ne rend que les valeurs litterales (les formules sont ignorees) : c'est ce
    qu'il faut pour comparer les donnees extraites des .txt, pas le calcul.
    """
    res = {}
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(chemin) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid2cible = {}
        for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            rid2cible[rel.get("Id")] = rel.get("Target").lstrip("/")
        noms = [(sh.get("name"), rid2cible[sh.get(R + "id")])
                for sh in wb.find(NS + "sheets")]
        ss = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                ss.append("".join(t.text or "" for t in si.iter(NS + "t")))
        for nom, cible in noms:
            part = cible if cible.startswith("xl/") else "xl/" + cible
            cellules = {}
            for _, el in ET.iterparse(z.open(part)):
                if el.tag != NS + "c":
                    continue
                if el.find(NS + "f") is not None:
                    el.clear()
                    continue
                ty, v = el.get("t"), el.find(NS + "v")
                if ty == "inlineStr":
                    isn = el.find(NS + "is")
                    val = ("".join(t.text or "" for t in isn.iter(NS + "t"))
                           if isn is not None else "")
                elif ty == "s" and v is not None:
                    val = ss[int(v.text)]
                elif v is not None:
                    val = v.text
                else:
                    el.clear()
                    continue
                ref = el.get("r")
                lig = int("".join(c for c in ref if c.isdigit()))
                col = "".join(c for c in ref if c.isalpha())
                cellules[(lig, col)] = val
                el.clear()
            res[nom] = cellules
    return res
