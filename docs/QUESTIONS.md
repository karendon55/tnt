# Decisions

One line per decision, as it is decided. Read this file before asking anything.
An answered question is settled unless the human reopens it.

Format:

    - YYYY-MM-DD [surface] Issue N: question? -> answer

- 2026-09-08 [harness] Instalar el estándar ENGINEERING-AND-DESIGN en ~/.claude, con hook pre-commit machine-wide -> sí
- 2026-09-08 [harness] ¿git init en ~/.claude para dar historial al harness? -> no; se usa el backup existente (angus-backup.py) porque ~/.claude guarda token y credenciales
- 2026-09-08 [harness] ¿Incluir standards/, skills/, git-hooks/ y ui-vocabulary-check.py en el backup a karendon55/angus-memory? -> sí
- 2026-09-08 [design] Intención estética de TNT en una línea -> pendiente, la decide Jesús César antes del próximo rediseño
- 2026-09-08 [design] Anti-estética de TNT -> ni SaaS genérico, ni app bancaria, ni hoja de cálculo
- 2026-09-08 [design] Referencias visuales bloqueadas -> shadcn charts + Tremor (1 de 3; faltan dos)
- 2026-09-08 [design] ¿Reescribir los 221 hallazgos existentes de color literal? -> no; el hook solo bloquea los nuevos
- 2026-09-08 [design] Dirección visual del panel (Fase 0, 4 bocetos) -> la 2 (Papel) pero en tema oscuro, el que ya tiene la app
- 2026-09-08 [design] Pareja tipográfica dentro de "papel en oscuro" -> pendiente, boceto en explorations/panel-papel-oscuro/
- 2026-09-08 [design] Pareja tipográfica de "papel en oscuro" -> E: Georgia en hero, titulares y KPI; sans tabular en tablas y categorías
- 2026-09-08 [design] Temperatura del fondo oscuro -> neutro (#0d0d0d), el que ya usa TNT
- 2026-09-08 [panel] Issue 1: ¿alcance del cambio en tnt.css y qué pasa con Impact? -> tokens globales, panel primero; --font-display pasa a Georgia y nace --font-brand con Impact para la marca
- 2026-09-08 [panel] Issue 2: ¿cómo quitar la tarjeta sin romper las otras once pantallas? -> clase nueva .sheet; .card se queda intacta
- 2026-09-08 [panel] Issue 3: ¿qué cuenta como prueba? -> capturas a 1440/1024/768/375 contra el boceto, más Movimientos y Categorías para no-regresión
- 2026-09-08 [panel] Issue 1: ¿dónde termina la serie del saldo cuando los extractos se quedan atrás respecto a hoy? -> en el último mes con datos (movimiento o valoración), no en el mes actual; los huecos internos arrastran el saldo anterior
- 2026-09-08 [panel] ¿La sparkline del hero se queda? -> no, retirada: duplicaba la gráfica de evolución del saldo
- 2026-09-08 [panel] ¿Mover el selector de mes debajo del hero? -> sí, en una .monthbar cerrada por filete, como el boceto
- 2026-09-08 [entorno] ¿Cómo arregla run.sh el arranque tras el salto a Python 3.14? -> reusar el pick_python de packaging/tnt-launcher.sh (comprueba que uvicorn+fastapi se importen, no que el fichero exista)
- 2026-09-08 [entorno] ¿Borrar ~/.local/lib/python3.10 (50 MB huérfanos)? -> sí, a la papelera
