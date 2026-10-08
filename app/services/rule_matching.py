"""
Cuándo casa una regla de categoría con una descripción, y cuál gana si casan
varias.

Es el único sitio que lo decide. Lo usan la categorización al importar y al
reentrenar (`categorizer.apply_rules_to_uncategorized`), la regla recién
creada (`categorizer.apply_rule_retroactively`), la sugerencia de regla al
recategorizar en Movimientos y la carga del histórico de HomeBank. Cuando
cada uno casaba a su manera, una misma regla hacía una cosa al crearla y
otra al importar.

Los patrones se guardan en mayúsculas. `matching_rules` y `best_rule` pasan
la descripción a mayúsculas; a `pattern_matches` se le da ya pasada.
"""
from __future__ import annotations


def pattern_matches(pattern: str, text: str) -> bool:
    """¿Está `pattern` en `text` como palabra entera (o palabras, si lleva
    espacios)? Los dos en mayúsculas.

    Una palabra es una racha de letras: los números, los espacios y los signos
    la cortan; las tildes y la Ñ no. Así, «IBI» casa con «RECIBO IBI 2025»,
    «IBI-URBANA» o «IBI2025», y no con «RECIBIDA» ni con «IBIS»; «PREST» casa
    con «PREST.DESEMPLEO» y no con «PRESTAMO». Es como se aprenden las reglas:
    `extract_tokens` saca palabras enteras.

    Solo se mira el borde por donde el patrón empieza o acaba en letra: si
    acaba en número o en signo («T145», «S.L.»), por ese lado ya está cortado.

    Un patrón vacío no casa con nada (por subcadena casaba con todo).
    """
    if not pattern.strip():
        return False
    check_before, check_after = pattern[0].isalpha(), pattern[-1].isalpha()
    start = text.find(pattern)
    while start != -1:
        end = start + len(pattern)
        free_before = not check_before or start == 0 or not text[start - 1].isalpha()
        free_after = not check_after or end == len(text) or not text[end].isalpha()
        if free_before and free_after:
            return True
        start = text.find(pattern, start + 1)  # puede volver a aparecer, suelta
    return False


def matching_rules(rules, description: str | None) -> list:
    """Las reglas que casan con la descripción, en el orden en que vienen."""
    text = (description or "").upper()
    return [r for r in rules if pattern_matches(r["pattern"], text)]


def rule_rank(rule) -> tuple[int, int, int]:
    """Criterio de desempate cuando varias reglas coinciden, de más a menos peso:

    1. Regla manual — lo que el usuario escribió explícitamente manda.
    2. Patrón más largo — el más específico gana. Es lo que permite que
       "REPSOL WAYLET" gane a "REPSOL" en la misma descripción; ordenar solo
       por frecuencia hacía que el token genérico y repetido se impusiera al
       específico.
    3. priority * hits — a igual especificidad, la mejor respaldada.
    """
    return (
        1 if rule["source"] == "manual" else 0,
        len(rule["pattern"]),
        rule["priority"] * max(rule["hits"], 1),
    )


def best_rule(rules, description: str | None):
    """La regla que gana para esa descripción, o None si no casa ninguna."""
    matching = matching_rules(rules, description)
    return max(matching, key=rule_rank) if matching else None
