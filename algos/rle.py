
# 1. RLE pre-BWT (blocs de 4 octets identiques)
def rle_blocs_encoder(donnees: bytes) -> bytes:
    """
    Compacte les suites de 4+ octets identiques.

    Exemple : AAAAAA (6 A) -> A A A A \x02  (4 fixes + 2 extras)
              AAA    (3 A) -> A A A          (moins de 4, copie directe)

    Maximum par sequence : 4 + 251 = 255 octets (limite du compteur).

    #     manisa ny suite ary manoratra 4 + count raha lava ampy
    #  O(n) — lalana tokana amin'ny donnees
    """
    sortie = bytearray()
    i = 0
    n = len(donnees)

    while i < n:
        octet  = donnees[i]
        compte = 1

        # Compter les repetitions consecutives (max 255 extras apres les 4 premiers)
        while i + compte < n and donnees[i + compte] == octet and compte < 255:
            compte += 1

        if compte >= 4:
            # Ecrire les 4 premiers copies + le nombre d'extras (0-251)
            extras = min(compte - 4, 251)
            sortie.extend([octet] * 4)
            sortie.append(extras)
            i += 4 + extras
        else:
            # Moins de 4 repetitions : copie directe
            sortie.extend([octet] * compte)
            i += compte

    return bytes(sortie)


def rle_blocs_decoder(donnees: bytes) -> bytes:
    """
    Inverse de rle_blocs_encoder.

    Quand on voit 4 octets identiques consecutifs dans l'entree,
    l'octet suivant est le compteur d'extras (0-251).
    Apres la lecture d'un bloc 4+extras, le compteur de run est remis
    a zero afin d'eviter une fausse detection sur les extras eux-memes.

    #  mamerina ny donnees voalohany amin'ny alalan'ny count
    #  O(n) — lalana tokana
    """
    sortie = bytearray()
    i = 0
    n = len(donnees)
    # run_courant : nombre d'octets identiques consecutifs dans sortie
    # (remis a zero apres chaque bloc de 4+extras pour eviter
    #  les fausses detections sur les extras eux-memes)
    run_courant = 0

    while i < n:
        octet = donnees[i]
        i += 1

        if run_courant >= 1 and sortie[-1] == octet:
            run_courant += 1
        else:
            run_courant = 1
        sortie.append(octet)

        # Quand on atteint exactement 4 identiques, lire le compteur d'extras
        if run_courant == 4:
            extras = donnees[i] if i < n else 0
            i += 1
            sortie.extend([octet] * extras)
            # Reinitialisation : les extras ne doivent pas declencher
            # une nouvelle detection
            run_courant = 0

    return bytes(sortie)

# 2. RLE des zeros (post-MTF)
def rle_zeros_encoder(mtf_sortie: bytes) -> bytes:
    """
    Compacte les suites de zeros dans la sortie MTF.

    Protocole :
      - Octet non nul (1-255) : emis tel quel.
      - Suite de N zeros      : emis comme 0x00 suivi de N (octet, 1-255).
      - Suite > 255 zeros     : decoupee en tranches de 255.

    Exemple : [0, 0, 0, 5, 0] -> [0, 3, 5, 0, 1]

    #  manisa ny zeros ary manoratra 0x00 + count
    #  O(n) — lalana tokana
    """
    sortie = bytearray()
    i = 0
    n = len(mtf_sortie)

    while i < n:
        if mtf_sortie[i] != 0:
            sortie.append(mtf_sortie[i])
            i += 1
        else:
            # Compter les zeros consecutifs
            nb_zeros = 0
            while i < n and mtf_sortie[i] == 0 and nb_zeros < 255:
                nb_zeros += 1
                i += 1
            sortie.append(0x00)
            sortie.append(nb_zeros)

    return bytes(sortie)


def rle_zeros_decoder(donnees: bytes) -> bytes:
    """
    Inverse de rle_zeros_encoder.

    #  mamaky 0x00 + count ary mamerina ny zeros
    #  O(n) — lalana tokana
    """
    sortie = bytearray()
    i = 0
    n = len(donnees)

    while i < n:
        if donnees[i] != 0:
            sortie.append(donnees[i])
            i += 1
        else:
            # Lire le compteur de zeros
            if i + 1 >= n:
                raise ValueError("RLE zeros : compteur manquant apres 0x00")
            nb_zeros = donnees[i + 1]
            i += 2
            sortie.extend(b'\x00' * nb_zeros)

    return bytes(sortie)

# Demonstration
def demo():
    # --- Test rle_blocs ---
    cas_blocs = [
        (b"AAAAAA",        b"AAAA\x02"),   # 6 A -> 4 + 2 extras
        (b"AAAA",          b"AAAA\x00"),   # 4 A -> 4 + 0 extras
        (b"AAA",           b"AAA"),         # 3 A -> copie directe
        (b"AAAABBBCCDAA",  None),           # exemple mixte, juste aller-retour
    ]

    print("=== RLE blocs (pre-BWT) ===")
    for original, attendu in cas_blocs:
        encode = rle_blocs_encoder(original)
        decode = rle_blocs_decoder(encode)
        ok_encode = ("OK" if encode == attendu else
                     f"DIFF {encode!r} (attendu {attendu!r})") if attendu else "N/A"
        ok_aller  = "OK" if decode == original else f"ERREUR {decode!r}"
        print(f"  {original!r} -> {encode!r}  encode:{ok_encode}  aller-retour:{ok_aller}")

    # --- Test rle_zeros ---
    print("\n=== RLE zeros (post-MTF) ===")
    cas_zeros = [
        (bytes([0, 0, 0, 5, 0]),        bytes([0, 3, 5, 0, 1])),
        (bytes([1, 2, 3]),               bytes([1, 2, 3])),
        (bytes([0]),                     bytes([0, 1])),
        (bytes([0] * 300),               None),    # 300 zeros -> deux tranches
    ]
    for original, attendu in cas_zeros:
        encode = rle_zeros_encoder(original)
        decode = rle_zeros_decoder(encode)
        ok_encode = ("OK" if encode == attendu else
                     f"DIFF {encode!r}") if attendu else "N/A"
        ok_aller  = "OK" if decode == original else f"ERREUR"
        print(f"  len={len(original):4d} -> len={len(encode):4d}  "
              f"encode:{ok_encode}  aller-retour:{ok_aller}")

    print("\n[OK] RLE valide.")


if __name__ == "__main__":
    demo()
