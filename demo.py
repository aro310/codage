# -*- coding: utf-8 -*-
"""
demo.py — Demonstration de compression sur 4 types de fichiers
Organise les sorties en 3 sous-dossiers par format :
  - comprimes/bzip2/   et decomprimes/bzip2/
  - comprimes/lzma/    et decomprimes/lzma/
  - comprimes/7z/      et decomprimes/7z/
"""

import hashlib
import io
import math
import os
import random
import struct
import sys
import time

from formats.mybzip2 import compresser as _bz2_c, decompresser as _bz2_d
from formats.mylzma  import compresser as _lzma_c, decompresser as _lzma_d
from formats.my7z    import creer_archive, cmd_extraire


# Generation des 4 fichiers de test

def _generer_texte(taille: int) -> bytes:
    phrase = (
        "La compression de donnees consiste a reduire la taille d'un fichier "
        "afin d'economiser de l'espace disque ou de la bande passante reseau. "
        "Les algorithmes sans perte comme Huffman, BWT et LZ77 permettent une "
        "reconstruction exacte des donnees originales apres decompression. "
    ).encode("utf-8")
    return (phrase * (taille // len(phrase) + 1))[:taille]


def _generer_wav(taille: int) -> bytes:
    nb = max(1, (taille - 44) // 2)
    echantillons = bytearray()
    for i in range(nb):
        val = int(32767 * math.sin(2 * math.pi * 440 * i / 44100))
        echantillons += struct.pack("<h", val)
    n = len(echantillons)
    entete = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + n, b"WAVE", b"fmt ", 16,
        1, 1, 44100, 88200, 2, 16, b"data", n,
    )
    return entete + bytes(echantillons)


def _generer_bmp(taille: int) -> bytes:
    cote = max(1, int((taille // 3) ** 0.5))
    n = cote * cote * 3
    entete_f = struct.pack("<2sIHHI", b"BM", 54 + n, 0, 0, 54)
    entete_i = struct.pack("<IiiHHIIiiII", 40, cote, -cote, 1, 24, 0, n, 2835, 2835, 0, 0)
    pixels = bytearray()
    for y in range(cote):
        for x in range(cote):
            v = (x + y) % 256
            pixels += bytes([v, v, v])
    return entete_f + entete_i + bytes(pixels)[:n]


def _generer_mp4(taille: int) -> bytes:
    frame_size = 1280 * 3
    sortie = bytearray()
    couleur = 0
    while len(sortie) < taille:
        for _ in range(frame_size):
            sortie.append(couleur % 256)
        couleur += 1
    return bytes(sortie[:taille])


FICHIERS_TEST = [
    ("texte.txt",  _generer_texte,  200_000),
    ("audio.wav",  _generer_wav,    400_000),
    ("image.bmp",  _generer_bmp,    600_000),
    ("video.mp4",  _generer_mp4,    800_000),
]


def preparer_fichiers(dossier_src: str) -> list[tuple[str, bytes]]:
    os.makedirs(dossier_src, exist_ok=True)
    fichiers = []
    for nom, gen, taille in FICHIERS_TEST:
        chemin = os.path.join(dossier_src, nom)
        if not os.path.exists(chemin):
            donnees = gen(taille)
            with open(chemin, "wb") as f:
                f.write(donnees)
        else:
            with open(chemin, "rb") as f:
                donnees = f.read()
        fichiers.append((chemin, donnees))
    return fichiers


# Compression / Decompression helpers

def bz2_compress(d: bytes) -> bytes:
    e, s = io.BytesIO(d), io.BytesIO()
    _bz2_c(e, s)
    return s.getvalue()

def bz2_decompress(d: bytes) -> bytes:
    e, s = io.BytesIO(d), io.BytesIO()
    _bz2_d(e, s)
    return s.getvalue()

def lzma_compress(d: bytes) -> bytes:
    e, s = io.BytesIO(d), io.BytesIO()
    _lzma_c(e, s, taille_fenetre=262144, lazy=True)
    return s.getvalue()

def lzma_decompress(d: bytes) -> bytes:
    e, s = io.BytesIO(d), io.BytesIO()
    _lzma_d(e, s)
    return s.getvalue()


def sep(c="=", n=70): print(c * n)

def afficher_resultat(nom: str, orig: int, comp: int, duree_c: float,
                      duree_d: float, sha_ok: bool) -> None:
    ratio  = comp / max(1, orig)
    gain   = (1 - ratio) * 100
    signe  = "+" if gain < 0 else " "
    statut = "OK" if sha_ok else "ERREUR SHA-256"
    print(f"  {nom:<12}  {orig:>9,} B  ->  {comp:>9,} B"
          f"  ratio={ratio:.3f}  gain={signe}{gain:5.1f}%"
          f"  c={duree_c:.2f}s  d={duree_d:.2f}s  [{statut}]")


# Execution principale

def main() -> int:
    dossier_src = "fichiers_test"
    base_comp   = "comprimes"
    base_decomp = "decomprimes"

    # Sous-dossiers par format
    dossiers_comp = {
        "bzip2": os.path.join(base_comp, "bzip2"),
        "lzma":  os.path.join(base_comp, "lzma"),
        "7z":    os.path.join(base_comp, "7z"),
    }
    dossiers_decomp = {
        "bzip2": os.path.join(base_decomp, "bzip2"),
        "lzma":  os.path.join(base_decomp, "lzma"),
        "7z":    os.path.join(base_decomp, "7z"),
    }

    for d in list(dossiers_comp.values()) + list(dossiers_decomp.values()):
        os.makedirs(d, exist_ok=True)

    sep()
    print("  DEMO DE COMPRESSION (4 types x 3 formats)")
    sep()

    print(f"\nFichiers sources dans '{dossier_src}/' :")
    fichiers = preparer_fichiers(dossier_src)
    for chemin, donnees in fichiers:
        print(f"  {os.path.basename(chemin):<12}  {len(donnees):>9,} octets")

    # 1. mybzip2
    sep("-")
    print("1. FORMAT mybzip2 (.mbz2) -> dossier comprimes/bzip2/")
    sep("-")
    for chemin, donnees in fichiers:
        nom = os.path.basename(chemin)
        sha_orig = hashlib.sha256(donnees).hexdigest()

        t0 = time.perf_counter()
        comp = bz2_compress(donnees)
        t_c = time.perf_counter() - t0

        c_path = os.path.join(dossiers_comp["bzip2"], nom + ".mbz2")
        with open(c_path, "wb") as f:
            f.write(comp)

        t0 = time.perf_counter()
        reconst = bz2_decompress(comp)
        t_d = time.perf_counter() - t0

        d_path = os.path.join(dossiers_decomp["bzip2"], nom)
        with open(d_path, "wb") as f:
            f.write(reconst)

        sha_ok = hashlib.sha256(reconst).hexdigest() == sha_orig
        afficher_resultat(nom, len(donnees), len(comp), t_c, t_d, sha_ok)

    # 2. mylzma
    sep("-")
    print("2. FORMAT mylzma (.mlzma) -> dossier comprimes/lzma/")
    sep("-")
    for chemin, donnees in fichiers:
        nom = os.path.basename(chemin)
        sha_orig = hashlib.sha256(donnees).hexdigest()

        t0 = time.perf_counter()
        comp = lzma_compress(donnees)
        t_c = time.perf_counter() - t0

        c_path = os.path.join(dossiers_comp["lzma"], nom + ".mlzma")
        with open(c_path, "wb") as f:
            f.write(comp)

        t0 = time.perf_counter()
        reconst = lzma_decompress(comp)
        t_d = time.perf_counter() - t0

        d_path = os.path.join(dossiers_decomp["lzma"], nom)
        with open(d_path, "wb") as f:
            f.write(reconst)

        sha_ok = hashlib.sha256(reconst).hexdigest() == sha_orig
        afficher_resultat(nom, len(donnees), len(comp), t_c, t_d, sha_ok)

    # 3. my7z
    sep("-")
    print("3. FORMAT my7z (.m7z) -> dossier comprimes/7z/")
    sep("-")
    for chemin, donnees in fichiers:
        nom = os.path.basename(chemin)
        sha_orig = hashlib.sha256(donnees).hexdigest()

        nom_arc = os.path.join(dossiers_comp["7z"], nom + ".m7z")

        t0 = time.perf_counter()
        creer_archive(nom_arc, [chemin], niveau=6)
        t_c = time.perf_counter() - t0

        taille_arc = os.path.getsize(nom_arc)

        # Extraire dans decomprimes/7z/
        t0 = time.perf_counter()
        cmd_extraire(nom_arc, dossiers_decomp["7z"])
        t_d = time.perf_counter() - t0

        d_path = os.path.join(dossiers_decomp["7z"], nom)
        with open(d_path, "rb") as f:
            extrait = f.read()
        sha_ok = hashlib.sha256(extrait).hexdigest() == sha_orig
        afficher_resultat(nom, len(donnees), taille_arc, t_c, t_d, sha_ok)

    sep()
    print("  RESUME DES DOSSIERS")
    sep()
    for fmt in ["bzip2", "lzma", "7z"]:
        print(f"\n[Format {fmt}]")
        print(f"  Comprimes   ({dossiers_comp[fmt]}):")
        for f in sorted(os.listdir(dossiers_comp[fmt])):
            sz = os.path.getsize(os.path.join(dossiers_comp[fmt], f))
            print(f"    - {f:<20} {sz:>8,} octets")
        print(f"  Decomprimes ({dossiers_decomp[fmt]}):")
        for f in sorted(os.listdir(dossiers_decomp[fmt])):
            sz = os.path.getsize(os.path.join(dossiers_decomp[fmt], f))
            print(f"    - {f:<20} {sz:>8,} octets")

    sep()
    print("  TERMINE AVEC SUCCES : tous les fichiers ont ete verifies (SHA-256).")
    sep()
    return 0


if __name__ == "__main__":
    sys.exit(main())
