"""
El árbol de categorías: leerlo entero, y encontrar (o crear) una por su ruta.

Las categorías son de dos niveles, principal › subcategoría. El árbol sigue el
que traen las importaciones de ING. Con `resolve_category` el código pide una
categoría por su ruta («Hogar|Luz y gas»): recibe la que ya exista y, si
falta, se crea.
"""
from __future__ import annotations

import sqlite3


# Categorías del banco que el usuario quiere en otro sitio. ING manda a veces
# «Vehículo y transporte › Transporte público», y el usuario tiene todo el
# transporte público en «Transporte»: sin traducirla, cada importación que la
# trajera volvería a crear la repetida. Decidido por el usuario.
_PISTAS_DEL_BANCO = {
    "Vehículo y transporte|Transporte público": "Transporte|Transporte público",
}


def resolve_category(cur: sqlite3.Cursor, hint: str | None,
                     default_kind: str = "expense") -> int | None:
    """
    hint = "Alimentación" o "Alimentación|Supermercados y alimentación"
    Devuelve id de la subcategoría si existe, si no el de la padre.
    Crea la jerarquía que falte respetando el nombre original del banco.
    """
    if not hint:
        return None
    hint = _PISTAS_DEL_BANCO.get(hint.strip(), hint)
    parts = [p.strip() for p in hint.split("|") if p.strip()]
    if not parts:
        return None
    parent_name = parts[0]
    sub_name = parts[1] if len(parts) > 1 else None

    parent_row = cur.execute(
        "SELECT id FROM categories WHERE parent_id IS NULL AND LOWER(name) = LOWER(?)",
        (parent_name,),
    ).fetchone()
    if parent_row:
        parent_id = parent_row["id"]
    else:
        # OR IGNORE: si otra la creó entre medias, el índice único de las
        # principales lo impide, y se usa la suya (ver db._indice_principales).
        cur.execute(
            "INSERT OR IGNORE INTO categories(name, kind) VALUES (?, ?)",
            (parent_name, default_kind),
        )
        parent_id = cur.execute(
            "SELECT id FROM categories WHERE parent_id IS NULL AND LOWER(name) = LOWER(?)",
            (parent_name,),
        ).fetchone()["id"]

    if parent_id and sub_name:
        sub_row = cur.execute(
            "SELECT id FROM categories WHERE parent_id = ? AND LOWER(name) = LOWER(?)",
            (parent_id, sub_name),
        ).fetchone()
        if sub_row:
            return sub_row["id"]
        # Creamos la subcategoría si no existe (ING tiene algunas que no sembramos)
        cur.execute(
            "INSERT OR IGNORE INTO categories(name, parent_id, kind) "
            "SELECT ?, ?, kind FROM categories WHERE id = ?",
            (sub_name, parent_id, parent_id),
        )
        sub_row = cur.execute(
            "SELECT id FROM categories WHERE parent_id = ? AND LOWER(name) = LOWER(?)",
            (parent_id, sub_name),
        ).fetchone()
        return sub_row["id"] if sub_row else parent_id

    return parent_id


def category_tree(cur: sqlite3.Cursor) -> list[dict]:
    cats = cur.execute(
        "SELECT id, name, parent_id, kind FROM categories ORDER BY parent_id IS NOT NULL, name"
    ).fetchall()
    by_parent: dict[int | None, list] = {}
    by_id: dict[int, dict] = {}
    for c in cats:
        d = {"id": c["id"], "name": c["name"], "parent_id": c["parent_id"],
             "kind": c["kind"], "children": []}
        by_id[c["id"]] = d
        by_parent.setdefault(c["parent_id"], []).append(d)
    tree = by_parent.get(None, [])
    for parent in tree:
        parent["children"] = by_parent.get(parent["id"], [])
    return tree
