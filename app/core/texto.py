"""Normalizacao de texto para busca (B4)."""

import unicodedata


def sem_acento(texto: str | None) -> str:
    """Minusculas, sem acentos e com espacos simples: "  Feijão  Preto" -> "feijao preto".

    Usado para buscar sem depender de acento nem de maiusculas, igual no
    Postgres e no SQLite dos testes (o `lower()` do SQLite so trata ASCII).
    """
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_marcas = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_marcas.casefold().split())


def palavras_da_busca(termo: str | None) -> list[str]:
    """Palavras do termo, normalizadas e sem pontuacao nas pontas.

    A busca exige todas, em qualquer ordem: "feijao preto" encontra
    "Feijão, preto, cozido".
    """
    return [p for p in (w.strip(".,;:-()") for w in sem_acento(termo).split()) if p]
