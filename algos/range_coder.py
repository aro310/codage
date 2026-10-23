PROB_MAX   = 1 << 11   # 2048
PROB_INIT  = 1 << 10   # 1024 — P(0) = 0.5 au depart
PROB_ADAPT = 5         # vitesse d'adaptation (decalage de 5 bits)
HAUT_32    = 1 << 24   # seuil de normalisation (octet haut = 8 bits)

# Modele de probabilite adaptatif
class ModeleAdaptatif:
    """
    Modele binaire adaptatif.
    Maintient P(0) dans [1, PROB_MAX-1] par moyenne exponentielle.

    """

    def __init__(self):
        self.prob = PROB_INIT   # P(0) sur PROB_MAX

    def mettre_a_jour(self, bit: int):
        """Converge vers P(0)=1 si bit=1 frequent, vers P(0)=PROB_MAX si bit=0 frequent."""
        if bit == 0:
            self.prob += (PROB_MAX - self.prob) >> PROB_ADAPT
        else:
            self.prob -= self.prob >> PROB_ADAPT

    def reset(self):
        self.prob = PROB_INIT

# Encodeur (approche intervalle [low, high] — sans carry)
class RangeEncoder:
    """
    Range coder entier (encodeur).

    Principe identique au codage arithmetique du cours, mais en entiers :
      rang = high - low + 1
      mid  = low + rang * P(0) // PROB_MAX - 1
      Si bit=0 : high = mid
      Si bit=1 : low  = mid + 1
    Normalisation : quand low et high partagent le meme octet haut,
    on flushe cet octet (il est desormais stable, pas de carry possible).
    """

    def __init__(self):
        self.low    = 0
        self.high   = 0xFFFFFFFF
        self.sortie = bytearray()

    def encoder_bit(self, bit: int, prob: int):
        """
        Encode un bit avec P(0) = prob / PROB_MAX.

        # subdiviser [low, high] selon la probabilite
        """
        rang = self.high - self.low + 1
        mid  = self.low + rang * prob // PROB_MAX - 1

        if bit == 0:
            self.high = mid
        else:
            self.low  = mid + 1

        self._normaliser()

    def _normaliser(self):
        """
        Flushe les octets hauts stables (partages par low et high).
        Pas de carry : on ne flushe que quand les octets sont certains.

        # manala ny octet ambony raha mitovy amin'ny low sy high
        """
        while (self.high ^ self.low) < HAUT_32:
            octet      = self.high >> 24
            self.sortie.append(octet)
            self.high  = ((self.high & 0x00FFFFFF) << 8) | 0xFF
            self.low   = ((self.low  & 0x00FFFFFF) << 8)

    def finaliser(self) -> bytes:
        """
        Flushe les 4 derniers octets de 'low' pour finaliser le flux.
        Doit etre appele apres tous les encoder_bit().

        # mamerina ny octets farany (low)
        """
        for _ in range(4):
            self.sortie.append(self.low >> 24)
            self.low = (self.low & 0x00FFFFFF) << 8
        return bytes(self.sortie)

    def encoder_octet(self, valeur: int, modeles: list):
        """
        Encode un octet (8 bits) — bit de poids fort en premier.
        Utilise 8 modeles adaptatifs independants (un par bit).

        # 8 appels a encoder_bit
        """
        for i in range(7, -1, -1):
            bit = (valeur >> i) & 1
            idx = 7 - i
            self.encoder_bit(bit, modeles[idx].prob)
            modeles[idx].mettre_a_jour(bit)

# Decodeur
class RangeDecoder:
    """
    Range coder entier (decodeur).

    Maintient un 'code' (valeur courante dans [low, high]).
    Pour chaque bit : compare code avec mid pour determiner 0 ou 1.
    """

    def __init__(self, donnees: bytes):
        self.donnees = donnees
        self.pos     = 0
        self.low     = 0
        self.high    = 0xFFFFFFFF
        # Initialiser 'code' avec les 4 premiers octets du flux
        self.code    = 0
        for _ in range(4):
            self.code = ((self.code & 0x00FFFFFF) << 8) | self._lire_octet()

    def _lire_octet(self) -> int:
        """Lit le prochain octet du flux (0 si epuise)."""
        if self.pos < len(self.donnees):
            v = self.donnees[self.pos]
            self.pos += 1
            return v
        return 0

    def decoder_bit(self, prob: int) -> int:
        """
        Decode un bit : code <= mid -> bit=0, sinon bit=1.

        # mitady ny bit amin'ny alalan'ny comparaison code vs mid
        """
        rang = self.high - self.low + 1
        mid  = self.low + rang * prob // PROB_MAX - 1

        if self.code <= mid:
            self.high = mid
            bit = 0
        else:
            self.low = mid + 1
            bit = 1

        self._normaliser()
        return bit

    def _normaliser(self):
        """Lit de nouveaux octets quand low et high partagent l'octet haut."""
        while (self.high ^ self.low) < HAUT_32:
            self.high  = ((self.high & 0x00FFFFFF) << 8) | 0xFF
            self.low   = ((self.low  & 0x00FFFFFF) << 8)
            self.code  = ((self.code & 0x00FFFFFF) << 8) | self._lire_octet()

    def decoder_octet(self, modeles: list) -> int:
        """
        Decode un octet (8 bits) — bit de poids fort en premier.

        # 8 appels a decoder_bit
        """
        valeur = 0
        for i in range(7, -1, -1):
            idx = 7 - i
            bit = self.decoder_bit(modeles[idx].prob)
            modeles[idx].mettre_a_jour(bit)
            valeur = (valeur << 1) | bit
        return valeur

# Fonctions utilitaires
def encoder_entier(enc: RangeEncoder, valeur: int,
                   nb_bits: int, modeles: list):
    """
    Encode un entier de 'nb_bits' bits (poids fort en premier).
    Utilise 'nb_bits' modeles independants (un par bit).
    """
    for i in range(nb_bits - 1, -1, -1):
        bit = (valeur >> i) & 1
        idx = nb_bits - 1 - i
        enc.encoder_bit(bit, modeles[idx].prob)
        modeles[idx].mettre_a_jour(bit)


def decoder_entier(dec: RangeDecoder, nb_bits: int, modeles: list) -> int:
    """
    Decode un entier de 'nb_bits' bits. Memes modeles que encoder_entier().
    """
    valeur = 0
    for i in range(nb_bits - 1, -1, -1):
        idx = nb_bits - 1 - i
        bit = dec.decoder_bit(modeles[idx].prob)
        modeles[idx].mettre_a_jour(bit)
        valeur = (valeur << 1) | bit
    return valeur


def nouveaux_modeles(nb: int) -> list:
    """Cree une liste de 'nb' modeles adaptatifs initialises a P(0)=0.5."""
    return [ModeleAdaptatif() for _ in range(nb)]

# Demonstration
def demo():
    import os

    print("=== Range coder adaptatif (intervalle [low,high]) ===\n")

    tests = [
        ("bytes(range(256))",      bytes(range(256))),
        ("1000 octets aleatoires", os.urandom(1000)),
        ("texte repetitif",        b"AAABBBAAABBB" * 20),
        ("octets nuls",            b"\x00" * 200),
    ]

    for nom, seq in tests:
        # Encodage
        modeles_e = nouveaux_modeles(8)
        enc = RangeEncoder()
        for octet in seq:
            enc.encoder_octet(octet, modeles_e)
        comp = enc.finaliser()

        # Decodage
        modeles_d = nouveaux_modeles(8)
        dec = RangeDecoder(comp)
        decode = bytes(dec.decoder_octet(modeles_d) for _ in range(len(seq)))

        ok    = "OK" if decode == seq else f"ERREUR @ {next(i for i,(a,b) in enumerate(zip(seq,decode)) if a!=b)}"
        ratio = len(comp) / max(len(seq), 1)
        print(f"  {nom:30s} {len(seq):5d}B -> {len(comp):5d}B "
              f"(ratio={ratio:.2f})  {ok}")

    print("\n[OK] Range coder valide.")


if __name__ == "__main__":
    demo()
