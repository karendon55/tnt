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
- 2026-09-08 [panel] Fase 4: ¿qué pasa con las barras de colores por categoría? -> fuera; eran ocho literales en la plantilla y el boceto pide filas limpias
- 2026-09-08 [panel] Fase 4: ¿dónde va la franja de copia de seguridad? -> al final de la página; es utilidad, no contenido
- 2026-09-08 [panel] Fase 4: ¿el segmentado Saldo/Neto sigue en rojo? -> no; el rojo sólido se reserva a la acción principal
- 2026-09-08 [base] ¿Cómo se marca la pantalla activa en la barra superior? -> subrayado rojo; la píldora roja sólida se reserva a la acción principal
- 2026-09-08 [movimientos] ¿Cuál es la acción roja de la pantalla? -> Filtrar; Importar pasa a enlace porque lleva a otra página
- 2026-09-08 [movimientos] ¿Los controles de categoría y memo se ven siempre? -> no; callados hasta el hover, con borde de acento al foco
- 2026-09-08 [movimientos] ¿Qué hacemos con los iconos ✎ y 🗑? -> SVG en línea con aria-label que nombra fecha y descripción
- 2026-09-08 [movimientos] ¿Cómo se prueba el comportamiento sin arriesgar datos? -> base de demostración generada (scripts/make_demo_db.py) y ./run.sh --demo
- 2026-09-08 [movimientos] El swap OOB de la celda Categoría no ocurría nunca -> el <template> lo escondía de htmx; pasa a un <span>, con tests que lo fijan
- 2026-09-08 [movimientos] Los enlaces de paginación duplicaban page= -> include_query_params(page=…) lo reemplaza
- 2026-09-08 [arranque] TNT del menú mostraba datos de demostración -> el lanzador reutilizaba cualquier servidor que respondiera /health 200; ahora compara qué base sirve
- 2026-09-08 [arranque] ¿Cómo se sabe a simple vista que la sesión es de mentira? -> píldora "Datos de demostración" en la barra, encendida por TNT_DEMO=1
- 2026-09-08 [arranque] Reinstalar con TNT abierto dejaba el código viejo en memoria -> install.sh avisa y dice cómo reiniciarlo
- 2026-09-08 [nav] ¿Traspasos arriba o dentro de Configuración? -> arriba; se revisa cada mes tras importar. Sus reglas automáticas sí bajan a Reglas
- 2026-09-08 [nav] Issue 1: ¿las secciones de Configuración cambian de URL? -> no; conservan la suya y comparten subnavegación
- 2026-09-08 [nav] Issue 2: ¿las cuentas de inversión siguen en Cuentas? -> sí, con su saldo; a Inversiones se muda la gestión del valor
- 2026-09-08 [nav] Issue 3: ¿tests de rutas? -> sí, con httpx2 en requirements-dev.txt; 11 tests de navegación
- 2026-09-09 [nav] Traspasos estaba en la barra y también dentro de Configuración -> solo arriba; una pantalla, un sitio
- 2026-09-09 [reglas] Dos <dialog id="newRule"> en la misma página -> el de transferencias pasa a newTransferRule; test de ids únicos en todas las páginas
- 2026-09-09 [reglas] ¿Cuál es la acción roja? -> Nueva regla de categorización; la de transferencia pasa a contorno
- 2026-09-09 [inversiones] ¿"Guardar valoración" en rojo repitiéndose por fondo? -> sí; es la misma acción repetida, no dos compitiendo
- 2026-09-09 [gráficos] Al cambiar de tema sin recargar la línea de tinta desaparecía -> tnt.js avisa y los gráficos se repintan; los estáticos llevan sello de versión
- 2026-09-09 [cuentas] ¿Cómo se marca el estado de conciliación sin emoji? -> texto y color: «cuadra, hace N d» o «difiere −X €»
- 2026-09-09 [cuentas] ¿Tres botones de texto por fila? -> no; Conciliar en texto, editar y archivar como iconos con aria-label
- 2026-09-09 [importar] ¿Subnavegación en preview y resultado? -> no; son estados de un flujo, no secciones. Sí en Lotes
- 2026-09-09 [importar] ¿Cómo se marcan los mensajes de error y de éxito? -> línea de aviso con punto rojo o verde, sin cajas de color
- 2026-09-09 [traspasos] ¿Cuál es la acción roja? -> "Emparejar como traspaso" del formulario; el de cada sugerencia es acción de fila
- 2026-09-09 [categorias] ¿Cuál es la acción roja del árbol? -> ninguna; hay cinco crear/añadir y ninguno es la principal
- 2026-09-09 [categorias] Los ocho colores del gráfico vivían en Python -> pasan a tokens --serie-1..8, leídos del tema y repintados al cambiarlo
- 2026-09-09 [backup] ¿Qué pasa si se pulsa "Hacer backup" en modo demostración? -> se bloquea: escribiría la base de mentira sobre las copias reales
- 2026-09-09 [backup] ¿Dos botones rojos (Hacer backup y Restaurar)? -> son tokens distintos: --accent para la acción principal, --danger para la destructiva
