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
| 2026-10-02 | Archivadas y el historial de conciliaciones también van en `.table-scroll` | a 375px, Archivadas medía 480px; el historial, 459px, y lo que se deslizaba era el diálogo entero, formulario incluido |

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

## Rendimiento (2026-09-09)

La página pedía el saldo, el número de movimientos y las conciliaciones **cuenta
por cuenta**: cuatro consultas por cuenta más las de la página. Medido sobre una
copia de la base real (9 cuentas, 947 movimientos): **39 consultas**. Con 30
cuentas, 123. Con 100, 403.

Ahora son tres consultas agregadas y una función nueva, `balances_by_account`,
que saca todos los saldos de una vez respetando la regla rara: una cuenta de
inversión vale su última valoración declarada, y solo si no hay ninguna cuenta
lo aportado.

**7 consultas, y las mismas 7 con 100 cuentas.**

Comprobado sobre la base real cuenta por cuenta: los nueve saldos coinciden al
céntimo con los que daba `account_balance`, incluida la de inversión.
