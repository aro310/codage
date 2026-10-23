def mtf_encoder(donnees: bytes) -> bytes:
    """
    Applique la transformee MTF a une sequence d'octets.

    Retourne une sequence d'indices (0-255) de meme longueur.

    Exemple : si l'alphabet est [A,B,C,...] et l'entree est "BANANA" :
      B -> pos 1, alphabet devient [B,A,N,...]
      A -> pos 1, alphabet devient [A,B,N,...]
      etc.

    # Dingana : mitady ny toerana ary mampiditra ny symbole eo am-boalohany
    """
    alphabet = list(range(256))    # [0, 1, 2, ..., 255]
    sortie   = bytearray()

    for octet in donnees:
        position = alphabet.index(octet)   # O(256) — recherche lineaire
        sortie.append(position)
        # Deplacer l'octet en tete
        alphabet.pop(position)
        alphabet.insert(0, octet)

    return bytes(sortie)


def mtf_decoder(donnees: bytes) -> bytes:
    """
    Inverse de mtf_encoder : reconstitue les octets originaux depuis les indices.

    Pour chaque indice : lire l'octet a cette position, le deplacer en tete.

    # Dingana : mamaky ny toerana ary mamerina ny symbole
    """
    alphabet = list(range(256))
    sortie   = bytearray()

    for position in donnees:
        octet = alphabet[position]         # O(1) — acces direct par indice
        sortie.append(octet)
        # Meme deplacement que lors de l'encodage
        alphabet.pop(position)
        alphabet.insert(0, octet)

    return bytes(sortie)

# Demonstration
def demo():
    print("=== Move-to-Front (MTF) ===\n")

    # Exemple simple pour illustrer le principe
    cas = [
        b"BANANA",
        b"AAABBBCCC",          # groupes -> beaucoup de zeros en sortie
        b"ABCABC",
    ]

    for original in cas:
        encode = mtf_encoder(original)
        decode = mtf_decoder(encode)
        ok = "OK" if decode == original else f"ERREUR {decode!r}"

        nb_zeros = encode.count(0)
        print(f"  Original : {original!r}")
        print(f"  MTF      : {list(encode)}")
        print(f"  Zeros    : {nb_zeros}/{len(encode)} "
              f"({100*nb_zeros//len(encode)}%)  aller-retour:{ok}")
        print()

    # Verification avec des octets aleatoires
    import os
    alea = os.urandom(1000)
    assert mtf_decoder(mtf_encoder(alea)) == alea, "Echec aller-retour aleatoire"
    print("[OK] MTF valide (y compris 1000 octets aleatoires).")


if __name__ == "__main__":
    demo()
