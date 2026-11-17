"""
Los tests no pueden tocar nada del usuario: ni sus backups, ni la clave maestra,
ni su base.

Un backup de verdad va a ~/Dropbox y a ~/Documentos/contabilidad/backup, y la
clave maestra vive en ~/.config/tnt. El 17/11/2026 el test del modo
demostración se lanzó detrás de otro, sin el modo demostración puesto: hizo un
backup de una base de prueba encima de los dos backups de verdad y borró el
cifrado de Dropbox.

Por eso, antes de cargar nada de la app, la carpeta personal de los tests es
una temporal, y la base por defecto también (cada fichero de tests elige
además la suya con TNT_DB). Lo que traiga la terminal —un TNT_DB que apunte a
la base de verdad, un TNT_DEMO— no llega a los tests.

Esto corre al importar el paquete `tests`: con ./run_tests.sh (discover con
-t .) o con `python -m unittest tests.<fichero>`. tests/test_aislamiento.py
comprueba que ha corrido.
"""
import atexit
import os
import shutil
import tempfile

CASA_DE_PRUEBA = tempfile.mkdtemp(prefix="tnt-tests-casa-")
atexit.register(shutil.rmtree, CASA_DE_PRUEBA, ignore_errors=True)

os.environ["HOME"] = CASA_DE_PRUEBA
os.environ["TNT_DB"] = os.path.join(CASA_DE_PRUEBA, "tnt.db")
for _variable in ("TNT_DEMO", "TNT_DEMO_ROTULO"):
    os.environ.pop(_variable, None)
