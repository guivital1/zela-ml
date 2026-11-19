import re

from zela_ml.dataset import normalize

# O dicionário é fixo. Cada termo distinto vale um ponto.
TERMS = {
    "iluminacao": (
        "poste",
        "postes",
        "lampada",
        "lampadas",
        "luminaria",
        "luminarias",
        "iluminacao",
        "sem luz",
        "luz da rua",
        "escuridao",
    ),
    "limpeza": (
        "lixo",
        "sujeira",
        "entulho",
        "coleta",
        "cata bagulho",
        "descarte",
        "lixeira",
        "lixeiras",
        "residuos",
        "varricao",
    ),
    "pavimentacao": (
        "buraco",
        "buracos",
        "asfalto",
        "cratera",
        "crateras",
        "pavimento",
        "tapa buraco",
        "recapeamento",
        "pista",
    ),
    "drenagem": (
        "bueiro",
        "bueiros",
        "boca de lobo",
        "alagamento",
        "alagada",
        "alagado",
        "enxurrada",
        "drenagem",
        "sarjeta",
        "agua acumulada",
    ),
    "acessibilidade": (
        "rampa",
        "rampas",
        "calçada",
        "calçadas",
        "cadeira de rodas",
        "cadeirante",
        "piso tatil",
        "travessia",
        "guia rebaixada",
    ),
    "areas_verdes": (
        "arvore",
        "arvores",
        "galho",
        "galhos",
        "poda",
        "mato",
        "vegetacao",
        "rocada",
        "grama",
    ),
}


def keywords_prediction(description: str) -> str:
    text = " " + " ".join(re.findall(r"[a-z0-9]+", normalize(description))) + " "
    votes = {
        category: sum(f" {normalize(term)} " in text for term in terms)
        for category, terms in TERMS.items()
    }
    highest = max(votes.values())
    winners = [category for category, count in votes.items() if count == highest]
    return winners[0] if highest and len(winners) == 1 else "revisao"
