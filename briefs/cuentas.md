# Cuentas — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

`/cuentas` (Configuración). El alta y baja de cuentas, el saldo inicial y la
conciliación con el banco. Se entra poco: cuando abres una cuenta, cuando archivas
una que ya no usas, y sobre todo cuando cuadras el saldo con el extracto.

Las cuentas de inversión siguen aquí con su saldo, pero el valor del fondo se declara
en Inversiones (decisión del 2026-09-08).

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | El estado de conciliación deja de ser una píldora con `✓` y `⚠` | «cuadra, hace 35 d» y «difiere −24,08 €» dicen más, y el color ya marca el tono |
| 2026-09-09 | Editar y archivar pasan a iconos con `aria-label`; Conciliar se queda en texto | tres botones de texto por fila comían la mitad del ancho, y Conciliar es la acción que se busca |
| 2026-09-09 | El formulario flotante de edición comparte clase con el de Reglas (`.inline-edit`) | es el mismo patrón; alcanzar el primitivo antes que inventar otro |
| 2026-09-09 | La tabla va dentro de `.table-scroll` | ocho columnas no caben a 375px; que scrolle la tabla, no la página |

## Qué NO hacer aquí

- Ni tarjetas: hoja y filete.
- Ni un segundo botón rojo: «Nueva cuenta» es el único (los de dentro de un diálogo
  no cuentan, cada modal tiene su acción principal).
- Ni símbolos que el sistema convierta en emoji para marcar estado.

## Validación (2026-09-09)

- [x] 1440 y 375 en navegador real; la tabla scrollea dentro, la página no
- [x] Tema claro y tema oscuro
- [x] Cero `style=` y cero emoji en `accounts.html`
- [x] Diálogo de conciliar: abre, guarda, y la fila pasa a «difiere −24,08 €»
      (probado de punta a punta sobre la base de demostración)
- [x] Botones de icono con `aria-label` que nombra la cuenta
