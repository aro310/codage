import argparse
import io
import os
import sys
import time

# Correspondances niveau -> parametres

# Taille de fenetre LZ77 selon le niveau (1-9)
FENETRES_LZMA = {
    1: 65536,   2: 65536,   3: 65536,
    4: 262144,  5: 262144,  6: 262144,
    7: 1048576, 8: 1048576, 9: 1048576,
}

# Taille de bloc BWT selon le niveau (en octets)
BLOCS_BZIP2 = {
    1: 50_000,  2: 50_000,  3: 50_000,
    4: 100_000, 5: 100_000, 6: 100_000,
    7: 200_000, 8: 200_000, 9: 200_000,
}


# Helpers


def _taille_lisible(n: int) -> str:
    """Convertit un nombre d'octets en chaine lisible (KB / MB)."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def _afficher_stats(taille_orig: int, taille_comp: int,
                    duree: float, action: str) -> None:
    """Affiche un resume de l'operation de compression/decompression."""
    ratio = taille_comp / max(1, taille_orig)
    print(f"  {action}")
    print(f"  Entree  : {_taille_lisible(taille_orig)}")
    print(f"  Sortie  : {_taille_lisible(taille_comp)}")
    if action == "Compression":
        print(f"  Ratio   : {ratio:.3f} ({(1-ratio)*100:.1f}% economise)")
    print(f"  Duree   : {duree:.3f} s")


# Sous-commandes bzip2

def cmd_bzip2_compress(args: argparse.Namespace) -> int:
    """Compresse un fichier au format .mbz2."""
    from formats.mybzip2 import compresser

    taille_bloc = BLOCS_BZIP2.get(args.niveau, 100_000)
    if args.verbose:
        print(f"[bzip2] Compression  niveau={args.niveau}"
              f"  bloc={_taille_lisible(taille_bloc)}")

    t0 = time.perf_counter()
    with open(args.entree, 'rb') as fin, open(args.sortie, 'wb') as fout:
        entree = io.BytesIO(fin.read())
        sortie = io.BytesIO()
        compresser(entree, sortie, taille_bloc=taille_bloc, verbose=args.verbose)
        fout.write(sortie.getvalue())
    duree = time.perf_counter() - t0

    if args.verbose:
        _afficher_stats(os.path.getsize(args.entree),
                        os.path.getsize(args.sortie), duree, "Compression")
    print(f"[OK] {args.entree} -> {args.sortie}")
    return 0


def cmd_bzip2_decompress(args: argparse.Namespace) -> int:
    """Decompresse un fichier .mbz2."""
    from formats.mybzip2 import decompresser

    if args.verbose:
        print(f"[bzip2] Decompression  fichier={args.entree!r}")

    t0 = time.perf_counter()
    with open(args.entree, 'rb') as fin, open(args.sortie, 'wb') as fout:
        entree = io.BytesIO(fin.read())
        sortie = io.BytesIO()
        decompresser(entree, sortie, verbose=args.verbose)
        fout.write(sortie.getvalue())
    duree = time.perf_counter() - t0

    if args.verbose:
        _afficher_stats(os.path.getsize(args.entree),
                        os.path.getsize(args.sortie), duree, "Decompression")
    print(f"[OK] {args.entree} -> {args.sortie}")
    return 0


# Sous-commandes lzma

def cmd_lzma_compress(args: argparse.Namespace) -> int:
    """Compresse un fichier au format .mlzma."""
    from formats.mylzma import compresser

    taille_fenetre = FENETRES_LZMA.get(args.niveau, 262144)
    lazy = args.niveau >= 5
    if args.verbose:
        print(f"[lzma] Compression  niveau={args.niveau}"
              f"  fenetre={_taille_lisible(taille_fenetre)}"
              f"  lazy={lazy}")

    t0 = time.perf_counter()
    with open(args.entree, 'rb') as fin, open(args.sortie, 'wb') as fout:
        compresser(fin, fout, taille_fenetre=taille_fenetre,
                   lazy=lazy, verbose=args.verbose)
    duree = time.perf_counter() - t0

    if args.verbose:
        _afficher_stats(os.path.getsize(args.entree),
                        os.path.getsize(args.sortie), duree, "Compression")
    print(f"[OK] {args.entree} -> {args.sortie}")
    return 0


def cmd_lzma_decompress(args: argparse.Namespace) -> int:
    """Decompresse un fichier .mlzma."""
    from formats.mylzma import decompresser

    if args.verbose:
        print(f"[lzma] Decompression  fichier={args.entree!r}")

    t0 = time.perf_counter()
    with open(args.entree, 'rb') as fin, open(args.sortie, 'wb') as fout:
        decompresser(fin, fout, verbose=args.verbose)
    duree = time.perf_counter() - t0

    if args.verbose:
        _afficher_stats(os.path.getsize(args.entree),
                        os.path.getsize(args.sortie), duree, "Decompression")
    print(f"[OK] {args.entree} -> {args.sortie}")
    return 0


# Sous-commandes 7z

def cmd_7z_ajouter(args: argparse.Namespace) -> int:
    """Commande '7z a' : cree une archive .m7z."""
    from formats.my7z import cmd_ajouter

    if not args.fichiers:
        print("[ERREUR] Aucun fichier specifie.", file=sys.stderr)
        return 1
    for f in args.fichiers:
        if not os.path.isfile(f):
            print(f"[ERREUR] Fichier introuvable : {f!r}", file=sys.stderr)
            return 1

    cmd_ajouter(args.archive, args.fichiers,
                niveau=args.niveau, verbose=args.verbose)
    if args.verbose:
        print(f"  Taille archive : {_taille_lisible(os.path.getsize(args.archive))}")
    return 0


def cmd_7z_extraire(args: argparse.Namespace) -> int:
    """Commande '7z x' : extrait une archive .m7z."""
    from formats.my7z import cmd_extraire

    dossier = getattr(args, 'dossier', '.') or '.'
    cmd_extraire(args.archive, dossier, verbose=args.verbose)
    return 0


def cmd_7z_lister(args: argparse.Namespace) -> int:
    """Commande '7z l' : liste le contenu d'une archive .m7z."""
    from formats.my7z import cmd_lister

    cmd_lister(args.archive)
    return 0


def cmd_7z_tester(args: argparse.Namespace) -> int:
    """Commande '7z t' : teste l'integrite d'une archive .m7z."""
    from formats.my7z import cmd_tester

    ok = cmd_tester(args.archive, verbose=args.verbose)
    return 0 if ok else 1


# Construction du parseur

def _construire_parseur() -> argparse.ArgumentParser:
    """Construit et renvoie le parseur argparse complet."""
    parser = argparse.ArgumentParser(
        prog='main',
        description='Outils de compression maison (mybzip2 / mylzma / my7z)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python -m main bzip2 compress   fichier.txt  fichier.mbz2\n"
            "  python -m main bzip2 decompress fichier.mbz2 fichier.txt\n"
            "  python -m main lzma  compress   fichier.txt  fichier.mlzma\n"
            "  python -m main lzma  decompress fichier.mlzma fichier.txt\n"
            "  python -m main 7z a archive.m7z f1.txt f2.bin\n"
            "  python -m main 7z x archive.m7z --dossier ./sortie\n"
            "  python -m main 7z l archive.m7z\n"
            "  python -m main 7z t archive.m7z\n"
            "\nNote : les formats .mbz2 / .mlzma / .m7z ne sont PAS compatibles\n"
            "       avec bzip2, lzma ou 7-zip officiels."
        ),
    )

    sous_cmds = parser.add_subparsers(dest='format', metavar='FORMAT',
                                      help='Format de compression')
    sous_cmds.required = True

    # -- Options communes reutilisables --
    def _options_communes(p: argparse.ArgumentParser) -> None:
        p.add_argument('--niveau', type=int, default=6, metavar='N',
                       choices=range(1, 10),
                       help='Niveau de compression 1-9 (defaut: 6)')
        p.add_argument('--verbose', action='store_true',
                       help='Affichage detaille')

    # ---- bzip2 ----
    p_bz2 = sous_cmds.add_parser('bzip2', help='Format mybzip2 (.mbz2)')
    op_bz2 = p_bz2.add_subparsers(dest='operation', metavar='OPERATION')
    op_bz2.required = True

    p_bz2_c = op_bz2.add_parser('compress', help='Compresser un fichier')
    p_bz2_c.add_argument('entree', help='Fichier source')
    p_bz2_c.add_argument('sortie', help='Fichier de sortie (.mbz2)')
    _options_communes(p_bz2_c)
    p_bz2_c.set_defaults(func=cmd_bzip2_compress)

    p_bz2_d = op_bz2.add_parser('decompress', help='Decompresser un fichier')
    p_bz2_d.add_argument('entree', help='Fichier source (.mbz2)')
    p_bz2_d.add_argument('sortie', help='Fichier de sortie')
    _options_communes(p_bz2_d)
    p_bz2_d.set_defaults(func=cmd_bzip2_decompress)

    # ---- lzma ----
    p_lz = sous_cmds.add_parser('lzma', help='Format mylzma (.mlzma)')
    op_lz = p_lz.add_subparsers(dest='operation', metavar='OPERATION')
    op_lz.required = True

    p_lz_c = op_lz.add_parser('compress', help='Compresser un fichier')
    p_lz_c.add_argument('entree', help='Fichier source')
    p_lz_c.add_argument('sortie', help='Fichier de sortie (.mlzma)')
    _options_communes(p_lz_c)
    p_lz_c.set_defaults(func=cmd_lzma_compress)

    p_lz_d = op_lz.add_parser('decompress', help='Decompresser un fichier')
    p_lz_d.add_argument('entree', help='Fichier source (.mlzma)')
    p_lz_d.add_argument('sortie', help='Fichier de sortie')
    _options_communes(p_lz_d)
    p_lz_d.set_defaults(func=cmd_lzma_decompress)

    # ---- 7z ----
    p_7z = sous_cmds.add_parser('7z', help='Archive multi-fichiers my7z (.m7z)')
    op_7z = p_7z.add_subparsers(dest='operation', metavar='OPERATION')
    op_7z.required = True

    p_7z_a = op_7z.add_parser('a', help='Ajouter des fichiers a une archive')
    p_7z_a.add_argument('archive', help='Archive de sortie (.m7z)')
    p_7z_a.add_argument('fichiers', nargs='+', help='Fichiers a archiver')
    _options_communes(p_7z_a)
    p_7z_a.set_defaults(func=cmd_7z_ajouter)

    p_7z_x = op_7z.add_parser('x', help='Extraire tous les fichiers')
    p_7z_x.add_argument('archive', help='Archive source (.m7z)')
    p_7z_x.add_argument('--dossier', default='.', metavar='DEST',
                         help='Dossier de destination (defaut: .)')
    _options_communes(p_7z_x)
    p_7z_x.set_defaults(func=cmd_7z_extraire)

    p_7z_l = op_7z.add_parser('l', help='Lister le contenu de l\'archive')
    p_7z_l.add_argument('archive', help='Archive source (.m7z)')
    _options_communes(p_7z_l)
    p_7z_l.set_defaults(func=cmd_7z_lister)

    p_7z_t = op_7z.add_parser('t', help='Tester l\'integrite de l\'archive')
    p_7z_t.add_argument('archive', help='Archive source (.m7z)')
    _options_communes(p_7z_t)
    p_7z_t.set_defaults(func=cmd_7z_tester)

    return parser


# Point d'entree

def main(argv: list[str] | None = None) -> int:
    """Point d'entree principal — parse les arguments et dispatche la commande."""
    parser = _construire_parseur()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"[ERREUR] Fichier introuvable : {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n[ANNULE]", file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
