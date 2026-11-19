import re
from dataclasses import dataclass

from zela_ml.dataset import normalize

PREFIXOS = {"r": "rua", "av": "avenida", "trav": "travessa", "al": "alameda", "pca": "praca"}


def chave(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalize(texto)))


@dataclass(frozen=True)
class Endereco:
    local: str
    rua: str
    numero: str = ""
    bairro: str = ""

    @property
    def rua_chave(self) -> str:
        palavras = chave(self.rua).split()
        if palavras:
            palavras[0] = PREFIXOS.get(palavras[0], palavras[0])
        return " ".join(palavras)

    @property
    def numero_chave(self) -> str:
        numero = re.sub(r"^n[º°o]?\.?\s*(?=\d)", "", normalize(self.numero))
        numero = re.sub(r"[^a-z0-9]", "", numero)
        return str(int(numero)) if numero.isdecimal() else numero

    @classmethod
    def legado(cls, local: str) -> "Endereco":
        match = re.fullmatch(r"(.+?)\s*,?\s+(?:n[º°o.]?\s*)?(\d+\s*[A-Za-z]?)", local)
        if match and chave(match[1]) not in {*PREFIXOS, *PREFIXOS.values()}:
            return cls(local, match[1].rstrip(","), match[2])
        match = re.fullmatch(r"(.+?),\s*(\d+\s*[A-Za-z]?)", local)
        return cls(local, *match.groups()) if match else cls(local, local)
