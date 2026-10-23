import io
import os
import struct
import zlib

from formats.mylzma import compresser as _compresser_stream
from formats.mylzma import decompresser as _decompresser_stream


def compresser(donnees: bytes, taille_fenetre: int = 262144) -> bytes:
    """Enveloppe bytes -> bytes autour de compresser() base flux."""
    entree = io.BytesIO(donnees)
    sortie = io.BytesIO()
    _compresser_stream(entree, sortie, taille_fenetre=taille_fenetre)
    return sortie.getvalue()


def decompresser(donnees: bytes) -> bytes:
    """Enveloppe bytes -> bytes autour de decompresser() base flux."""
    entree = io.BytesIO(donnees)
    sortie = io.BytesIO()
    _decompresser_stream(entree, sortie)
    return sortie.getvalue()

# -- Constantes du format --
MAGIE = b'MY7Z'        # signature magique 4 octets
VERSION = 1            # version du format
ENTETE_GLOBAL = struct.Struct('>4sBi')    # magie(4) version(1) nb_fichiers(4) -> 9 B
ENTETE_FICHIER = struct.Struct('>QIq')    # taille_orig(8) crc32(4) offset(8) -> 20 B


def _verifier_chemin(nom: str) -> None:
    """Refuse les chemins dangereux (traversee de repertoire)."""
    if '..' in nom.replace('\\', '/').split('/'):
        raise ValueError(f"Chemin non autorise : {nom!r}")


# Ecriture d'une archive
def creer_archive(chemin_archive: str, fichiers: list[str],
                  niveau: int = 6, verbose: bool = False) -> None:
    """
    Cree une archive .m7z a partir d'une liste de chemins de fichiers.

    :param chemin_archive: chemin de l'archive de sortie
    :param fichiers: liste des fichiers a archiver
    :param niveau:   niveau de compression 1-9 (affecte la fenetre LZ77)
    :param verbose:  affiche les details de chaque fichier
    """
    if not fichiers:
        raise ValueError("Aucun fichier fourni.")

    # Correspondance niveau -> taille de fenetre (octets)
    fenetres = {1: 65536, 2: 65536, 3: 65536,
                4: 262144, 5: 262144, 6: 262144,
                7: 1048576, 8: 1048576, 9: 1048576}
    taille_fenetre = fenetres.get(max(1, min(9, niveau)), 262144)

    noms = [os.path.basename(f) for f in fichiers]
    donnees_comp = []   # liste de bytes compresses

    for chemin, nom in zip(fichiers, noms):
        with open(chemin, 'rb') as fh:
            donnees = fh.read()
        crc = zlib.crc32(donnees) & 0xFFFFFFFF
        comp = compresser(donnees, taille_fenetre=taille_fenetre)
        donnees_comp.append((nom, len(donnees), crc, comp))
        if verbose:
            ratio = len(comp) / max(1, len(donnees))
            print(f"  {nom}: {len(donnees)}B -> {len(comp)}B (ratio={ratio:.2f})")

    # Calcul des offsets : ils commencent apres l'en-tete global + toutes les
    # entetes de fichiers.  On calcule d'abord la taille totale des en-tetes.
    taille_entete_global = ENTETE_GLOBAL.size  # 9 B
    taille_entetes_fichiers = sum(
        2 + len(nom.encode('utf-8')) + ENTETE_FICHIER.size  # H(2) + nom + QIq(20)
        for nom, _, _, _ in donnees_comp
    )
    debut_donnees = taille_entete_global + taille_entetes_fichiers

    offsets = []
    curseur = debut_donnees
    for _, _, _, comp in donnees_comp:
        offsets.append(curseur)
        curseur += len(comp)

    with open(chemin_archive, 'wb') as arc:
        # En-tete global
        arc.write(ENTETE_GLOBAL.pack(MAGIE, VERSION, len(donnees_comp)))
        # En-tetes des fichiers
        for (nom, taille_orig, crc, comp), offset in zip(donnees_comp, offsets):
            nom_bytes = nom.encode('utf-8')
            arc.write(struct.pack('>H', len(nom_bytes)))
            arc.write(nom_bytes)
            arc.write(ENTETE_FICHIER.pack(taille_orig, crc, offset))
        # Donnees compressees
        for _, _, _, comp in donnees_comp:
            arc.write(comp)


# Lecture de l'en-tete d'une archive


def lire_entetes(arc: io.RawIOBase) -> list[dict]:
    """
    Lit et renvoie la liste des entrees de l'archive (sans decompresser).

    :param arc: fichier ouvert en mode binaire
    :return: liste de dicts {nom, taille_orig, crc32, offset, taille_comp}
    """
    raw = arc.read(ENTETE_GLOBAL.size)
    if len(raw) < ENTETE_GLOBAL.size:
        raise ValueError("Archive trop courte ou corrompue.")
    magie, version, nb_fichiers = ENTETE_GLOBAL.unpack(raw)
    if magie != MAGIE:
        raise ValueError(f"Mauvaise signature : {magie!r} (attendu {MAGIE!r})")
    if version != VERSION:
        raise ValueError(f"Version non supportee : {version}")

    entrees = []
    for _ in range(nb_fichiers):
        nom_len_raw = arc.read(2)
        nom_len = struct.unpack('>H', nom_len_raw)[0]
        nom = arc.read(nom_len).decode('utf-8')
        hdr = arc.read(ENTETE_FICHIER.size)
        taille_orig, crc, offset = ENTETE_FICHIER.unpack(hdr)
        entrees.append({'nom': nom, 'taille_orig': taille_orig,
                        'crc32': crc, 'offset': offset})

    # Calcul de la taille compressée de chaque entree
    for i, entree in enumerate(entrees):
        if i + 1 < len(entrees):
            entree['taille_comp'] = entrees[i + 1]['offset'] - entree['offset']
        else:
            arc.seek(0, 2)  # fin du fichier
            entree['taille_comp'] = arc.tell() - entree['offset']

    return entrees



# Commandes


def cmd_ajouter(archive: str, fichiers: list[str],
                niveau: int = 6, verbose: bool = False) -> None:
    """Commande 'a' : cree ou remplace l'archive avec les fichiers donnes."""
    creer_archive(archive, fichiers, niveau=niveau, verbose=verbose)
    print(f"Archive creee : {archive} ({len(fichiers)} fichier(s))")


def cmd_extraire(archive: str, dossier_sortie: str = '.',
                 verbose: bool = False) -> None:
    """Commande 'x' : extrait tous les fichiers de l'archive."""
    os.makedirs(dossier_sortie, exist_ok=True)
    with open(archive, 'rb') as arc:
        entrees = lire_entetes(arc)
        for entree in entrees:
            nom = entree['nom']
            _verifier_chemin(nom)
            arc.seek(entree['offset'])
            comp = arc.read(entree['taille_comp'])
            donnees = decompresser(comp)
            crc_calc = zlib.crc32(donnees) & 0xFFFFFFFF
            if crc_calc != entree['crc32']:
                raise ValueError(f"CRC32 invalide pour {nom!r}")
            chemin_sortie = os.path.join(dossier_sortie, nom)
            with open(chemin_sortie, 'wb') as fh:
                fh.write(donnees)
            if verbose:
                print(f"  Extrait : {chemin_sortie}")
    print(f"Extraction terminee dans {dossier_sortie!r}.")


def cmd_lister(archive: str) -> None:
    """Commande 'l' : liste le contenu de l'archive."""
    with open(archive, 'rb') as arc:
        entrees = lire_entetes(arc)
    print(f"{'Nom':<30} {'Orig':>10} {'Comp':>10} {'Ratio':>7}  CRC32")
    print('-' * 65)
    total_orig = total_comp = 0
    for e in entrees:
        ratio = e['taille_comp'] / max(1, e['taille_orig'])
        print(f"{e['nom']:<30} {e['taille_orig']:>10} {e['taille_comp']:>10}"
              f" {ratio:>7.2f}  {e['crc32']:08X}")
        total_orig += e['taille_orig']
        total_comp += e['taille_comp']
    print('-' * 65)
    ratio_total = total_comp / max(1, total_orig)
    print(f"{'TOTAL':<30} {total_orig:>10} {total_comp:>10} {ratio_total:>7.2f}")


def cmd_tester(archive: str, verbose: bool = False) -> bool:
    """
    Commande 't' : verifie l'integrite de chaque fichier (CRC32).

    :return: True si tout est valide, False sinon.
    """
    ok = True
    with open(archive, 'rb') as arc:
        entrees = lire_entetes(arc)
        for entree in entrees:
            arc.seek(entree['offset'])
            comp = arc.read(entree['taille_comp'])
            donnees = decompresser(comp)
            crc_calc = zlib.crc32(donnees) & 0xFFFFFFFF
            if crc_calc == entree['crc32']:
                statut = "OK"
            else:
                statut = "ERREUR (CRC invalide)"
                ok = False
            if verbose:
                print(f"  {entree['nom']}: {statut}")
    if ok:
        print("[OK] Archive integre.")
    else:
        print("[ERREUR] Archive corrompue.")
    return ok



# Demo / auto-test


def _demo() -> None:
    """Test aller-retour sur des donnees synthetiques en memoire."""
    import tempfile

    print("=== my7z - tests aller-retour ===\n")

    # Cree des fichiers temporaires
    fichiers_test = [
        ("fichier1.txt", b"Hello, monde! " * 200),
        ("fichier2.bin", bytes(range(256)) * 4),
        ("vide.dat",     b""),
        ("repetitif.txt", b"AAABBBCCC" * 150),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        chemins = []
        for nom, contenu in fichiers_test:
            chemin = os.path.join(tmpdir, nom)
            with open(chemin, 'wb') as fh:
                fh.write(contenu)
            chemins.append(chemin)

        archive = os.path.join(tmpdir, "test.m7z")
        creer_archive(archive, chemins)

        print(f"  Archive creee : {os.path.getsize(archive)} octets")
        print()

        # Lister
        with open(archive, 'rb') as arc:
            entrees = lire_entetes(arc)
        print(f"  {'Nom':<20} {'Orig':>8} {'Comp':>8}  CRC32")
        print("  " + "-" * 44)
        for e in entrees:
            print(f"  {e['nom']:<20} {e['taille_orig']:>8} {e['taille_comp']:>8}"
                  f"  {e['crc32']:08X}")

        print()

        # Extraire et verifier
        dossier_ext = os.path.join(tmpdir, "extrait")
        cmd_extraire(archive, dossier_ext)

        erreurs = 0
        for nom, contenu_orig in fichiers_test:
            chemin_ext = os.path.join(dossier_ext, nom)
            with open(chemin_ext, 'rb') as fh:
                contenu_ext = fh.read()
            if contenu_ext == contenu_orig:
                statut = "OK"
            else:
                statut = "ERREUR"
                erreurs += 1
            print(f"  {nom}: {statut}")

        print()
        if erreurs == 0:
            print("[OK] my7z valide.")
        else:
            print(f"[ERREUR] {erreurs} fichier(s) corrompus.")


if __name__ == '__main__':
    _demo()
