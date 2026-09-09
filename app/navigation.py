"""
Mapa de la navegación de Configuración.

Vive aparte del router porque lo necesitan dos sitios que no pueden importarse
entre sí: el router que pinta la portada y templating.py, que lo expone como
global para que la subnavegación esté disponible en cualquier plantilla de
sección sin tener que pasarla desde cada handler.
"""
from __future__ import annotations

# El orden es el del menú lateral, y también el de la portada.
#
# Traspasos no está aquí a propósito: vive en la barra de arriba porque se
# revisa cada mes al importar. Repetirlo en Configuración contradecía la regla
# de reparto. Lo que sí cuelga de Reglas son sus emparejamientos automáticos.
SECCIONES_CONFIG = [
    {
        "key": "backup",
        "titulo": "Backup",
        "url": "/backup",
        "resumen": "Copias de seguridad de la base, cifrado y restauración.",
    },
    {
        "key": "accounts",
        "titulo": "Cuentas",
        "url": "/cuentas",
        "resumen": "Alta y baja de cuentas, saldos iniciales y conciliación con el banco.",
    },
    {
        "key": "categories",
        "titulo": "Categorías",
        "url": "/categorias",
        "resumen": "El árbol de categorías y subcategorías.",
    },
    {
        "key": "rules",
        "titulo": "Reglas",
        "url": "/reglas",
        "resumen": "Reglas de categorización automática y de transferencias externas.",
    },
    {
        "key": "import",
        "titulo": "Importar",
        "url": "/importar",
        "resumen": "Subir extractos del banco y revisar los lotes importados.",
    },
    {
        "key": "aliases",
        "titulo": "Alias",
        "url": "/alias",
        "resumen": "Nombres legibles para descripciones del banco que no hay quien lea.",
    },
]


# Qué valores de `active` cuelgan de Configuración, para iluminar la pestaña
# padre. Traspasos NO está: vive arriba, y en Configuración solo se enlaza.
ACTIVOS_CONFIG = {"settings", "backup", "accounts", "categories",
                  "rules", "import", "aliases"}
