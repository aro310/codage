# -*- coding: utf-8 -*-


import heapq
import io
from collections import Counter
from algos.bitio import BitWriter, BitReader


# 1. Construction de l'arbre de Huffman (identique au cours, sur des octets)

class _Noeud:
    """Noeud interne de l'arbre (usage prive a ce module)."""
    __slots__ = ("symbole", "freq", "gauche", "droite")

    def __init__(self, symbole, freq, gauche=None, droite=None):
        self.symbole = symbole
        self.freq    = freq
        self.gauche  = gauche
        self.droite  = droite

    def __lt__(self, autre):
        if self.freq == autre.freq:
            # Departage : symbole le plus petit en premier (deterministe)
            s1 = self.symbole if self.symbole is not None else -1
            s2 = autre.symbole if autre.symbole is not None else -1
            return s1 < s2
        return self.freq < autre.freq


def _construire_arbre(frequences: dict[int, int]) -> _Noeud:
    """
    Construit l'arbre de Huffman depuis un dictionnaire {octet: frequence}.

    """
    tas = [_Noeud(sym, freq) for sym, freq in frequences.items()]
    heapq.heapify(tas)

    # Cas degenere : un seul symbole distinct
    if len(tas) == 1:
        seul = heapq.heappop(tas)
        heapq.heappush(tas, _Noeud(None, seul.freq, seul, _Noeud(seul.symbole, 0)))

    while len(tas) > 1:
        g = heapq.heappop(tas)
        d = heapq.heappop(tas)
        heapq.heappush(tas, _Noeud(None, g.freq + d.freq, g, d))

    return tas[0]


# 2. Extraction des longueurs de codes

def _extraire_longueurs(noeud: _Noeud, profondeur: int,
                        longueurs: dict[int, int]):
    """
    Parcours recursif de l'arbre pour noter la profondeur de chaque feuille.


    """
    if noeud is None:
        return
    if noeud.symbole is not None:          # feuille
        longueurs[noeud.symbole] = profondeur
    else:
        _extraire_longueurs(noeud.gauche, profondeur + 1, longueurs)
        _extraire_longueurs(noeud.droite, profondeur + 1, longueurs)


def calculer_longueurs(donnees: bytes) -> list[int]:
    """
    Calcule les longueurs de code Huffman pour chaque octet possible (0-255).
    Retourne une liste de 256 valeurs ; 0 = symbole absent.

    """
    frequences = Counter(donnees)
    if not frequences:
        return [0] * 256

    arbre     = _construire_arbre(frequences)
    longueurs : dict[int, int] = {}
    _extraire_longueurs(arbre, 0, longueurs)

    return [longueurs.get(i, 0) for i in range(256)]


# 3. Codes canoniques depuis les longueurs

def codes_canoniques(longueurs: list[int]) -> dict[int, tuple[int, int]]:
    """
    Calcule les codes canoniques depuis le tableau des longueurs.

    Algorithme canonique :
    1. Trier les symboles presents par longueur, puis par valeur.
    2. Le premier code est 0 (sur longueur[0] bits).
    3. Pour chaque symbole suivant : incrementer le code, puis decaler
       a gauche si la longueur augmente.

    Retourne un dict {octet: (code_entier, nb_bits)}.

    """
    # Symboles presents (longueur > 0), tries par (longueur, symbole)
    symboles = sorted(
        ((longueurs[i], i) for i in range(256) if longueurs[i] > 0)
    )
    if not symboles:
        return {}

    codes: dict[int, tuple[int, int]] = {}
    code_courant = 0
    longueur_precedente = 0

    for longueur, symbole in symboles:
        # Decaler a gauche si la longueur augmente
        code_courant <<= (longueur - longueur_precedente)
        codes[symbole] = (code_courant, longueur)
        code_courant += 1
        longueur_precedente = longueur

    return codes


# 4. Table de decodage (lookup rapide)

def table_decodage(longueurs: list[int]) -> dict[tuple[int, int], int]:
    """
    Construit la table inverse : {(code, nb_bits): octet}.
    Utilisee lors de la decompression pour retrouver le symbole.

    """
    codes = codes_canoniques(longueurs)
    return {(code, nb): sym for sym, (code, nb) in codes.items()}


# 5. Compression : ecriture de l'en-tete et du corps

def ecrire_entete(longueurs: list[int], writer: BitWriter):
    """
    Ecrit les 256 longueurs de code dans le flux (1 octet par longueur).
    La longueur maximale theorique est 255 bits, mais on la plafonne a 255.

    """
    for lon in longueurs:
        writer.ecrire_octet(min(lon, 255))


def lire_entete(reader: BitReader) -> list[int]:
    """
    Lit les 256 longueurs de code depuis le flux.

    """
    return [reader.lire_octet() for _ in range(256)]


def compresser(donnees: bytes, flux_sortie: io.RawIOBase) -> int:
    """
    Compresse 'donnees' avec Huffman canonique et ecrit dans 'flux_sortie'.
    Retourne le nombre de bits de donnees ecrits (hors en-tete).

    Format du flux :
      [ 256 octets d'en-tete (longueurs) ]
      [ bits de donnees compressees      ]
      [ 0 a 7 bits de rembourrage        ]

    """
    longueurs = calculer_longueurs(donnees)
    codes     = codes_canoniques(longueurs)

    writer = BitWriter(flux_sortie)
    ecrire_entete(longueurs, writer)

    nb_bits_donnees = 0
    for octet in donnees:
        code, nb = codes[octet]
        writer.ecrire_bits(code, nb)
        nb_bits_donnees += nb

    writer.fermer()
    return nb_bits_donnees


def decompresser(flux_entree: io.RawIOBase, nb_symboles: int) -> bytes:
    """
    Decompresse 'nb_symboles' octets depuis 'flux_entree'.
    'nb_symboles' doit etre connu (stocke dans l'en-tete du format .mbz2).

    """
    reader   = BitReader(flux_entree)
    longueurs = lire_entete(reader)
    table    = table_decodage(longueurs)

    # Longueur maximale des codes presents
    max_lon = max((l for l in longueurs if l > 0), default=0)

    resultat = bytearray()
    code_courant = 0
    nb_bits_lus  = 0

    while len(resultat) < nb_symboles:
        bit = reader.lire_bit()
        code_courant = (code_courant << 1) | bit
        nb_bits_lus += 1

        cle = (code_courant, nb_bits_lus)
        if cle in table:
            resultat.append(table[cle])
            code_courant = 0
            nb_bits_lus  = 0

        if nb_bits_lus > max_lon:
            raise ValueError(f"Code invalide apres {nb_bits_lus} bits")

    return bytes(resultat)


# Demonstration

def demo():
    texte   = b"ABRACADABRA"
    flux    = io.BytesIO()

    nb_bits = compresser(texte, flux)
    print(f"Original  : {len(texte)} octets = {len(texte)*8} bits")
    print(f"Compresse : {flux.tell()} octets ({nb_bits} bits de donnees + en-tete)")

    flux.seek(0)
    retour = decompresser(flux, len(texte))
    print(f"Decompresse : {retour}")
    print(f"Aller-retour OK : {retour == texte}")

    # Verifier que les codes canoniques ont bien la longueur attendue (23 bits)
    from collections import Counter
    freq = Counter(texte)
    lon  = calculer_longueurs(texte)
    codes = codes_canoniques(lon)
    total_bits = sum(codes[b][1] * freq[b] for b in freq)
    print(f"Longueur du message code : {total_bits} bits (attendu : 23)")

    assert retour     == texte, "Erreur d'aller-retour"
    assert total_bits == 23,    f"Longueur incorrecte : {total_bits}"
    print("\n[OK] Huffman canonique valide.")


if __name__ == "__main__":
    demo()
