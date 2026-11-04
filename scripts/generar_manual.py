"""
Genera el manual de usuario, docs/Manual-TNT.docx y su PDF, desde docs/Manual-TNT.md.

El texto vive en Markdown, que se lee y se revisa en git. El Word conserva su
portada, sus estilos y su pie de página porque el propio .docx hace de
plantilla: se le quita lo que va detrás del índice y se escribe de nuevo con
sus estilos. Volver a lanzarlo da siempre el mismo documento.

    .venv/bin/python scripts/generar_manual.py            # Word y PDF
    .venv/bin/python scripts/generar_manual.py --sin-pdf  # solo el Word

Necesita python-docx (requirements-dev.txt). El PDF lo saca LibreOffice, con el
índice ya relleno: ver scripts/manual_a_pdf.py.

Del Markdown entiende: «# », «## » y «### » (capítulos y secciones; cada
capítulo empieza en página nueva), párrafos, listas con «- », bloques ``` de
código, tablas con «|» y, dentro del texto, **negrita**, *cursiva* y `código`.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.parfmt import ParagraphFormat

RAIZ = Path(__file__).resolve().parent.parent
MD = RAIZ / "docs" / "Manual-TNT.md"
DOCX = RAIZ / "docs" / "Manual-TNT.docx"
PDF = RAIZ / "docs" / "Manual-TNT.pdf"

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_EN_LINEA = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)")
# Las letras de la plantilla, Calibri y Consolas, no están instaladas; van las
# instaladas que más se parecen (las que el sistema da por sustitutas).
_LETRA_TEXTO = "Noto Sans"
_LETRA_CODIGO = "DejaVu Sans Mono"
_EN_LUGAR_DE = {"Calibri": _LETRA_TEXTO, "Consolas": _LETRA_CODIGO}


def _estilo(parrafo) -> str:
    p = parrafo.find(f"{_W}pPr/{_W}pStyle")
    return p.get(f"{_W}val") if p is not None else ""


def _texto_de(elemento) -> str:
    return "".join(t.text or "" for t in elemento.iter(f"{_W}t"))


def _letras_de_los_estilos(doc) -> None:
    """Noto Sans en el texto y DejaVu Sans Mono en el código.

    El LibreOffice de ahora pone Noto Serif en lugar de cualquier letra que no
    esté instalada; el de mayo buscaba la parecida. Y los estilos heredaban
    además la «letra del tema» (Cambria), que prefiere a la del estilo. Todo
    salía en Noto Serif, el código también. Sin el tema, manda la del estilo, y
    es una que está."""
    for parte in (doc.styles.element, doc.element):
        for letras in parte.iter(qn("w:rFonts")):
            for atributo in ("w:asciiTheme", "w:hAnsiTheme"):
                letras.attrib.pop(qn(atributo), None)
            for atributo in ("w:ascii", "w:hAnsi"):
                actual = letras.get(qn(atributo))
                letras.set(qn(atributo), _EN_LUGAR_DE.get(actual, actual or _LETRA_TEXTO))


def _vaciar_tras_el_indice(doc) -> None:
    """Quita todo lo que va detrás del índice, menos las propiedades de la
    sección (el pie de página y los márgenes)."""
    hijos = list(doc.element.body.iterchildren())
    visto_indice = False
    for i, hijo in enumerate(hijos):
        if hijo.tag != f"{_W}p" or _estilo(hijo) not in ("Heading1", "TOCHeading"):
            continue
        if not visto_indice and _texto_de(hijo).strip() == "Índice":
            visto_indice = True
        elif visto_indice and _estilo(hijo) == "Heading1":
            for sobra in hijos[i:]:
                if sobra.tag != f"{_W}sectPr":
                    doc.element.body.remove(sobra)
            return
    if not visto_indice:
        sys.exit("La plantilla no tiene el «Índice»: no sé dónde empieza el cuerpo.")


def _poner_texto(parrafo, texto: str) -> None:
    """Cambia el texto de un párrafo sin tocar su formato."""
    parrafo.runs[0].text = texto
    for r in parrafo.runs[1:]:
        r.text = ""


def _cambiar(doc, empieza: str, texto: str) -> None:
    """Cambia el párrafo de la portada que empieza por `empieza`."""
    for p in doc.paragraphs:
        if p.text.startswith(empieza) and p.runs:
            _poner_texto(p, texto)
            return
    sys.exit(f"No encuentro el párrafo que empieza por «{empieza}».")


def _nota_del_indice(doc, texto: str) -> None:
    """Cambia la nota que va bajo el título «Índice». La reconoce por el sitio
    y no por el texto, que es justo lo que cambia: buscando el texto viejo, la
    segunda vuelta ya no la encontraba."""
    parrafos = doc.paragraphs
    for titulo, nota in zip(parrafos, parrafos[1:]):
        if titulo.text.strip() == "Índice" and nota.runs:
            _poner_texto(nota, texto)
            return
    sys.exit("No encuentro la nota que va bajo el título «Índice».")


def _indice_sin_entrada_propia(doc) -> None:
    """El título «Índice», con el estilo «TOC Heading»: se ve como el de un
    capítulo, pero el índice no lo recoge como su primera entrada."""
    for p in doc.paragraphs:
        if p.text.strip() == "Índice":
            p.style = doc.styles["TOC Heading"]
            return


def _en_linea(parrafo, texto: str) -> None:
    for trozo in _EN_LINEA.split(texto):
        if not trozo:
            continue
        if trozo.startswith("**"):
            parrafo.add_run(trozo[2:-2]).bold = True
        elif trozo.startswith("`"):
            parrafo.add_run(trozo[1:-1]).font.name = _LETRA_CODIGO  # pone ascii y hAnsi
        elif trozo.startswith("*"):
            parrafo.add_run(trozo[1:-1]).italic = True
        else:
            parrafo.add_run(trozo)


def _tabla(doc, filas: list[str]) -> None:
    celdas = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas
              if not re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?", f.strip())]
    tabla = doc.add_table(rows=len(celdas), cols=len(celdas[0]))
    tabla.style = doc.styles["Light Grid Accent 1"]  # la de la plantilla
    for fila, valores in zip(tabla.rows, celdas):
        for celda, valor in zip(fila.cells, valores):
            _en_linea(celda.paragraphs[0], valor)


def _aire_tras_las_tablas(doc) -> None:
    """El párrafo que sigue a una tabla iba pegado a su borde."""
    for tabla in doc.element.body.iter(f"{_W}tbl"):
        siguiente = tabla.getnext()
        if siguiente is not None and siguiente.tag == f"{_W}p":
            ParagraphFormat(siguiente).space_before = Pt(12)


def escribir(doc, markdown: str) -> None:
    lineas = markdown.split("\n")
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if linea.startswith("```"):
            # Un bloque es un solo párrafo, con saltos de línea: como párrafos
            # sueltos, cada línea llevaba su espacio antes y después.
            inicio = i + 1
            i = inicio
            while i < len(lineas) and not lineas[i].startswith("```"):
                i += 1
            doc.add_paragraph("\n".join(lineas[inicio:i]), style="TNT-Code")
        elif linea.startswith("|"):
            inicio = i
            while i < len(lineas) and lineas[i].startswith("|"):
                i += 1
            _tabla(doc, lineas[inicio:i])
            continue
        elif linea.startswith("### "):
            doc.add_paragraph(linea[4:], style="Heading 3")
        elif linea.startswith("## "):
            doc.add_paragraph(linea[3:], style="Heading 2")
        elif linea.startswith("# "):
            doc.add_paragraph(linea[2:], style="Heading 1").paragraph_format.page_break_before = True
        elif linea.startswith("- "):
            _en_linea(doc.add_paragraph(style="List Bullet"), linea[2:])
        elif linea.strip():
            _en_linea(doc.add_paragraph(), linea)
        i += 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Genera el manual de usuario desde docs/Manual-TNT.md.")
    p.add_argument("--sin-pdf", action="store_true", help="solo el Word")
    args = p.parse_args(argv)
    doc = Document(DOCX)
    _letras_de_los_estilos(doc)
    _vaciar_tras_el_indice(doc)
    _indice_sin_entrada_propia(doc)
    _cambiar(doc, "Versión documental:", f"Versión documental: {date.today().isoformat()}")
    _nota_del_indice(doc, "En el PDF el índice va ya relleno. En Word o LibreOffice, si aparece vacío, "
                          "haz clic derecho sobre él y elige «Actualizar campo» (o pulsa F9).")
    escribir(doc, MD.read_text(encoding="utf-8"))
    _aire_tras_las_tablas(doc)
    # El título es el que enseña el visor de PDF en lugar del nombre del fichero.
    doc.core_properties.title = "TNT · Manual de usuario"
    doc.core_properties.author = "Angus"
    doc.core_properties.comments = "Generado desde docs/Manual-TNT.md con scripts/generar_manual.py"
    doc.save(DOCX)
    print(f"Word: {DOCX.relative_to(RAIZ)}")
    if not args.sin_pdf:
        # `uno`, el puente con LibreOffice, viene con el Python del sistema, no con el del proyecto.
        subprocess.run(["/usr/bin/python3", str(RAIZ / "scripts" / "manual_a_pdf.py"), str(DOCX), str(PDF)],
                       check=True)
        print(f"PDF:  {PDF.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
