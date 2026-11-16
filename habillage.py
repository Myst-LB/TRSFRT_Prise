# -*- coding: utf-8 -*-
"""Habillage « Avant / Après » des feuilles CABLAGE et Changements.

Deux familles de couleur : bleu pour l'existant (ce que le script lit sur
l'ancienne switch), vert pour le nouveau (ce qu'on planifie), gris pour le
reste (POE, Etat, Commentaire). Un double trait separe les deux familles.

Les styles sont AJOUTES en fin de listes du styles.xml du gabarit (polices,
remplissages, bordures, cellXfs, dxfs) : aucun index existant ne bouge, comme
pour la police Consolas de gabarit._ajouter_mono. Le gabarit continue de
fournir theme, largeurs de colonnes, couleur d'onglet et mise en page.

La disposition est decrite PAR NOM D'EN-TETE, jamais par position : ajouter
ou deplacer une colonne dans formules.CAB_ENTETES / CHG_ENTETES sans la
declarer ici fait echouer l'import, plutot que de produire une colonne sans
style.
"""
import re

import formules as F

# Famille de chaque colonne : « anc » (existant), « nouv » (planification),
# « autre » (ni l'un ni l'autre). Le double trait se pose devant la premiere
# colonne « nouv ».
CAB_FAMILLE = {
    "Local Switch": "anc", "Anc. Switch": "anc", "Interface": "anc",
    "Description": "anc", "Anc. Prise": "anc", "Anc. Locale": "anc",
    "Nouv. Prise": "nouv", "Nouv. Switch": "nouv", "Nouv. Interface": "nouv",
    "POE": "autre", "Nouv. Locale": "nouv", "VOCATION": "nouv",
    "État": "autre", "Commentaire": "autre",
}
CHG_FAMILLE = {
    "Switch": "anc", "Interface": "anc", "Admin": "anc", "Anc. Prise": "anc",
    "POE": "anc", "Device": "anc", "Config": "anc",
    "Nouv. Interface": "nouv", "Local": "nouv", "Nouv. Prise": "nouv",
    "Description override": "nouv", "New Config": "nouv",
    "État": "autre", "Commentaire": "autre",
}
# Genre de contenu : decide police et alignement. Absent = texte a gauche.
CAB_GENRE = {"Interface": "gras", "Anc. Prise": "prise", "Nouv. Prise": "prise",
             "POE": "centre", "État": "centre"}
CHG_GENRE = {"Interface": "gras", "Nouv. Interface": "gras",
             "Config": "mono", "New Config": "mono",
             "Admin": "centre", "Anc. Prise": "centre", "POE": "centre",
             "Nouv. Prise": "centre", "État": "centre"}

# Feuille IMPRESSION : bloc « existant » a gauche, bloc « a brancher » a droite.
IMP_FAMILLE = {
    "Local Switch": "anc", "Anc. Prise": "anc", "Anc. Locale": "anc",
    "POE": "anc", "VOCATION": "anc", "Description": "anc",
    "Nouv. Prise": "nouv", "Nouv. Locale": "nouv", "Nouv. Switch": "nouv",
    "Nouv. Interface": "nouv", "Commentaire": "autre",
}
IMP_GENRE = {"Anc. Prise": "prise", "Nouv. Prise": "prise", "POE": "centre",
             "Nouv. Interface": "gras", "Local Switch": "petit",
             "Description": "petit"}
# Bandeau de local technique : ardoise, texte blanc.
IMP_BANDE = ("FF3B4A5C", "FFFFFFFF")
IMP_NOUV_FOND = "FFF0F7EE"   # colonnes a remplir / a brancher

for _ent, _fam in ((F.CAB_ENTETES, CAB_FAMILLE), (F.CHG_ENTETES, CHG_FAMILLE),
                   (F.IMP_COLONNES, IMP_FAMILLE)):
    _manque = [e for e in _ent if e not in _fam]
    if _manque:
        raise ImportError("habillage : colonne(s) sans famille : %s" % _manque)

# Palette (ARGB). En-tete fonce + donnees pales, par famille.
ENTETE = {"anc": ("FFDFE6EE", "FF23364D"),
          "nouv": ("FFDCEFDC", "FF1D4D1D"),
          "autre": ("FFF2F2F2", "FF333333")}
DONNEE = {"anc": "FFF4F7FA", "nouv": "FFF5FAF4", "autre": None}
CONFIG = {"anc": "FFEEF3F8", "nouv": "FFEEF7EC", "autre": None}
TRAIT_FORT = "FF333333"
TRAIT_FIN = "FFD5D5D5"
TRAIT_SEPARATION = "FF555555"
GROUPE = ("FF333333", "FFFFFFFF")
# Mise en forme conditionnelle
A_SAISIR = "FFFFF8D6"       # case de planification encore vide
FAIT = "FF1D6B1D"
A_DESACTIVER = "FFC00000"     # rouge : port a remettre a zero
A_PROG = "FF7030A0"          # violet : reste a programmer sur le switch
A_VERIFIER = "FF2E5DA8"      # bleu : a controler sur place
A_FAIRE = "FFC65911"         # orange : planifie, reste a executer
NE_PAS_FAIRE = "FF999999"
ALERTE = "FFAA3333"         # DOUBLON, HORS GABARIT
MODIFIE = "FFC6EFCE"      # vert franc : New Config qui change le port


def _police(taille=11, gras=False, couleur="FF1A1A1A", nom="Calibri"):
    return ('<font>%s<sz val="%s"/><color rgb="%s"/><name val="%s"/>'
            '<family val="%d"/></font>'
            % ("<b/>" if gras else "", taille, couleur, nom,
               3 if nom == "Consolas" else 2))


def _remplissage(argb):
    return ('<fill><patternFill patternType="solid"><fgColor rgb="%s"/>'
            '<bgColor indexed="64"/></patternFill></fill>' % argb)


def _bordure(bas=None, haut=None, gauche=None):
    """Chaque cote : None ou (style, argb)."""
    def cote(tag, v):
        if not v:
            return "<%s/>" % tag
        return '<%s style="%s"><color rgb="%s"/></%s>' % (tag, v[0], v[1], tag)
    return ("<border>%s<right/>%s%s<diagonal/></border>"
            % (cote("left", gauche), cote("top", haut), cote("bottom", bas)))


class _Liste:
    """Une liste du styles.xml (<fonts>, <fills>...) qu'on allonge par la fin."""

    def __init__(self, xml, balise):
        self.balise = balise
        m = re.search(r'<%s count="(\d+)"\s*/>' % balise, xml)
        if m:                                    # <dxfs count="0"/>
            self.vide = m.group(0)
            self.base = int(m.group(1))
        else:
            self.vide = None
            self.base = int(re.search(r'<%s count="(\d+)"' % balise,
                                      xml).group(1))
        self.ajouts = []
        self.index = {}

    def __call__(self, bout):
        """Index de `bout`, ajoute a la fin s'il n'y est pas deja."""
        if bout not in self.index:
            self.index[bout] = self.base + len(self.ajouts)
            self.ajouts.append(bout)
        return self.index[bout]

    def appliquer(self, xml):
        if not self.ajouts:
            return xml
        total = self.base + len(self.ajouts)
        if self.vide:
            return xml.replace(self.vide, '<%s count="%d">%s</%s>' % (
                self.balise, total, "".join(self.ajouts), self.balise), 1)
        xml = re.sub(r'<%s count="\d+"' % self.balise,
                     '<%s count="%d"' % (self.balise, total), xml, count=1)
        return xml.replace("</%s>" % self.balise,
                           "".join(self.ajouts) + "</%s>" % self.balise, 1)


class Habillage:
    """Styles de cellule et formats conditionnels, par nom de colonne.

    Attributs utiles au generateur :
      cab_entete / cab_donnee / chg_entete / chg_donnee : {en-tete: index xf}
      groupe, separateur : index xf des lignes « Local technique » et
                           « — HORS GABARIT — »
      dxf_a_saisir, dxf_fait, dxf_a_faire, dxf_a_prog, dxf_a_desactiver, dxf_a_verifier, dxf_ne_pas_faire, dxf_alerte, dxf_modifie : index dxf
      styles_xml : le styles.xml complete
    """

    def __init__(self, styles_xml):
        polices = _Liste(styles_xml, "fonts")
        fonds = _Liste(styles_xml, "fills")
        bords = _Liste(styles_xml, "borders")
        xfs = _Liste(styles_xml, "cellXfs")
        dxfs = _Liste(styles_xml, "dxfs")

        def xf(police, fond=None, bord=None, horiz=None, vert="center",
               retour=False):
            align = '<alignment%s vertical="%s"%s/>' % (
                ' horizontal="%s"' % horiz if horiz else "", vert,
                ' wrapText="1"' if retour else "")
            return xfs('<xf numFmtId="0" fontId="%d" fillId="%d" borderId="%d" '
                       'xfId="0" applyFont="1" applyFill="1" applyBorder="1" '
                       'applyAlignment="1">%s</xf>'
                       % (polices(police), fonds(fond) if fond else 0,
                          bords(bord) if bord else 0, align))

        def colonnes(entetes, famille, genre, vert):
            separation = next(e for e in entetes if famille[e] == "nouv")
            entete, donnee = {}, {}
            for e in entetes:
                fam, g = famille[e], genre.get(e, "texte")
                gauche = ("double", TRAIT_SEPARATION) if e == separation else None
                fond, encre = ENTETE[fam]
                entete[e] = xf(_police(gras=True, couleur=encre),
                               _remplissage(fond),
                               _bordure(bas=("medium", TRAIT_FORT),
                                        gauche=gauche),
                               horiz="center", retour=True)
                bord = _bordure(bas=("thin", TRAIT_FIN), gauche=gauche)
                if g == "mono":
                    fond_d = CONFIG[fam]
                    donnee[e] = xf(_police(9, nom="Consolas"),
                                   _remplissage(fond_d) if fond_d else None,
                                   bord, vert="top", retour=True)
                    continue
                fond_d = DONNEE[fam]
                donnee[e] = xf(_police(13 if g == "prise" else 11,
                                       gras=g in ("prise", "gras")),
                               _remplissage(fond_d) if fond_d else None, bord,
                               horiz="center" if g in ("prise", "centre")
                               else None, vert=vert)
            return entete, donnee

        self.cab_entete, self.cab_donnee = colonnes(
            F.CAB_ENTETES, CAB_FAMILLE, CAB_GENRE, "center")
        self.chg_entete, self.chg_donnee = colonnes(
            F.CHG_ENTETES, CHG_FAMILLE, CHG_GENRE, "top")
        self.groupe = xf(_police(12, gras=True, couleur=GROUPE[1]),
                         _remplissage(GROUPE[0]))
        self.separateur = xf(_police(gras=True, couleur=TRAIT_FORT),
                             _remplissage(ENTETE["autre"][0]),
                             _bordure(haut=("medium", TRAIT_FORT),
                                      bas=("medium", TRAIT_FORT)))

        # Dans un dxf, la couleur d'un remplissage plein va dans bgColor.
        self.dxf_a_saisir = dxfs('<dxf><fill><patternFill patternType="solid">'
                                 '<bgColor rgb="%s"/></patternFill></fill></dxf>'
                                 % A_SAISIR)
        self.dxf_fait = dxfs('<dxf><font><b/><color rgb="%s"/></font></dxf>'
                             % FAIT)
        self.dxf_a_faire = dxfs('<dxf><font><b/><color rgb="%s"/></font></dxf>'
                                % A_FAIRE)
        self.dxf_a_prog = dxfs('<dxf><font><b/><color rgb="%s"/></font>'
                               '</dxf>' % A_PROG)
        self.dxf_a_desactiver = dxfs('<dxf><font><b/><i/><color rgb="%s"/>'
                                     '</font></dxf>' % A_DESACTIVER)
        self.dxf_a_verifier = dxfs('<dxf><font><b/><color rgb="%s"/></font>'
                                   '</dxf>' % A_VERIFIER)
        self.dxf_ne_pas_faire = dxfs('<dxf><font><i/><color rgb="%s"/></font>'
                                     '</dxf>' % NE_PAS_FAIRE)
        self.dxf_alerte = dxfs('<dxf><font><b/><color rgb="%s"/></font></dxf>'
                               % ALERTE)
        # New Config differente de Config : ce que le transfert va changer.
        self.dxf_modifie = dxfs('<dxf><font><b/></font><fill><patternFill '
                                'patternType="solid"><bgColor rgb="%s"/>'
                                '</patternFill></fill></dxf>' % MODIFIE)

        # Feuille IMPRESSION. Meme code couleur que CABLAGE (bleu = existant,
        # vert = a brancher), double trait entre les deux blocs.
        def bord4(gauche, bas=("thin", TRAIT_FIN)):
            return ('<border><left style="%s"><color rgb="%s"/></left>'
                    '<right style="thin"><color rgb="%s"/></right><top/>'
                    '<bottom style="%s"><color rgb="%s"/></bottom><diagonal/>'
                    '</border>' % (gauche[0], gauche[1], TRAIT_FIN,
                                   bas[0], bas[1]))
        premier_nouv = next(c for c in F.IMP_COLONNES
                            if IMP_FAMILLE[c] == "nouv")
        self.imp_entete, self.imp_donnee = {}, {}
        for c in F.IMP_COLONNES:
            fam, g = IMP_FAMILLE[c], IMP_GENRE.get(c, "texte")
            gauche = (("double", TRAIT_SEPARATION) if c == premier_nouv
                      else ("thin", TRAIT_FIN))
            fond, encre = ENTETE[fam]
            self.imp_entete[c] = xf(_police(10, gras=True, couleur=encre),
                                    _remplissage(fond),
                                    bord4(gauche, ("medium", TRAIT_FORT)),
                                    horiz="center", retour=True)
            police = {"prise": _police(12, gras=True),
                      "gras": _police(10, gras=True),
                      "petit": _police(9, couleur="FF404040")}.get(
                          g, _police(10))
            self.imp_donnee[c] = xf(
                police,
                _remplissage(IMP_NOUV_FOND) if fam == "nouv" else None,
                bord4(gauche),
                horiz="center" if g in ("prise", "centre", "gras") else None,
                vert="center", retour=True)
        self.imp_bande = xf(_police(11, gras=True, couleur=IMP_BANDE[1]),
                            _remplissage(IMP_BANDE[0]),
                            _bordure(haut=("medium", TRAIT_FORT)),
                            vert="center")
        self.imp_bande_hg = xf(_police(11, gras=True, couleur="FFFFFFFF"),
                               _remplissage(ALERTE),
                               _bordure(haut=("medium", TRAIT_FORT)),
                               vert="center")
        # Feuille « Config à copier » : titres de section et conf t / end.
        self.dxf_section = dxfs(
            '<dxf><font><b/><color rgb="FFFFFFFF"/></font><fill><patternFill '
            'patternType="solid"><bgColor rgb="%s"/></patternFill></fill></dxf>'
            % IMP_BANDE[0])
        self.dxf_cmd = dxfs('<dxf><font><b/><color rgb="%s"/></font></dxf>'
                            % "FF7030A0")
        self.imp_aide = xf(_police(9, couleur="FF808080"), horiz="center",
                           vert="center")
        self.imp_rappel = xf(_police(11, gras=True, couleur="FF7F3F00"),
                             _remplissage("FFFFE699"), vert="center")

        for liste in (polices, fonds, bords, xfs, dxfs):
            styles_xml = liste.appliquer(styles_xml)
        self.styles_xml = styles_xml
