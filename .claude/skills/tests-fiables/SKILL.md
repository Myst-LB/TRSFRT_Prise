---
name: tests-fiables
description: >-
  Règles et pièges déjà payés pour que des tests verts disent vrai : tests sautés en silence, fils et serveurs qui
  survivent au test, horloge et fuseau figés, chemins accentués, tests de parité entre deux copies d'une règle,
  référence (baseline) à ne pas refaire, tests structurels qui lisent le code, et ce que les tests ne voient jamais
  (l'écran). À lire avant d'écrire, modifier ou lancer une suite de tests, ou quand un test échoue par
  intermittence.
---

# Des tests qui disent vrai

Un test vert qui ne vérifie rien est pire qu'un test absent : il rassure. Chaque règle ci-dessous vient d'un défaut
passé au travers d'une suite verte.

## 1. Compter ce qui a vraiment tourné

- **Un test sauté ne se voit pas dans « 0 échec »** ; seul le compteur `skipped` en parle. Un `skipTest` conditionné
  à un chemin peut ne **jamais** mordre (un `dirname` de trop) : le test de parité qu'il gardait n'a jamais tourné,
  et la divergence est passée.
- Le lanceur **liste les sautés et échoue sur un saut inexpliqué** : une liste blanche de raisons permises, chacune
  avec sa condition **réévaluée** (« module absent » alors qu'il s'importe = échec).
- Le harnais lui-même est testé : il échoue quand un test échoue, et il signale un fichier de test qui ne s'exécute
  pas (« fichier muet ») au lieu de l'ignorer.
- Rapporter les comptes à la clôture : « 248 tests, 248 passés, 0 sautés », pas « tout passe ».

## 2. Ne rien laisser courir

- Un fil, un serveur ou un processus démarré par un test est **joint ou arrêté** avant la fin du test. `stop()`
  qui rend la main tout de suite ne suffit pas si le fil dort encore : il survit et fait échouer, par intermittence,
  **un autre fichier** que le fautif (mesuré : 2 exécutions sur 3 en échec, 0 sur 3 une fois les fils joints).
- Un serveur de test écoute sur un port libre choisi par le système, pas sur le port de l'outil.
- Symptôme d'une fuite : un échec qui ne se reproduit pas en lançant le test seul.

## 3. Reproductible : horloge, fuseau, ordre

- Le code passe par une **indirection** (`_now()`) au lieu d'appeler `datetime.now()` ; le test et le rejeu figent
  l'horloge. Sans elle, décroissances, fenêtres glissantes et « depuis » dépendent de l'heure du jour.
- Imposer un fuseau en remplaçant les fonctions de sonde du code, pas par `TZ=` (`time.tzset()` n'existe pas sous
  Windows). Tester la nuit du changement d'heure (heure répétée) quand le code compare des horodatages.
- Ne pas dépendre de l'ordre alphabétique des fichiers de test ni de l'ordre d'un dictionnaire.

## 4. Chemins et encodages réels

- Faire tourner la suite sous un **dossier temporaire accentué** (« …/Réseau/… ») : un défaut d'encodage de chemin
  n'apparaît qu'hors d'un chemin ASCII. Garder un interrupteur pour isoler un échec ; un test qui ne passe
  qu'avec est un défaut, pas un test fragile.
- Fixtures avec BOM UTF-8, UTF-16, fins de ligne CRLF, fichier sans fin de ligne finale.
- Pas de glyphe hors cp1252 dans les `print()` d'un outil lancé sur une console Windows (`⚠` fait lever).

## 5. Deux copies d'une règle : test de parité

Quand une règle existe en deux langages ou deux outils (serveur / navigateur, deux dépôts) :

- Le test **lit la vraie constante des deux côtés** et les compare ; vérifier qu'un appel existe côté JS ne
  verrouille rien.
- Commentaire croisé dans chaque copie qui nomme l'autre et le test.
- Avant d'ajouter une copie : le serveur peut-il calculer et expédier le résultat ? Le client peut-il envoyer sa
  donnée déjà découpée ? Une copie de moins vaut mieux qu'un test de parité de plus.
- Une **copie d'un fichier** (`outil-fix.py`) n'est jamais un correctif livré : reporter dans l'original et tester.

## 6. Référence et deltas

- Un rejeu sur un **corpus figé** (copie datée, taille et empreinte enregistrées) produit un tableau
  AVANT / APRÈS / DELTA : c'est le contrat. Tout chiffre qui bouge s'explique par le changement ; un delta
  inexpliqué = on s'arrête et on cherche, **on ne refait pas la référence**.
- Jamais rejouer sur un fichier vivant qui grossit : les deltas mélangeraient le code et les données.
- Vérifier ce que couvre vraiment le corpus (son nom peut mentir sur sa période) avant d'en tirer des taux.
- Agréger sans doubler : un enregistrement de groupe qui somme ses membres ne se compte pas en plus d'eux.

## 7. Tests structurels (qui lisent le code)

Quand le langage ne s'exécute pas dans le harnais (JS dans une chaîne Python, HTML), un test peut lire le code
servi : `node --check` de chaque `<script>` **réellement servi**, présence d'un garde, absence d'une surface
retirée. Fragiles par nature : si un renommage les casse, mettre à jour l'assertion, pas la supprimer. Le test qui
compte vérifie l'**absence d'effet** (le crochet n'est pas atteint), pas seulement un code de retour : c'est le seul
qui échoue si un garde est simplement déplacé plus bas.

## 8. Plus de refus que d'acceptations

Une règle qui supprime, fusionne ou filtre se trompe par excès, et ça ne se voit pas. Écrire deux fois plus de cas
sur ce qu'elle doit **laisser passer intact** que sur ce qu'elle avale ; un cas illisible ne doit jamais être avalé
(mieux vaut compter deux fois que perdre une ligne qu'on n'a pas su lire).

## 9. Ce que les tests ne voient pas

- **Une valeur produite n'est pas une valeur affichée** : une chaîne construite peut ne jamais atterrir dans le
  DOM. Tester l'émission, puis regarder l'écran.
- Composition d'écran, règle CSS juste dans un contexte et fausse dans un autre, total en double : seulement à
  l'écran, à la vraie largeur.
- Un serveur qui garde sa page en mémoire sert l'**ancienne** version après une modification : relancer avant de
  mesurer.
- Un onglet en arrière-plan bride les minuteries : n'y mesurer aucune fréquence.
- Un binaire embarque une copie figée du code : reconstruire avant de diagnostiquer.

## 10. Données

Fixtures fictives seulement, jamais une copie de production : skill `donnees-sensibles`.
