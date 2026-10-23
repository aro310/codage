import io
import math
import struct
import zlib   # uniquement pour crc32

from algos.lz77        import encoder_lz77, decoder_lz77, Litteral, Reference
from algos.lz77        import TAILLE_MIN_MATCH, TAILLE_FENETRE
from algos.range_coder import (RangeEncoder, RangeDecoder, ModeleAdaptatif,
                                nouveaux_modeles, encoder_entier, decoder_entier)


MAGIC            = b'MLZM'
VERSION          = b'\x01'
NB_BITS_LONGUEUR = 8    # encode longueur - 3 sur 8 bits (0..255 = long 3..258)


# Utilitaires

def _crc32(donnees: bytes) -> int:
    return zlib.crc32(donnees) & 0xFFFFFFFF


def _nb_bits_offset(taille_fenetre: int) -> int:
    """
    Calcule le nombre de bits necessaires pour encoder un offset dans la fenetre.
    Exemple : fenetre 64 Ko -> 16 bits.
    """
    if taille_fenetre <= 1:
        return 1
    return math.ceil(math.log2(taille_fenetre))


# Contexte de modeles pour le range coder

class ModelesLZMA:
    """
    Groupe les modeles adaptatifs utilises pour encoder/decoder les tokens.
    Encodeur et decodeur doivent creer le meme ModelesLZMA et l'utiliser
    dans le meme ordre -> les probabilites restent synchronisees.

    # Dingana : modeles independants pour chaque type de symbole
    """

    def __init__(self, nb_bits_off: int):
        self.is_ref  = ModeleAdaptatif()                  # 1 bit : ref ou literal ?
        self.lit     = nouveaux_modeles(8)                # 8 bits du literal
        self.lon     = nouveaux_modeles(NB_BITS_LONGUEUR) # 8 bits de longueur
        self.off     = nouveaux_modeles(nb_bits_off)      # M bits d'offset
        self.nb_bits_off = nb_bits_off


# Encodage d'un seul token

def _encoder_token(enc: RangeEncoder, tok, modeles: ModelesLZMA):
    """
    Encode un token (Litteral ou Reference) dans le range coder.

    # Dingana : chaque token encode avec ses propres modeles adaptatifs
    """
    if isinstance(tok, Litteral):
        enc.encoder_bit(0, modeles.is_ref.prob)
        modeles.is_ref.mettre_a_jour(0)
        encoder_entier(enc, tok.octet, 8, modeles.lit)
    else:
        enc.encoder_bit(1, modeles.is_ref.prob)
        modeles.is_ref.mettre_a_jour(1)
        lon_extra = tok.longueur - TAILLE_MIN_MATCH   # 0..255
        off_extra = tok.offset   - 1                  # 0..(W-1)
        encoder_entier(enc, lon_extra, NB_BITS_LONGUEUR, modeles.lon)
        encoder_entier(enc, off_extra, modeles.nb_bits_off, modeles.off)


# Decodage d'un seul token

def _decoder_token(dec: RangeDecoder, modeles: ModelesLZMA):
    """
    Decode un token depuis le range coder.
    Retourne un Litteral ou une Reference.

    # Dingana : mamerina ny token iray avy amin'ny range coder
    """
    is_ref = dec.decoder_bit(modeles.is_ref.prob)
    modeles.is_ref.mettre_a_jour(is_ref)

    if is_ref == 0:
        valeur = decoder_entier(dec, 8, modeles.lit)
        return Litteral(valeur)
    else:
        lon_extra = decoder_entier(dec, NB_BITS_LONGUEUR, modeles.lon)
        off_extra = decoder_entier(dec, modeles.nb_bits_off, modeles.off)
        return Reference(off_extra + 1, lon_extra + TAILLE_MIN_MATCH)


# Interface publique : compression / decompression

def compresser(entree: io.RawIOBase, sortie: io.RawIOBase,
               taille_fenetre: int = TAILLE_FENETRE,
               lazy: bool = False,
               verbose: bool = False) -> dict:
    """
    Compresse le flux 'entree' vers 'sortie' au format .mlzma.

    Etapes :
      1. Lire toutes les donnees (necessite taille_orig pour l'en-tete).
      2. LZ77 -> tokens.
      3. Range coder -> flux compresse.
      4. Ecrire en-tete + flux.

    # Hafaingana : O(n) — LZ77 O(n) + range coder O(n)
    """
    donnees     = entree.read()
    crc32       = _crc32(donnees)
    taille_orig = len(donnees)
    nb_bits_off = _nb_bits_offset(taille_fenetre)

    if verbose:
        print(f"  LZ77 (fenetre={taille_fenetre//1024}Ko, lazy={lazy})...")

    tokens  = encoder_lz77(donnees, taille_fenetre, lazy)
    modeles = ModelesLZMA(nb_bits_off)
    enc     = RangeEncoder()

    for tok in tokens:
        _encoder_token(enc, tok, modeles)

    flux_rc = enc.finaliser()

    if verbose:
        nb_ref = sum(1 for t in tokens if isinstance(t, Reference))
        print(f"  {len(tokens)} tokens ({nb_ref} references) -> {len(flux_rc)} octets RC")

    # Ecrire l'en-tete
    entete = (MAGIC + VERSION
              + struct.pack('>IQIb', crc32, taille_orig,
                            taille_fenetre, int(lazy)))
    sortie.write(entete)
    sortie.write(flux_rc)

    taille_comp = len(entete) + len(flux_rc)
    return {
        'taille_orig': taille_orig,
        'taille_comp': taille_comp,
        'ratio':       taille_comp / max(taille_orig, 1),
        'nb_tokens':   len(tokens),
    }


def decompresser(entree: io.RawIOBase, sortie: io.RawIOBase,
                 verbose: bool = False) -> dict:
    """
    Decompresse un flux .mlzma.
    Verifie le CRC32 ; leve ValueError si le fichier est corrompu.

    # Hafaingana : O(n) — range coder O(n) + reconstruction LZ77 O(n)
    """
    # Lire et valider l'en-tete
    magic = entree.read(4)
    if magic != MAGIC:
        raise ValueError(f"Magic invalide : {magic!r} (attendu {MAGIC!r})")
    version = entree.read(1)
    if version != VERSION:
        raise ValueError(f"Version inconnue : {version!r}")

    crc32_attendu, taille_orig, taille_fenetre, lazy_flag = \
        struct.unpack('>IQIb', entree.read(17))
    nb_bits_off = _nb_bits_offset(taille_fenetre)

    flux_rc = entree.read()
    modeles = ModelesLZMA(nb_bits_off)
    dec     = RangeDecoder(flux_rc)

    # Decoder les tokens jusqu'a avoir reconstitue taille_orig octets
    tokens  = []
    octets_reconstitues = 0

    while octets_reconstitues < taille_orig:
        tok = _decoder_token(dec, modeles)
        tokens.append(tok)
        if isinstance(tok, Litteral):
            octets_reconstitues += 1
        else:
            octets_reconstitues += tok.longueur

    donnees = decoder_lz77(tokens)[:taille_orig]

    # Verifier l'integrite
    crc32_calcule = _crc32(donnees)
    if crc32_calcule != crc32_attendu:
        raise ValueError(
            f"CRC32 incorrect : attendu {crc32_attendu:#010x}, "
            f"calcule {crc32_calcule:#010x}"
        )

    sortie.write(donnees)
    return {
        'taille_decomp': len(donnees),
        'nb_tokens':     len(tokens),
        'crc32_ok':      True,
    }


# Fonctions pratiques sur fichiers

def compresser_fichier(chemin_entree: str, chemin_sortie: str,
                       taille_fenetre: int = TAILLE_FENETRE,
                       lazy: bool = False,
                       verbose: bool = False) -> dict:
    with open(chemin_entree, 'rb') as f_in, \
         open(chemin_sortie, 'wb') as f_out:
        return compresser(f_in, f_out, taille_fenetre, lazy, verbose)


def decompresser_fichier(chemin_entree: str, chemin_sortie: str,
                         verbose: bool = False) -> dict:
    with open(chemin_entree, 'rb') as f_in, \
         open(chemin_sortie, 'wb') as f_out:
        return decompresser(f_in, f_out, verbose)


# Demonstration

def demo():
    import hashlib

    print("=== mylzma — tests aller-retour ===\n")
    print(f"{'Apercu':>24}  {'Orig':>7}  {'Comp':>7}  {'Ratio':>6}  {'OK':>4}")
    print("-" * 55)

    exemples = [
        b"",
        b"A",
        b"ABRACADABRA" * 100,
        b"Hello, monde! " * 500,
        bytes(range(256)) * 10,
        b"AAABBBCCCAAABBBCCC" * 50,
    ]

    for original in exemples:
        flux_comp  = io.BytesIO()
        compresser(io.BytesIO(original), flux_comp)
        taille_comp = flux_comp.tell()

        flux_comp.seek(0)
        flux_decomp = io.BytesIO()
        decompresser(flux_comp, flux_decomp)
        retour = flux_decomp.getvalue()

        sha_ok = hashlib.sha256(retour).digest() == hashlib.sha256(original).digest()
        ratio  = taille_comp / max(len(original), 1)
        ok     = "OK" if (retour == original and sha_ok) else "ERREUR"
        apercu = repr(original[:16])[2:-1]

        print(f"  {apercu:>24}  {len(original):>7}  {taille_comp:>7}  "
              f"{ratio:>6.2f}  {ok}")

    print("\n[OK] mylzma valide.")


if __name__ == "__main__":
    demo()
