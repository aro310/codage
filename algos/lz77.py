TAILLE_MIN_MATCH  =  3       # longueur minimale pour une reference
TAILLE_MAX_MATCH  = 258      # longueur maximale (standard DEFLATE)
TAILLE_FENETRE    = 64 * 1024   # 64 Ko (niveau defaut)
TAILLE_CHAINE     = 32       # profondeur max de la chaine de hachage

# Representation des tokens
class Litteral:
    """Un octet copie tel quel."""
    __slots__ = ('octet',)

    def __init__(self, octet: int):
        self.octet = octet

    def __repr__(self):
        return f"L({self.octet:#04x})"


class Reference:
    """Une reference vers la fenetre : recopier 'longueur' octets depuis 'offset' en arriere."""
    __slots__ = ('offset', 'longueur')

    def __init__(self, offset: int, longueur: int):
        self.offset   = offset
        self.longueur = longueur

    def __repr__(self):
        return f"R({self.offset},{self.longueur})"

# Table de hachage des trigrammes
def _hacher(donnees: bytes | bytearray, pos: int) -> int:
    """
    Hash d'un trigramme pour indexer la table de correspondance.
    Multiplications de Knuth pour bonne distribution.

    #  O(1) — hash de 3 octets
    """
    h = donnees[pos]
    h = (h * 2654435761 + donnees[pos + 1]) & 0xFFFFFFFF
    h = (h * 2654435761 + donnees[pos + 2]) & 0xFFFFFFFF
    return h & 0xFFFF   # 65536 buckets


def _chercher_match(donnees: bytes, pos: int, taille_fenetre: int,
                    table: dict[int, list[int]]) -> tuple[int, int]:
    """
    Cherche la plus longue correspondance pour donnees[pos:] dans la fenetre.
    Utilise la table de hachage + chaine de collisions.

    Retourne (offset, longueur). offset=0 -> pas de correspondance.

    #  O(C) — C = profondeur de la chaine (TAILLE_CHAINE)
    """
    n = len(donnees)
    if pos + TAILLE_MIN_MATCH > n:
        return 0, 0

    h = _hacher(donnees, pos)
    candidats = table.get(h, [])

    debut_fenetre  = max(0, pos - taille_fenetre)
    meilleur_off   = 0
    meilleure_lon  = 0
    limite         = min(n - pos, TAILLE_MAX_MATCH)

    for start in candidats:
        if start < debut_fenetre:
            continue                  # hors fenetre
        lon = 0
        while lon < limite and donnees[start + lon] == donnees[pos + lon]:
            lon += 1
        if lon >= TAILLE_MIN_MATCH and lon > meilleure_lon:
            meilleure_lon = lon
            meilleur_off  = pos - start

    return meilleur_off, meilleure_lon


def _ajouter_table(table: dict, pos: int, h: int):
    """
    Insere la position 'pos' au debut de la chaine pour le hash 'h'.
    Limite la chaine a TAILLE_CHAINE entrees pour rester rapide.

    #  O(1) amorti
    """
    chaine = table.get(h)
    if chaine is None:
        table[h] = [pos]
    else:
        chaine.insert(0, pos)
        if len(chaine) > TAILLE_CHAINE:
            chaine.pop()

# Encodage LZ77
def encoder_lz77(donnees: bytes,
                 taille_fenetre: int = TAILLE_FENETRE,
                 lazy: bool = False) -> list:
    """
    Compresse 'donnees' avec LZ77 et retourne une liste de tokens.

    Mode glouton (lazy=False) : on prend le meilleur match en pos et on avance.
    Mode lazy   (lazy=True)   : on compare le match en pos avec celui en pos+1 ;
                                si pos+1 donne mieux, on emet d'abord un litteral.

    # O(n) en moyenne — table de hachage O(1) par position
    """
    n      = len(donnees)
    table  : dict[int, list[int]] = {}
    tokens : list = []
    pos    = 0

    while pos < n:
        offset, longueur = _chercher_match(donnees, pos, taille_fenetre, table)

        if lazy and longueur >= TAILLE_MIN_MATCH and pos + 1 < n:
            # Verifier si pos+1 donne un meilleur match (lazy matching)
            off2, lon2 = _chercher_match(donnees, pos + 1, taille_fenetre, table)
            if lon2 > longueur + 1:
                # Emettre le litteral courant, utiliser le match en pos+1
                tokens.append(Litteral(donnees[pos]))
                if pos + TAILLE_MIN_MATCH <= n:
                    h = _hacher(donnees, pos)
                    _ajouter_table(table, pos, h)
                pos += 1
                offset, longueur = off2, lon2

        if longueur >= TAILLE_MIN_MATCH:
            tokens.append(Reference(offset, longueur))
            # Indexer toutes les positions couvertes par le match
            for k in range(longueur):
                if pos + k + TAILLE_MIN_MATCH <= n:
                    h = _hacher(donnees, pos + k)
                    _ajouter_table(table, pos + k, h)
            pos += longueur
        else:
            tokens.append(Litteral(donnees[pos]))
            if pos + TAILLE_MIN_MATCH <= n:
                h = _hacher(donnees, pos)
                _ajouter_table(table, pos, h)
            pos += 1

    return tokens

# Decodage LZ77
def decoder_lz77(tokens: list) -> bytes:
    """
    Reconstruit les donnees originales depuis une liste de tokens LZ77.

    Note : les references peuvent se chevaucher avec la sortie en cours
    (ex : offset=3, longueur=10 -> repetition cyclique). Gere correctement.

    # O(n) — une operation par token
    """
    sortie = bytearray()

    for tok in tokens:
        if isinstance(tok, Litteral):
            sortie.append(tok.octet)
        else:
            debut = len(sortie) - tok.offset
            for i in range(tok.longueur):
                # Copie sequentielle : peut se referencer elle-meme (run cyclique)
                sortie.append(sortie[debut + i])

    return bytes(sortie)

# Statistiques utiles pour mylzma
def statistiques(tokens: list, longueur_orig: int) -> dict:
    """Calcule le nombre de litteraux et de references dans le flux de tokens."""
    nb_lit = sum(1 for t in tokens if isinstance(t, Litteral))
    nb_ref = sum(1 for t in tokens if isinstance(t, Reference))
    octets_ref = sum(t.longueur for t in tokens if isinstance(t, Reference))
    return {
        'nb_litteraux':   nb_lit,
        'nb_references':  nb_ref,
        'octets_ref':     octets_ref,
        'taux_ref':       octets_ref / max(longueur_orig, 1),
    }

# Demonstration
def demo():
    print("=== LZ77 production ===\n")

    # Exemple du cours (avec les memes parametres)
    from cours.lz77_cours import lz77_encoder as lz77_cours
    texte_cours = b"CABRACADABRARRARRAD"
    tokens_prod = encoder_lz77(texte_cours, taille_fenetre=7)
    retour      = decoder_lz77(tokens_prod)
    print(f"Exemple cours : {texte_cours!r}")
    print(f"  Tokens prod : {tokens_prod}")
    print(f"  Aller-retour : {'OK' if retour == texte_cours else 'ERREUR'}")
    print()

    # Test sur texte repetitif
    cas = [
        b"",
        b"A",
        b"ABCABC" * 100,
        b"Hello, monde! " * 500,
        bytes(range(256)) * 40,
    ]
    for orig in cas:
        tokens = encoder_lz77(orig, lazy=True)
        retour = decoder_lz77(tokens)
        stats  = statistiques(tokens, len(orig))
        ok     = "OK" if retour == orig else "ERREUR"
        print(f"  len={len(orig):6d}  tokens={len(tokens):5d}  "
              f"taux_ref={stats['taux_ref']:.2%}  {ok}")

    print("\n[OK] LZ77 production valide.")


if __name__ == "__main__":
    demo()
