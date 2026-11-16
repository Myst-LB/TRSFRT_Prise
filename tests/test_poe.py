# -*- coding: utf-8 -*-
"""Colonne POE : règle NON-POE / POE / POE+ et lecture du « show power inline ».

Données FICTIVES uniquement (skill donnees-sensibles) : noms de switchs,
locaux et prises inventés ; aucun fichier du parc n'est lu.

Lancer : python -m unittest discover -s tests -v
"""
import os
import re
import sys
import tempfile
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))

import analyse  # noqa: E402
import formules  # noqa: E402


def port(power, device="n/a", classe="n/a", maxi=30.0):
    """Une ligne de « show power inline » telle que lire_poe() la rend."""
    return {"admin": "auto", "oper": "on" if power else "off",
            "power": power, "device": device, "classe": classe, "max": maxi}


class RegleNonPoe(unittest.TestCase):
    """Pas de courant sur l'ancien port -> pas de PoE à prévoir."""

    def test_aucune_donnee(self):
        self.assertEqual(analyse.etat_poe(None), "NON-POE")

    def test_zero_watt_meme_sur_port_capable(self):
        self.assertEqual(analyse.etat_poe(port(0.0, maxi=30.0)), "NON-POE")

    def test_zero_watt_meme_marque_ap(self):
        # La consigne porte sur ce qui est branché : rien ne tire de courant.
        self.assertEqual(analyse.etat_poe(port(0.0), "LAB-0101-00_P0001 (AP)"),
                         "NON-POE")


class ReglePoe(unittest.TestCase):

    def test_telephone_classe_2(self):
        self.assertEqual(analyse.etat_poe(port(6.5, "IP Phone 8845", "2")), "POE")

    def test_classe_3_sous_le_plafond(self):
        self.assertEqual(analyse.etat_poe(port(12.0, "Ieee PD", "3")), "POE")

    def test_pile_au_plafond_af(self):
        # 15,4 W est encore du PoE classique : POE+ seulement au-dessus.
        self.assertEqual(analyse.etat_poe(port(15.4, "Ieee PD", "3")), "POE")

    def test_vocation_autre_que_ap(self):
        self.assertEqual(
            analyse.etat_poe(port(4.0, "Ieee PD", "2"),
                             "LAB-0101-00_P0012 (Imprimante)"), "POE")

    def test_modele_ap_dans_la_description_sans_marqueur(self):
        # Seul le marqueur « (AP) » de la description compte ; un nom de
        # modèle dans la description n'en est pas un.
        self.assertEqual(
            analyse.etat_poe(port(7.0, "Ieee PD", "3"), "AIR-AP2802I-A-K9 _P12"),
            "POE")


class ReglePoePlus(unittest.TestCase):

    def test_conso_au_dessus_du_plafond_af(self):
        self.assertEqual(analyse.etat_poe(port(15.5, "Ieee PD", "3")), "POE+")

    def test_classe_4_meme_a_faible_conso(self):
        self.assertEqual(analyse.etat_poe(port(5.0, "Ieee PD", "4")), "POE+")

    def test_classes_bt(self):
        for c in ("5", "6", "7", "8"):
            with self.subTest(classe=c):
                self.assertEqual(analyse.etat_poe(port(5.0, "Ieee PD", c)), "POE+")

    def test_marqueur_ap_dans_la_description(self):
        self.assertEqual(
            analyse.etat_poe(port(8.0, "Ieee PD", "3"), "LAB-0101-00_P0643 (AP)"),
            "POE+")

    def test_modeles_ap_reconnus_dans_device(self):
        for device in ("AIR-AP2802I-A-K9", "AIR-CAP3702I-A-K9", "C9115AXI-B",
                       "C9120AXE-A", "C9130AXI-E", "CW9166I-MR", "MR46",
                       "Meraki MR36", "Cisco AP", "Access Point", "PTZ Cam"):
            with self.subTest(device=device):
                self.assertEqual(analyse.etat_poe(port(9.0, device, "n/a")),
                                 "POE+")

    def test_faux_amis_de_device(self):
        # « AP » doit être un mot entier : un modèle qui le contient au milieu
        # n'est pas un point d'accès.
        for device in ("IP Phone 8865", "Ieee PD", "SNAPSHOT-CAM", "KAPTURE"):
            with self.subTest(device=device):
                self.assertEqual(analyse.etat_poe(port(6.0, device, "2")), "POE")


class LecturePoe(unittest.TestCase):
    """De bout en bout : fichier -> lire_poe() -> etat_poe()."""

    SORTIE = (
        "﻿Module   Available     Used     Remaining\r\n"
        "          (Watts)     (Watts)    (Watts)\r\n"
        "------   ---------   --------   ---------\r\n"
        "1           740.0       39.1       700.9\r\n"
        "Interface Admin  Oper       Power   Device              Class Max\r\n"
        "                            (Watts)\r\n"
        "--------- ------ ---------- ------- ------------------- ----- ----\r\n"
        "Gi1/0/1   auto   off        0.0     n/a                 n/a   30.0\r\n"
        "Gi1/0/2   auto   on         6.5     IP Phone 8845       2     30.0\r\n"
        "Gi1/0/3   auto   on         9.2     C9120AXI-A          4     30.0\r\n"
        "Gi1/0/4   auto   on         17.6    Ieee PD             4     30.0\r\n"
        "Gi1/0/5   auto   on         11.0    Ieee PD             3     30.0"
    )

    def setUp(self):
        # Dossier accentué : un défaut d'encodage de chemin ne se voit qu'ainsi.
        self._tmp = tempfile.TemporaryDirectory(prefix="Câblage_Réseau_")
        self.chemin = os.path.join(self._tmp.name, "LAB-0101-9300A.txt")
        with open(self.chemin, "w", encoding="utf-8", newline="") as f:
            f.write(self.SORTIE)

    def tearDown(self):
        self._tmp.cleanup()

    def test_lecture_et_etats(self):
        poe, entete = analyse.lire_poe(self.chemin)
        self.assertTrue(entete)
        self.assertEqual(sorted(poe), ["Gi1/0/%d" % i for i in range(1, 6)])
        descriptions = {"Gi1/0/5": "LAB-0101-00_P0005 (AP)"}
        etats = {p: analyse.etat_poe(poe[p], descriptions.get(p)) for p in poe}
        self.assertEqual(etats, {"Gi1/0/1": "NON-POE", "Gi1/0/2": "POE",
                                 "Gi1/0/3": "POE+", "Gi1/0/4": "POE+",
                                 "Gi1/0/5": "POE+"})


class PariteAbreges(unittest.TestCase):
    """La table d'abréviations existe en deux copies : analyse.ABREGES et les
    XLOOKUP des formules J et N. Une divergence casse la résolution des blocs
    de config sans aucune erreur visible."""

    def tables_formule(self, formule):
        listes = re.findall(r'\{\{("[^}]*")\}\}', formule)
        abr = re.findall(r'"([^"]*)"', listes[-2])
        longs = re.findall(r'"([^"]*)"', listes[-1])
        return list(zip(abr, longs))

    def test_parite(self):
        attendu = analyse.ABREGES
        for nom, formule in (("CHG_J", formules.CHG_J), ("CHG_N", formules.CHG_N)):
            with self.subTest(formule=nom):
                table = self.tables_formule(formule)
                self.assertEqual(len(table), 9)
                for paire in table:
                    self.assertIn(paire, attendu)
                # Chaque abrégé de Python a sa traduction dans la formule
                # (« FortyGigE » n'est qu'une forme reconnue en lecture).
                self.assertEqual({a for a, _ in attendu}, {a for a, _ in table})


if __name__ == "__main__":
    unittest.main()
