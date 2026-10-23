import io


TAILLE_BLOC_DEFAUT = 100_000   # 100 Ko par bloc


# 1. Construction du suffix array par doublement de prefixes

def construire_suffix_array(texte: list[int]) -> list[int]:

    n = len(texte)
    if n == 0:
        return []
    if n == 1:
        return [0]

    # Rang initial : valeur de chaque caractere
    rang = texte[:]

    # Valeur sentinelle pour "hors limites" (plus petite que tout rang reel)
    SENTINELLE_RANG = min(texte) - 1

    k = 1
    while k < n:
        # Pour chaque position i : cle = (rang[i], rang[i+k] ou sentinelle)
        rang_dec = [rang[i + k] if i + k < n else SENTINELLE_RANG
                    for i in range(n)]

        sa = sorted(range(n), key=lambda i: (rang[i], rang_dec[i]))

        # Recalculer les rangs en fonction du tri
        nouveau_rang = [0] * n
        for j in range(1, n):
            # Meme cle que le precedent -> meme rang
            meme = (rang[sa[j]]     == rang[sa[j - 1]] and
                    rang_dec[sa[j]] == rang_dec[sa[j - 1]])
            nouveau_rang[sa[j]] = nouveau_rang[sa[j - 1]] + (0 if meme else 1)

        rang = nouveau_rang

        # Si tous les rangs sont distincts, le suffix array est complet
        if rang[sa[-1]] == n - 1:
            break

        k *= 2

    # Tri final si on n'a pas fini dans la boucle
    if k >= n:
        sa = sorted(range(n), key=lambda i: rang[i])

    return sa


# 2. Encodage BWT d'un bloc

def bwt_encode_bloc(bloc: bytes) -> tuple[bytes, int]:
    """
    Applique la BWT a un bloc d'octets.

    Methode :
    1. Ajouter une sentinelle -1 a la fin (garantit des suffixes distincts).
    2. Construire le suffix array.
    3. Extraire la derniere colonne (avant chaque suffixe dans la rotation).
    4. Retirer la sentinelle de la sortie ; retourner son indice (= index BWT).

    Retourne (bwt: bytes, index: int).

    """
    n     = len(bloc)
    texte = list(bloc) + [-1]    # sentinelle = -1, plus petite que tout octet

    sa  = construire_suffix_array(texte)
    bwt = [texte[(s - 1) % (n + 1)] for s in sa]   # derniere colonne

    # La sentinelle (-1) apparait exactement une fois dans la sortie BWT
    index = next(i for i, v in enumerate(bwt) if v == -1)

    # Retirer la sentinelle et convertir en bytes
    bwt_octets = bytes(v for v in bwt if v >= 0)
    return bwt_octets, index


# 3. Decodage BWT d'un bloc (LF-mapping)

def bwt_decode_bloc(bwt: bytes, index: int) -> bytes:
    """
    Inverse la BWT d'un bloc via le LF-mapping.

    Algorithme :
    1. Reinserir la sentinelle a la position 'index' dans la colonne L.
    2. Calculer la colonne F = tri de L.
    3. Calculer le LF-mapping : lf[i] = position de la i-eme occurrence de L[i] dans F.
    4. Remonter depuis 'index' pendant n+1 pas, lire col_F[ligne].
    5. Supprimer la sentinelle du resultat.

    """
    # Reinserir la sentinelle dans la colonne L (= bwt avec sentinelle)
    col_L = list(bwt[:index]) + [-1] + list(bwt[index:])
    n_ext = len(col_L)   # = len(bwt) + 1

    # Colonne F = tri de L
    col_F = sorted(col_L)

    # Premiere occurrence de chaque symbole dans F
    premier_dans_F: dict[int, int] = {}
    for i, sym in enumerate(col_F):
        if sym not in premier_dans_F:
            premier_dans_F[sym] = i

    # Rang de chaque occurrence dans L (combien de fois ce symbole est apparu avant)
    comptes: dict[int, int] = {}
    rang_dans_L = [0] * n_ext
    for i, sym in enumerate(col_L):
        rang_dans_L[i] = comptes.get(sym, 0)
        comptes[sym]   = rang_dans_L[i] + 1

    # LF-mapping
    lf = [premier_dans_F[col_L[i]] + rang_dans_L[i] for i in range(n_ext)]

    # Reconstruction : partir de 'index', lire col_L[ligne] a chaque pas,
    # puis inverser — car on lit le texte de la fin vers le debut.
    resultat = []
    ligne    = index
    for _ in range(n_ext):
        resultat.append(col_L[ligne])
        ligne = lf[ligne]

    resultat.reverse()

    # Supprimer la sentinelle (-1) du resultat
    return bytes(v for v in resultat if v >= 0)


# 4. Interface par blocs (utilisee par formats/mybzip2.py)

def encoder_par_blocs(donnees: bytes,
                      taille_bloc: int = TAILLE_BLOC_DEFAUT) -> list[tuple[bytes, int]]:
    """
    Decoupe 'donnees' en blocs et applique BWT a chacun.
    Retourne une liste de (bwt_bloc, index) pour chaque bloc.

    # Hafaingana : O((n/B) x B log^2 B) = O(n log^2 B) — B = taille du bloc
    """
    blocs = []
    for debut in range(0, len(donnees), taille_bloc):
        bloc = donnees[debut: debut + taille_bloc]
        blocs.append(bwt_encode_bloc(bloc))
    return blocs


def decoder_par_blocs(blocs: list[tuple[bytes, int]]) -> bytes:
    """
    Inverse encoder_par_blocs : reconstitue les donnees originales.

    # Hafaingana : O(n log n) — LF-mapping sur chaque bloc
    """
    return b"".join(bwt_decode_bloc(bwt, idx) for bwt, idx in blocs)


# Demonstration

def demo():
    print("=== BWT production (suffix array + sentinelle) ===\n")

    # Exemple du cours
    bwt, index = bwt_encode_bloc(b"BANANA")
    retour      = bwt_decode_bloc(bwt, index)
    print(f"BANANA  -> BWT={bwt!r}  index={index}")
    print(f"  Cours : BWT='NNBAAA' index=3")
    print(f"  Aller-retour : {retour!r}  {'OK' if retour == b'BANANA' else 'ERREUR'}")
    print()

    # Verification : la BWT avec sentinelle peut differir de la version sans sentinelle
    # car la sentinelle change l'ordre des rotations. Ce qui compte : l'aller-retour.

    # Cas binaires (impossible sans sentinelle)
    cas = [
        b"",
        b"A",
        b"\x00\x01\x02",
        b"AAAAAAAAAAAA",
        b"ABCABCABC",
    ]
    for original in cas:
        bwt, idx = bwt_encode_bloc(original)
        retour    = bwt_decode_bloc(bwt, idx)
        ok = "OK" if retour == original else f"ERREUR {retour!r}"
        apercu = repr(original)[:30]
        print(f"  {apercu:32s} -> index={idx:4d}  aller-retour:{ok}")

    # Test sur un bloc de taille reelle
    import os
    gros = os.urandom(5000)
    blocs  = encoder_par_blocs(gros, taille_bloc=1000)
    retour = decoder_par_blocs(blocs)
    ok = "OK" if retour == gros else "ERREUR"
    print(f"\n  5000 octets aleatoires en 5 blocs : aller-retour {ok}")

    print("\n[OK] BWT production validee.")


if __name__ == "__main__":
    demo()
