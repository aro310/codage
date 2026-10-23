import io
import struct
import zlib  # utilise uniquement pour crc32 (pas pour la compression)

from algos.rle     import rle_blocs_encoder, rle_blocs_decoder
from algos.rle     import rle_zeros_encoder, rle_zeros_decoder
from algos.bwt     import bwt_encode_bloc,   bwt_decode_bloc
from algos.mtf     import mtf_encoder,        mtf_decoder
from algos.huffman import compresser as huffman_compresser
from algos.huffman import decompresser as huffman_decompresser


MAGIC         = b'MBZ2'
VERSION       = b'\x01'
TAILLE_BLOC   = 100_000   # 100 Ko par bloc (ajustable selon --niveau)


# Utilitaires binaires

def _crc32(donnees: bytes) -> int:
    """Calcule le CRC32 des donnees (entier non signe 32 bits)."""
    return zlib.crc32(donnees) & 0xFFFFFFFF


def _pack_entete_fichier(crc32: int, nb_blocs: int) -> bytes:
    """Serialise l'en-tete global du fichier."""
    return MAGIC + VERSION + struct.pack('>II', crc32, nb_blocs)


def _unpack_entete_fichier(flux: io.RawIOBase) -> tuple[int, int]:
    """
    Lit et valide l'en-tete global.
    Retourne (crc32_original, nb_blocs).
    Leve ValueError si le magic ou la version est invalide.
    """
    magic = flux.read(4)
    if magic != MAGIC:
        raise ValueError(f"Magic number invalide : {magic!r} (attendu {MAGIC!r})")
    version = flux.read(1)
    if version != VERSION:
        raise ValueError(f"Version inconnue : {version!r}")
    crc32, nb_blocs = struct.unpack('>II', flux.read(8))
    return crc32, nb_blocs


def _pack_entete_bloc(taille_orig: int, nb_sym: int,
                      bwt_index: int, taille_huff: int) -> bytes:
    """Serialise l'en-tete d'un bloc."""
    return struct.pack('>IIII', taille_orig, nb_sym, bwt_index, taille_huff)


def _unpack_entete_bloc(flux: io.RawIOBase) -> tuple[int, int, int, int]:
    """Lit l'en-tete d'un bloc. Retourne (taille_orig, nb_sym, bwt_index, taille_huff)."""
    return struct.unpack('>IIII', flux.read(16))


# Compression d'un seul bloc

def _compresser_bloc(bloc: bytes) -> bytes:
    """
    Compresse un seul bloc de donnees et retourne les octets du bloc compresse
    (en-tete de bloc + donnees Huffman).

    Etapes :
      1. RLE blocs  : reduit les longues repetitions
      2. BWT        : regroupe les octets similaires
      3. MTF        : transforme en petits entiers (beaucoup de zeros)
      4. RLE zeros  : compacte les suites de zeros
      5. Huffman    : compression entropique finale

    # Dingana : pipeline rle_blocs -> BWT -> MTF -> rle_zeros -> Huffman
    """
    taille_orig = len(bloc)

    # Etape 1 : RLE initial (pre-BWT)
    apres_rle_blocs = rle_blocs_encoder(bloc)

    # Etape 2 : BWT
    bwt_data, bwt_index = bwt_encode_bloc(apres_rle_blocs)

    # Etape 3 : MTF
    apres_mtf = mtf_encoder(bwt_data)

    # Etape 4 : RLE des zeros
    apres_rle_zeros = rle_zeros_encoder(apres_mtf)

    # Etape 5 : Huffman canonique
    flux_huff = io.BytesIO()
    huffman_compresser(apres_rle_zeros, flux_huff)
    donnees_huff  = flux_huff.getvalue()
    nb_sym        = len(apres_rle_zeros)   # nombre de symboles a decoder

    entete = _pack_entete_bloc(taille_orig, nb_sym, bwt_index, len(donnees_huff))
    return entete + donnees_huff


# Decompression d'un seul bloc

def _decompresser_bloc(flux: io.RawIOBase) -> bytes:
    """
    Lit et decompresse un bloc depuis le flux.
    Retourne les donnees originales du bloc.

    # Dingana : pipeline inverse Huffman -> rle_zeros^-1 -> MTF^-1 -> BWT^-1 -> rle_blocs^-1
    """
    taille_orig, nb_sym, bwt_index, taille_huff = _unpack_entete_bloc(flux)

    donnees_huff = flux.read(taille_huff)
    flux_huff    = io.BytesIO(donnees_huff)

    # Etape 5^-1 : Huffman
    apres_rle_zeros = huffman_decompresser(flux_huff, nb_sym)

    # Etape 4^-1 : RLE zeros
    apres_mtf = rle_zeros_decoder(apres_rle_zeros)

    # Etape 3^-1 : MTF
    bwt_data = mtf_decoder(apres_mtf)

    # Etape 2^-1 : BWT
    apres_rle_blocs = bwt_decode_bloc(bwt_data, bwt_index)

    # Etape 1^-1 : RLE blocs
    bloc = rle_blocs_decoder(apres_rle_blocs)

    return bloc


# Interface publique

def compresser(entree: io.RawIOBase, sortie: io.RawIOBase,
               taille_bloc: int = TAILLE_BLOC,
               verbose: bool = False) -> dict:
    """
    Compresse le flux 'entree' vers le flux 'sortie' au format .mbz2.

    Retourne un dictionnaire de statistiques :
      {'taille_orig', 'taille_comp', 'ratio', 'nb_blocs'}

    # Hafaingana : O(n log^2 n) — dominee par la BWT sur chaque bloc
    """
    # Lire toutes les donnees pour le CRC32 et le decompte de blocs
    donnees = entree.read()
    crc32   = _crc32(donnees)

    # Comprimer chaque bloc
    blocs_comprimes = []
    for debut in range(0, max(len(donnees), 1), taille_bloc):
        bloc = donnees[debut: debut + taille_bloc]
        if not bloc and debut > 0:
            break
        blocs_comprimes.append(_compresser_bloc(bloc))
        if verbose:
            print(f"  Bloc {len(blocs_comprimes):3d} : {len(bloc):7d} octets -> "
                  f"{len(blocs_comprimes[-1]):7d} octets")

    # Ecrire l'en-tete global
    sortie.write(_pack_entete_fichier(crc32, len(blocs_comprimes)))
    # Ecrire les blocs
    for bloc_comp in blocs_comprimes:
        sortie.write(bloc_comp)

    taille_orig = len(donnees)
    taille_comp = sortie.tell() if hasattr(sortie, 'tell') else -1
    ratio = taille_comp / taille_orig if taille_orig > 0 else 1.0

    return {
        'taille_orig': taille_orig,
        'taille_comp': taille_comp,
        'ratio':       ratio,
        'nb_blocs':    len(blocs_comprimes),
    }


def decompresser(entree: io.RawIOBase, sortie: io.RawIOBase,
                 verbose: bool = False) -> dict:
    """
    Decompresse un flux .mbz2 vers 'sortie'.
    Verifie le CRC32 : leve ValueError si les donnees sont corrompues.

    Retourne un dictionnaire de statistiques.

    # Hafaingana : O(n log n) — dominee par le LF-mapping de la BWT
    """
    crc32_attendu, nb_blocs = _unpack_entete_fichier(entree)

    blocs = []
    for i in range(nb_blocs):
        bloc = _decompresser_bloc(entree)
        blocs.append(bloc)
        if verbose:
            print(f"  Bloc {i + 1:3d} decompresse : {len(bloc):7d} octets")

    donnees = b"".join(blocs)

    # Verification d'integrite
    crc32_calcule = _crc32(donnees)
    if crc32_calcule != crc32_attendu:
        raise ValueError(
            f"CRC32 incorrect : attendu {crc32_attendu:#010x}, "
            f"calcule {crc32_calcule:#010x} — fichier corrompu"
        )

    sortie.write(donnees)
    return {
        'taille_decomp': len(donnees),
        'nb_blocs':      nb_blocs,
        'crc32_ok':      True,
    }


# Fonctions pratiques sur fichiers

def compresser_fichier(chemin_entree: str, chemin_sortie: str,
                       taille_bloc: int = TAILLE_BLOC,
                       verbose: bool = False) -> dict:
    """Compresse un fichier et ecrit le resultat dans un autre fichier."""
    with open(chemin_entree, 'rb') as f_in, \
         open(chemin_sortie, 'wb') as f_out:
        return compresser(f_in, f_out, taille_bloc, verbose)


def decompresser_fichier(chemin_entree: str, chemin_sortie: str,
                         verbose: bool = False) -> dict:
    """Decompresse un fichier .mbz2 vers un fichier de sortie."""
    with open(chemin_entree, 'rb') as f_in, \
         open(chemin_sortie, 'wb') as f_out:
        return decompresser(f_in, f_out, verbose)


# Demonstration

def demo():
    import hashlib, time

    exemples = [
        b"",
        b"A",
        b"ABRACADABRA" * 100,
        b"Hello, monde! " * 500,
        bytes(range(256)) * 10,
    ]

    print("=== mybzip2 — tests aller-retour ===\n")
    print(f"{'Entree':>20}  {'Orig':>7}  {'Comp':>7}  {'Ratio':>6}  {'SHA256':>8}")
    print("-" * 60)

    for original in exemples:
        sha_orig = hashlib.sha256(original).hexdigest()[:8]

        flux_comp = io.BytesIO()
        compresser(io.BytesIO(original), flux_comp)
        taille_comp = flux_comp.tell()

        flux_comp.seek(0)
        flux_decomp = io.BytesIO()
        decompresser(flux_comp, flux_decomp)
        retour = flux_decomp.getvalue()

        sha_retour = hashlib.sha256(retour).hexdigest()[:8]
        ok   = "OK" if retour == original else "ERREUR"
        ratio = taille_comp / max(len(original), 1)

        apercu = repr(original[:20])[2:-1]
        print(f"  {apercu:>20}  {len(original):>7}  {taille_comp:>7}  "
              f"{ratio:>6.2f}  {ok} sha={sha_retour[:6]}")

    print("\n[OK] mybzip2 valide.")


if __name__ == "__main__":
    demo()
