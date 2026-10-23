# Projet de Compression — Clone bzip2, lzma, 7-zip

réalisation d'un clone fonctionnel de **bzip2**, **lzma** et **7-zip** en Python pur (sans bibliothèques externes).



## 1. À quoi sert le projet ?

Ce projet permet de **compresser** (réduire la taille) et **décompresser** (retrouver le fichier d'origine à l'identique) 4 types de fichiers :
-  **Texte** (`.txt`)
-  **Audio** (`.wav`)
-  **Image** (`.bmp`)
-  **Vidéo** (`.mp4`)

Avec 3 formats différents :
- **mybzip2** (`.mbz2`) : RLE + BWT + MTF + Huffman
- **mylzma** (`.mlzma`) : LZ77 + Range Coder
- **my7z** (`.m7z`) : Archive multi-fichiers basée sur LZ77

---

## 2. Structure du projet

```text
compression-clone/
├── algos/               # Le "moteur" : algorithmes purs (Huffman, LZ77, BWT...)
├── formats/             # Les 3 formats de fichiers (mybzip2, mylzma, my7z)
├── fichiers_test/       # Les 4 fichiers d'essai (texte, audio, image, vidéo)
│
├── comprimes/           # Les fichiers compressés
│   ├── bzip2/           # Sorties .mbz2
│   ├── lzma/            # Sorties .mlzma
│   └── 7z/              # Sorties .m7z
│
├── decomprimes/         # Les fichiers restaurés à l'identique
│   ├── bzip2/           # Fichiers extraits depuis bzip2
│   ├── lzma/            # Fichiers extraits depuis lzma
│   └── 7z/              # Fichiers extraits depuis 7z
│
├── demo.py              # Le bouton magique : teste tout en 1 commande
├── main.py              # La commande manuelle pour vos propres fichiers
└── README.md            # Ce guide
```

## 5. Comment lancer ?

### A. Lancer la démonstration automatique 
Ouvrez le terminal dans le dossier du projet et tapez :
```powershell
python -m demo
```
*Tous les fichiers compressés iront dans `comprimes/` et les fichiers restaurés dans `decomprimes/` classés par format.*

### B. Utiliser la commande manuelle (`main.py`)

#### Format mybzip2 (.mbz2)
```powershell
# Compresser :
python -m main bzip2 compress "teste.txt" "teste.mbz2"

# Décompresser :
python -m main bzip2 decompress "teste.mbz2" "fichier_restaure.txt"
```

#### Format mylzma (.mlzma)
```powershell
# Compresser :
python -m main lzma compress "teste.txt" "teste.mlzma"

# Décompresser :
python -m main lzma decompress "teste.mlzma" "fichier_restaure.txt"
```

#### Format my7z (.m7z)
```powershell
# Créer une archive (avec 'a') :
python -m main 7z a "archive.m7z" "fichier1.txt" "fichier2.bmp"

# Lister le contenu (avec 'l') :
python -m main 7z l "archive.m7z"

# Extraire l'archive (avec 'x') :
python -m main 7z x "archive.m7z" --dossier "./dossier_sortie"
```

---

## 6. Résultats d'efficacité obtenus

Résultats obtenus lors de la démonstration :

| **texte.txt** | 200 Ko | 1.4 Ko (99.3%) | **0.3 Ko (99.8%)** | 0.4 Ko (99.8%) |
| **audio.wav** | 400 Ko | 30.9 Ko (92.3%) | **4.6 Ko (98.8%)** | 4.7 Ko (98.8%)|
| **image.bmp** | 600 Ko | 7.5 Ko (98.7%) | **4.2 Ko (99.3%)** | 4.2 Ko (99.3%) |
| **video.mp4** | 800 Ko | 3.4 Ko (99.6%) | **1.3 Ko (99.8%)** | 1.3 Ko (99.8%) |

