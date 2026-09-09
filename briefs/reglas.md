# Reglas — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

`/reglas` (Configuración). Reúne todo lo que en TNT es una regla: las de
categorización automática —manuales, aprendidas e integradas— y las de
transferencias externas, que vivían escondidas dentro de Cuentas. No es una pantalla
de uso diario: se entra cuando algo se categoriza mal.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | El h1 pasa de "Reglas de categorización" a **"Reglas"** | ya no solo hay de categorización; el subtítulo explica los dos tipos |
| 2026-09-09 | La acción roja es **Nueva regla** (de categorización) | "Nueva regla de transferencia" pasa a contorno: dos rojos competían |
| 2026-09-09 | Los dos diálogos se llaman distinto (`newRule` / `newTransferRule`) | ambos se llamaban `newRule`; `getElementById` abría siempre el primero |
| 2026-09-09 | Editar y borrar pasan a botones de icono con `aria-label` | eran texto sin nombre accesible, y ocupaban media columna |
| 2026-09-09 | Los grupos dejan de ser tarjetas | hoja y filete, como el resto |

## Qué NO hacer aquí

- Ni un segundo botón rojo: el de categorización es el único.
- Ni dos elementos con el mismo `id`, por muy separados que parezcan en la plantilla.
- Ni emoji en las acciones de la cabecera.

## Validación (2026-09-09)

- [x] 1440 y 375 en navegador real; la cabecera de sección envuelve en estrecho
- [x] Cero `style=` y cero emoji en `rules.html`
- [x] Botones de icono con `aria-label` que nombra el patrón de la regla
- [x] Tres tests nuevos: ningún id repetido en ninguna página, los dos diálogos
      existen y son distintos, y todo `getElementById` apunta a algo que existe
