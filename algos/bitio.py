import io


class BitWriter:
    """
    Ecrit des bits un par un (ou par groupes) dans un flux d'octets.

    Fonctionnement :
    - On accumule les bits dans un entier 'tampon' de 8 bits.
    - Quand le tampon est plein, on ecrit l'octet dans le flux.
    - A la fermeture, on remplit les bits manquants avec des zeros.

    Exemple d'utilisation :
        flux = io.BytesIO()
        w = BitWriter(flux)
        w.ecrire_bit(1)
        w.ecrire_bits(0b101, 3)
        w.fermer()
        donnees = flux.getvalue()
    """

    def __init__(self, flux: io.RawIOBase):
        self.flux    = flux
        self.tampon  = 0    # bits en attente (8 bits max)
        self.nb_bits = 0    # combien de bits sont dans le tampon

    def ecrire_bit(self, bit: int):
        """
        Ecrit un seul bit (0 ou 1).

        #  mampiditra bit iray ao amin'ny tampon
        """
        self.tampon  = (self.tampon << 1) | (bit & 1)
        self.nb_bits += 1
        if self.nb_bits == 8:
            self._vider()

    def ecrire_bits(self, valeur: int, nb: int):
        """
        Ecrit 'nb' bits depuis 'valeur' (bit de poids fort en premier).

        Exemple : ecrire_bits(0b101, 3) ecrit les bits 1, 0, 1.

        #  mampiditra bits maromaro, bit lehibe aloha
        """
        for i in range(nb - 1, -1, -1):
            self.ecrire_bit((valeur >> i) & 1)

    def ecrire_octet(self, octet: int):
        """
        Raccourci pour ecrire 8 bits d'un coup.

        #  manoratra byte iray
        """
        self.ecrire_bits(octet, 8)

    def fermer(self):
        """
        Vide le tampon en ajoutant des zeros de rembourrage si necessaire.
        Doit etre appele avant de lire le flux.

        #  manafina ny tampon amin'ny alalan'ny zeros
        """
        if self.nb_bits > 0:
            # Decaler pour que les bits soient dans les poids forts
            self.tampon <<= (8 - self.nb_bits)
            self._vider()

    def _vider(self):
        """Ecrit l'octet courant dans le flux et remet le tampon a zero."""
        self.flux.write(bytes([self.tampon]))
        self.tampon  = 0
        self.nb_bits = 0

    @property
    def bits_ecrits(self) -> int:
        """Nombre total de bits ecrits (y compris ceux en attente)."""
        return self.flux.tell() * 8 + self.nb_bits


class BitReader:
    """
    Lit des bits un par un (ou par groupes) depuis un flux d'octets.

    Fonctionnement :
    - On charge un octet a la fois dans un tampon.
    - On extrait les bits du poids fort vers le poids faible.
    - Quand le tampon est vide, on charge l'octet suivant.

    Exemple d'utilisation :
        r = BitReader(flux)
        bit = r.lire_bit()
        valeur = r.lire_bits(5)
    """

    def __init__(self, flux: io.RawIOBase):
        self.flux    = flux
        self.tampon  = 0    # octet courant
        self.nb_bits = 0    # bits restants dans le tampon

    def lire_bit(self) -> int:
        """
        Lit et retourne le prochain bit (0 ou 1).
        Leve EOFError si le flux est epuise.

        #  mamaky bit iray avy amin'ny tampon
        """
        if self.nb_bits == 0:
            octet = self.flux.read(1)
            if not octet:
                raise EOFError("Fin du flux de bits")
            self.tampon  = octet[0]
            self.nb_bits = 8

        self.nb_bits -= 1
        return (self.tampon >> self.nb_bits) & 1

    def lire_bits(self, nb: int) -> int:
        """
        Lit 'nb' bits et retourne leur valeur entiere (bit de poids fort en premier).

        Exemple : si les prochains bits sont 1,0,1 alors lire_bits(3) retourne 5.

        #  mamaky bits maromaro, manangona azy ireo ho integer
        """
        valeur = 0
        for _ in range(nb):
            valeur = (valeur << 1) | self.lire_bit()
        return valeur

    def lire_octet(self) -> int:
        """
        Raccourci pour lire 8 bits d'un coup.

        #  mamaky byte iray
        """
        return self.lire_bits(8)

    def essayer_lire_bit(self) -> int | None:
        """
        Comme lire_bit() mais retourne None en fin de flux (sans lever d'exception).
        Utile pour tester la fin d'un flux sans try/except.

        #  mamerina None raha tapitra ny flux
        """
        try:
            return self.lire_bit()
        except EOFError:
            return None


# ---------------------------------------------------------------------------
# Demonstration et test rapide
# ---------------------------------------------------------------------------

def demo():
    """
    Verifie que BitWriter et BitReader sont coherents entre eux.
    Ecrit une sequence de bits, la relit et compare.
    """
    # Sequence de bits a tester
    bits_originaux = [1, 0, 1, 1, 0, 0, 0, 1,   # 0xB1
                      1, 1, 1, 0, 0, 1, 0, 1,   # 0xE5
                      1]                          # 1 bit de rembourrage

    flux = io.BytesIO()
    w = BitWriter(flux)
    for b in bits_originaux:
        w.ecrire_bit(b)
    w.fermer()

    donnees = flux.getvalue()
    print(f"Octets ecrits   : {donnees.hex(' ')}")
    print(f"Bits originaux  : {bits_originaux}")

    # Relecture
    flux.seek(0)
    r = BitReader(flux)
    bits_lus = []
    for _ in range(len(bits_originaux)):
        bits_lus.append(r.lire_bit())

    print(f"Bits lus        : {bits_lus}")
    assert bits_lus == bits_originaux, "ERREUR : les bits lus different des bits ecrits"
    print("[OK] BitWriter/BitReader coherents.")

    # Test ecrire_bits / lire_bits
    flux2 = io.BytesIO()
    w2 = BitWriter(flux2)
    w2.ecrire_bits(0b10110, 5)   # 5 bits
    w2.ecrire_bits(0b111,   3)   # 3 bits -> total 8 bits = 1 octet
    w2.fermer()

    flux2.seek(0)
    r2 = BitReader(flux2)
    val1 = r2.lire_bits(5)
    val2 = r2.lire_bits(3)
    assert val1 == 0b10110, f"Attendu 22, obtenu {val1}"
    assert val2 == 0b111,   f"Attendu 7, obtenu {val2}"
    print("[OK] ecrire_bits / lire_bits coherents.")


if __name__ == "__main__":
    demo()
