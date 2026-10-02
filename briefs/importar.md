# Importar — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

El ritual mensual, y la razón de ser de TNT frente a HomeBank. Son cuatro pantallas
encadenadas: `/importar` (subir), el preview de lo que va a entrar, el resultado, y
`/importar/lotes` para deshacer una importación que salió mal.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | El h1 del preview pasa de "Preview de importación" a **"Lo que va a entrar"** | dice lo mismo sin anglicismo, y es exactamente la pregunta que uno se hace |
| 2026-09-09 | Las cajas de error dejan de ser tarjetas con borde de color | pasan a la línea de aviso del panel, con el punto en rojo o verde según el tono |
| 2026-09-09 | Los cuatro KPI del resultado usan la banda, con `is-4` | el resumen trae cuatro cifras, no tres; a 1000px se parten en dos filas |
| 2026-09-09 | Una sola acción roja por pantalla | subir → "Importar"; preview → "Confirmar e insertar N"; resultado → "Ver panel". Lo demás, enlaces |
| 2026-09-09 | Las filas duplicadas del preview usan `.is-dim` | estaban atenuadas con un `style="opacity"` en línea |
| 2026-09-09 | Lotes incluye la subnavegación de Configuración; preview y resultado no | son estados de un flujo, no secciones: ahí la subnavegación solo invita a irse |
| 2026-09-09 | La banda de KPIs solo cuenta lo del lote; lo demás baja al pie | cuatro cifras juntas se leen como una unidad, y una que hablaba de toda la base hacía que un fichero de 3 filas presumiera de 71 |
| 2026-10-02 | La tabla de Lotes va en `.table-scroll` | a 375px medía 972px (cada fichero, en una línea que no se parte) y empujaba la página; ahora se desliza dentro de su caja |
| 2026-10-02 | Las tablas de la vista previa y del resultado, también | a 375px, 866px y 835px con un extracto de prueba de descripciones largas |

## Qué NO hacer aquí

- Ni emoji en los títulos ni en los botones (había 📜 y 📥 dos veces).
- Ni bordes de color con literales para marcar el tono de un mensaje.
- Ni un segundo rojo compitiendo con la acción de confirmar.

## Validación (2026-09-09)

Recorrido entero sobre la base de demostración, con un extracto de EuroCaja Rural
fabricado a mano (`explorations/` no lo guarda: son tres filas inventadas):

- [x] Subir → el preview dice "3 se insertarán, 0 duplicados" y lista las tres filas
- [x] Confirmar → "Importación completada", 3 nuevos, detalle por fichero
- [x] Las tres filas aparecen en la base
- [x] Lotes registra el lote #1 con sus 3 insertados
- [x] Deshacer → 303, las tres filas desaparecen y el mensaje sale con el punto verde
- [x] Cero `style=`, cero `.card` y cero emoji en las cuatro plantillas

## Pendiente

- ~~En el resultado, "Auto-categorizados" contó **71** habiendo insertado 3~~
  **resuelto el 2026-09-09**: `apply_rules_to_uncategorized` devuelve ahora dos cifras
  (total y las del lote). La banda de KPIs, que es toda "lo que ha entrado", enseña solo
  las del lote; los movimientos antiguos que las reglas rescatan de paso bajan al pie,
  junto a las reglas aprendidas, que es de donde vienen. Comprobado en la base de
  demostración: 2 filas importadas → KPI **1**, pie **59 anteriores**.
