# Handoff — Setup de Angus (agente de backup) en GitHub

**Fecha:** 2026-04-21
**Usuario:** Jesús César (`karendon55` en GitHub)
**Estado:** Backup funcional. Hook instalado pero sin verificar que dispare en vivo (requiere un SessionEnd real).

---

## Contexto

Jesús César usa Claude Code para construir una app que reemplaza a HomeBank (gestión de finanzas personales con extractos de ING y CaixaBank). Bautizó a su agente como **Angus** (por Angus Young de AC/DC). Pidió que haya un backup automático en GitHub de memoria, slash commands, planes y workspace para no perder nada entre sesiones o equipos.

## Qué está hecho

1. **Token de GitHub** almacenado en `/home/trooper/.claude/.angus-token` (perms 0600). Cuenta: `karendon55`, creada el 2026-04-21.
2. **Repo privado** `karendon55/angus-memory` creado vía API, con backup inicial de 28 archivos.
3. **Script de backup** en `/home/trooper/.claude/angus-backup.py`:
   - Python stdlib (urllib + hashlib + base64) — **git no está instalado en el sistema**, sudo pide password, así que el script usa la GitHub Git Data API directamente.
   - Flujo: blob → tree (con `base_tree` para acumular) → commit → update ref.
   - Cache local de SHAs ya empujados en `/home/trooper/.claude/.angus-pushed-blobs` para evitar re-uploads.
   - Firma los commits como `Angus <angus@users.noreply.github.com>`.
4. **Hook `SessionEnd`** añadido en `/home/trooper/.claude/settings.json` (async, timeout 120s). Ejecuta el script al cerrar cada sesión.
5. **Slash command `/backup`** en `/home/trooper/.claude/commands/backup.md` para sync manual.
6. **Memoria actualizada** con dos entradas nuevas (identidad Angus + sistema de backup), indexadas en `MEMORY.md`.

## Qué se sube al repo (prefijos)

| Origen local                                                     | En el repo               |
|------------------------------------------------------------------|--------------------------|
| `~/.claude/projects/-home-trooper-IA/memory/`                    | `memory/`                |
| `~/.claude/commands/`                                            | `commands/`              |
| `~/.claude/plans/`                                               | `plans/`                 |
| `~/.claude/settings.json`                                        | `config/settings.json`   |
| `~/IA/` (filtrado)                                               | `workspace/`             |

**Exclusiones** (nunca se suben): `.venv/`, `data/`, `__pycache__/`, `.claude/` (dentro del workspace), `.git/`, `node_modules/`, `.pytest_cache/`, extensiones `.xls .xlsx .csv .ofx .pdf .db .db-journal .db-wal .db-shm .log .pyc .pyo`, `.DS_Store`, el token y la cache. Archivos > 5 MB se skippean.

## Qué queda pendiente / por verificar

1. **Validar que el hook SessionEnd dispare.** No se pudo probar en esta sesión porque el hook corre fuera del turno. Opciones para verificar:
   - Cerrar la sesión y abrir una nueva — ver si aparece un nuevo commit en https://github.com/karendon55/angus-memory/commits/main
   - Si no aparece, abrir `/hooks` en Claude Code una vez (fuerza recarga de la config) o reiniciar. Caveat conocido: el watcher de settings solo vigila directorios que ya tenían settings al iniciar la sesión actual.
2. **Activar 2FA en GitHub** (https://github.com/settings/security). La cuenta no tiene 2FA y el token circuló en texto plano por la conversación previa. Recomendar al usuario rotarlo tras activar 2FA.
3. **El token está en plano en el disco (`~/.claude/.angus-token`, 0600).** Alternativa más segura cuando el usuario esté listo: `libsecret`/`pass`/`gh auth login` (requeriría instalar `gh`).
4. **Limitación del script:** solo añade/actualiza archivos; no borra remotos al borrar locales (usa `base_tree` acumulativo). Si se necesita purga, hacerla manualmente en GitHub o invalidar el cache.
5. **`tests/` del workspace** apareció vacío en el primer push — verificar si era intencional o si el filtro de exclusión lo estaba pillando por error.

## Comandos útiles para el siguiente agente

```bash
# Backup manual
python3 /home/trooper/.claude/angus-backup.py

# Ver contenido actual del repo (listado de archivos)
TOKEN=$(cat /home/trooper/.claude/.angus-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/karendon55/angus-memory/git/trees/main?recursive=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(t['path']) for t in sorted(d['tree'], key=lambda x:x['path']) if t['type']=='blob']"

# Ver últimos commits
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/karendon55/angus-memory/commits?per_page=5" \
  | python3 -c "import json,sys; [print(c['sha'][:7], c['commit']['message']) for c in json.load(sys.stdin)]"

# Resetear cache de blobs (forzar re-upload completo)
rm /home/trooper/.claude/.angus-pushed-blobs
```

## Rutas clave

- Script: `/home/trooper/.claude/angus-backup.py`
- Token: `/home/trooper/.claude/.angus-token`
- Cache: `/home/trooper/.claude/.angus-pushed-blobs`
- Settings con hook: `/home/trooper/.claude/settings.json`
- Slash command: `/home/trooper/.claude/commands/backup.md`
- Memoria de Angus: `/home/trooper/.claude/projects/-home-trooper-IA/memory/user_agent_angus.md`
- Memoria del backup: `/home/trooper/.claude/projects/-home-trooper-IA/memory/reference_angus_backup.md`
- Repo remoto: https://github.com/karendon55/angus-memory

## Convenciones acordadas con el usuario

- Idioma: **español**.
- Firma de commits: `Angus <angus@users.noreply.github.com>`.
- Antes de recomendar acciones destructivas en GitHub (force push, borrar repos, cerrar PRs), pedir confirmación — acabamos de empezar y la cuenta está fresca.
