"""
Saca el PDF del manual con LibreOffice, con el índice relleno.

LibreOffice sin ventana no actualiza el índice al exportar: el PDF salía con la
página del índice en blanco. Aquí se abre el Word por el puente de LibreOffice
(`uno`), se actualiza el índice y se exporta. Va aparte de generar_manual.py
porque `uno` viene con el Python del sistema, no con el del proyecto:

    /usr/bin/python3 scripts/manual_a_pdf.py docs/Manual-TNT.docx docs/Manual-TNT.pdf

Usa un perfil de LibreOffice propio y temporal, para no chocar con un
LibreOffice que ya esté abierto.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.connection import NoConnectException


def _prop(nombre, valor):
    p = PropertyValue()
    p.Name, p.Value = nombre, valor
    return p


def main(docx: str, pdf: str) -> None:
    perfil = tempfile.mkdtemp(prefix="tnt-libreoffice-")
    tuberia = f"tnt_manual_{os.getpid()}"
    lo = subprocess.Popen(
        ["soffice", "--headless", "--invisible", "--norestore", "--nologo", "--nodefault",
         f"-env:UserInstallation=file://{perfil}", f"--accept=pipe,name={tuberia};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local = uno.getComponentContext()
        resolutor = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(150):
            try:
                ctx = resolutor.resolve(f"uno:pipe,name={tuberia};urp;StarOffice.ComponentContext")
                break
            except NoConnectException:
                time.sleep(0.2)
        else:
            sys.exit("LibreOffice no ha respondido.")
        escritorio = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        doc = escritorio.loadComponentFromURL(uno.systemPathToFileUrl(os.path.abspath(docx)), "_blank", 0,
                                              (_prop("Hidden", True),))
        indices = doc.getDocumentIndexes()
        # Dos veces: la primera mete las entradas y empuja páginas; la segunda
        # corrige los números de página que ese empujón movió.
        for _ in range(2):
            for i in range(indices.getCount()):
                indices.getByIndex(i).update()
        doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(pdf)), (_prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        try:
            escritorio.terminate()
        except Exception:  # LibreOffice corta la conexión al cerrarse
            pass
    finally:
        try:
            lo.wait(timeout=30)
        except subprocess.TimeoutExpired:
            lo.kill()
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: /usr/bin/python3 scripts/manual_a_pdf.py <entrada.docx> <salida.pdf>")
    main(sys.argv[1], sys.argv[2])
