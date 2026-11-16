#!/usr/bin/env bash
# TNT — Qué viaja al instalar y al empaquetar. Lo cargan install.sh y package.sh.
#
# Lo que git ignora no es código: datos del usuario, extractos, capturas con
# datos de verdad, entornos, logs. La lista de verdad es .gitignore. rsync la
# lee tal cual; para tar va traducida aquí, UNA vez. Antes cada script llevaba
# la suya y se desfasaban: así se colaron las subcarpetas de data/, las
# capturas y, sin rsync, los extractos de la raíz.
#
# tests/test_empaquetado.py pone un señuelo por cada patrón de .gitignore y
# comprueba que ninguno viaja por ningún camino. Un patrón nuevo allí obliga a
# ponerle señuelo, y el señuelo, a excluirlo aquí.

# Lo que tar no lleva. «./x» es solo el de la raíz; «x», en cualquier carpeta.
# .claude/ son los ajustes del agente y los worktrees de otras sesiones: no son
# de la app, aunque git siga alguno.
EXCLUSIONES_TAR=(
    --exclude=.git --exclude=./.claude
    --exclude=./data --exclude=./extracts --exclude=./logs --exclude=./mockups
    --exclude=./packaging/dist --exclude=./reinstalarcambios.txt
    --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache
    --exclude=.vscode --exclude=.idea --exclude=.DS_Store --exclude=.env.local
    '--exclude=*.pyc' '--exclude=*.pyo' '--exclude=*.swp' '--exclude=*.log'
    '--exclude=*.db' '--exclude=*.db-journal' '--exclude=*.db-wal' '--exclude=*.db-shm'
    '--exclude=*.xls' '--exclude=*.xlsx' '--exclude=*.csv' '--exclude=*.ofx' '--exclude=*.pdf'
    '--exclude=our-build-*.png' '--exclude=diff-*.png'
)

# El único PDF que viaja: .gitignore lo exceptúa de «*.pdf» con «!», y ni rsync
# ni tar entienden esa excepción.
MANUAL_PDF="docs/Manual-TNT.pdf"

# es_repositorio CARPETA — cierto si CARPETA es la raíz de un repositorio git.
# No basta con «estar dentro de uno»: un paquete desempaquetado dentro de un
# repositorio ajeno no tiene nada seguido, y saldría vacío.
es_repositorio() {
    local raiz
    raiz="$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)" || return 1
    [[ "$raiz" == "$(cd "$1" && pwd -P)" ]]
}

# copiar_con_rsync ORIGEN DESTINO — copia el código y quita del destino lo que
# ya no está en el origen. Lo excluido tampoco se borra: data/, logs/ y .venv/
# de la instalación no se tocan nunca.
copiar_con_rsync() {
    rsync -a --delete \
        --include="/$MANUAL_PDF" \
        --filter=':- .gitignore' \
        --exclude='/data/' --exclude='/.claude/' \
        --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='.env.local' \
        --exclude='*.pyc' --exclude='logs' --exclude='.pytest_cache' \
        --exclude='packaging/dist' \
        "$1"/ "$2"/
}

# copiar_con_tar ORIGEN DESTINO — lo mismo donde no hay rsync. No borra del
# destino lo que ya no esté en el origen.
copiar_con_tar() {
    (cd "$1" && tar "${EXCLUSIONES_TAR[@]}" -cf - .) | (cd "$2" && tar -xf -)
    if [[ -f "$1/$MANUAL_PDF" ]]; then
        mkdir -p "$2/$(dirname "$MANUAL_PDF")"
        cp -p "$1/$MANUAL_PDF" "$2/$MANUAL_PDF"
    fi
}

# copiar_seguidos_por_git ORIGEN DESTINO — solo lo que git sigue: lo que sale
# de este PC en un paquete. Un fichero nuevo sin añadir a git no viaja.
# --no-recursion: si git lista una carpeta (un submódulo), no se lleva lo de dentro.
copiar_seguidos_por_git() {
    (cd "$1" && git ls-files -z -- . ':(exclude).claude' \
        | tar --null --no-recursion --ignore-failed-read -T - -cf -) | (cd "$2" && tar -xf -)
}
