# -*- coding: utf-8 -*-
"""Lecture de Template.xlsx : styles, largeurs et mise en page a reutiliser.

On ne recopie pas le classeur : on lui emprunte sa *presentation*. Le
generateur produit les feuilles et les formules, mais les polices, couleurs,
bordures, largeurs de colonnes, couleurs d'onglet et mise en page d'impression
viennent du gabarit -- donc le classeur produit ressemble exactement a celui
tenu a la main.

Concretement, le gabarit fournit pour chacune de ses deux feuilles modeles :
  - les largeurs de colonnes (bloc <cols>) ;
  - le <sheetPr> (couleur d'onglet) et la queue d'impression.

Les styles de CELLULE ne viennent plus du gabarit mais de habillage.py, qui les
ajoute en fin du xl/styles.xml du gabarit. Celui-ci est donc toujours recopie
dans le classeur produit, avec le theme dont il depend pour ses couleurs.
"""
import re
import zipfile
import xml.etree.ElementTree as ET

import habillage

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Police ajoutee au styles.xml du gabarit pour les feuilles de config brute :
# le gabarit n'en contient aucune (il n'a pas ce type de feuille).
_FONT_MONO = '<font><sz val="9"/><name val="Consolas"/><family val="3"/></font>'


class Modele:
    """Presentation empruntee a une feuille du gabarit."""

    def __init__(self, xml):
        m = re.search(r"<cols>.*?</cols>", xml, re.S)
        self.cols_xml = m.group(0) if m else ""
        # Largeurs/styles de colonne, indexes par numero de colonne, pour
        # pouvoir les remapper quand la feuille produite n'a pas exactement
        # les memes colonnes que le gabarit (voir cols_depuis).
        self.cols = {}
        for bout in re.findall(r"<col [^>]*/>", self.cols_xml):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', bout))
            for c in range(int(attrs["min"]), int(attrs["max"]) + 1):
                self.cols[c] = attrs

        m = (re.search(r"<sheetPr>.*?</sheetPr>", xml, re.S)
             or re.search(r"<sheetPr[^>]*/>", xml))
        self.sheetpr_xml = m.group(0) if m else ""

        # Queue d'impression uniquement. On laisse volontairement tomber
        # <autoFilter> (regenere a la bonne taille) et <sheetProtection> : le
        # gabarit protege la feuille Changements, ce qui empecherait de saisir
        # la colonne « Local » dans le classeur produit.
        tail = xml[xml.find("</sheetData>") + 12:]
        garde = []
        for motif in (r"<printOptions[^>]*/>", r"<pageMargins[^>]*/>",
                      r"<pageSetup[^>]*/>", r"<headerFooter>.*?</headerFooter>"):
            m = re.search(motif, tail, re.S)
            if m:
                bout = m.group(0)
                # r:id renvoie a un printerSettings.bin qu'on ne recopie pas.
                bout = re.sub(r'\s+r:id="[^"]*"', "", bout)
                garde.append(bout)
        self.queue_xml = "".join(garde)

    def cols_depuis(self, mapping, largeurs=None, masquees=None):
        """Reconstruit un <cols> pour une feuille aux colonnes decalees.

        `mapping` : {colonne produite -> colonne du gabarit dont on reprend
        largeur et masquage}. Le style de colonne du gabarit n'est PAS repris :
        les cellules portent celui de habillage.py, et un style de colonne
        herite teinterait les cellules non ecrites, sous le tableau. `largeurs` force une largeur pour
        certaines colonnes produites. Sans ca, inserer une colonne au milieu
        decalerait toutes les largeurs du gabarit d'un cran.

        `masquees` : ensemble des colonnes produites a masquer. Passe explicite
        (meme vide), il remplace le masquage herite du gabarit -- necessaire
        parce que Device y est masquee alors qu'on veut la lire.
        """
        out = []
        for gen in sorted(mapping):
            src = self.cols.get(mapping[gen], {})
            largeur = (largeurs or {}).get(gen) or src.get("width")
            if not largeur:
                continue
            bout = '<col min="%d" max="%d" width="%s" customWidth="1"' % (
                gen, gen, largeur)
            cache = (gen in masquees) if masquees is not None \
                else src.get("hidden") == "1"
            if cache:
                bout += ' hidden="1"'
            out.append(bout + "/>")
        return "<cols>%s</cols>" % "".join(out) if out else ""


class Gabarit:
    def __init__(self, chemin):
        self.chemin = chemin
        with zipfile.ZipFile(chemin) as z:
            noms = z.namelist()
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            rid = {r.get("Id"): r.get("Target").lstrip("/")
                   for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            feuilles = [(s.get("name"), rid[s.get(R + "id")])
                        for s in wb.find(NS + "sheets")]
            styles = z.read("xl/styles.xml").decode("utf-8")
            self.theme_xml = (z.read("xl/theme/theme1.xml").decode("utf-8")
                              if "xl/theme/theme1.xml" in noms else None)

            def lire(prefixe):
                for nom, cible in feuilles:
                    if nom.upper().startswith(prefixe):
                        part = cible if cible.startswith("xl/") else "xl/" + cible
                        return Modele(z.read(part).decode("utf-8"))
                return None

            self.cablage = lire("CÂBLAGE") or lire("CABLAGE")
            self.changements = lire("CHANGEMENTS")

        if self.cablage is None or self.changements is None:
            raise ValueError(
                "%s ne contient pas les deux feuilles modeles attendues "
                "(une « CÂBLAGE… » et une « Changements… »)" % chemin)

        self.styles_xml, self.mono, self.mono_wrap = self._ajouter_mono(styles)
        # Styles des feuilles CABLAGE et Changements, ajoutes a la suite.
        self.habillage = habillage.Habillage(self.styles_xml)
        self.styles_xml = self.habillage.styles_xml

    @staticmethod
    def _ajouter_mono(styles):
        """Ajoute une police a chasse fixe et ses deux styles au styles.xml.

        Renvoie (xml, index_mono, index_mono_wrap). Les index existants du
        gabarit ne bougent pas : on ne fait qu'ajouter a la fin de <fonts> et
        de <cellXfs>, donc tous les styles releves dans les feuilles modeles
        restent valides.
        """
        m = re.search(r'<fonts count="(\d+)"', styles)
        n_fonts = int(m.group(1))
        styles = styles.replace(m.group(0), '<fonts count="%d"' % (n_fonts + 1), 1)
        styles = styles.replace("</fonts>", _FONT_MONO + "</fonts>", 1)

        m = re.search(r'<cellXfs count="(\d+)"', styles)
        n_xf = int(m.group(1))
        styles = styles.replace(m.group(0), '<cellXfs count="%d"' % (n_xf + 2), 1)
        ajout = ('<xf numFmtId="0" fontId="%d" fillId="0" borderId="0" xfId="0"'
                 ' applyFont="1"/>'
                 '<xf numFmtId="0" fontId="%d" fillId="0" borderId="0" xfId="0"'
                 ' applyFont="1" applyAlignment="1">'
                 '<alignment vertical="top" wrapText="1"/></xf>'
                 % (n_fonts, n_fonts))
        styles = styles.replace("</cellXfs>", ajout + "</cellXfs>", 1)
        return styles, n_xf, n_xf + 1

    def entete_impression(self, projet):
        """En-tete d'impression du gabarit, avec le nom du projet courant.

        Le gabarit porte « Projet Réaménagement Câblage Z7 - Imprimé le
        21 juillet 2026 par MM » : recopie tel quel, chaque projet s'imprimerait
        sous le nom d'un autre. On garde la mise en forme, on remplace le texte.
        """
        return ("<headerFooter><oddHeader>&amp;CProjet Réaménagement Câblage "
                "%s</oddHeader><oddFooter xml:space=\"preserve\">&amp;R&amp;P  "
                "</oddFooter></headerFooter>"
                % re.sub(r"[&<>]", "", projet))
