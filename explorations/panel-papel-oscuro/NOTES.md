# Panel · Papel en oscuro — parejas tipográficas

Segundo boceto de Fase 0. La dirección ya está decidida (papel, en oscuro); aquí solo se
elige la tipografía. Mismo maquetado en las cuatro pestañas: lo único que cambia es qué
familia lleva cada cosa. Teclas 1-5, y `f` para alternar el fondo cálido/neutro.

| | Titulares | Cifras | Qué se gana | Qué se pierde |
|---|---|---|---|---|
| A · Georgia | Georgia | Georgia | carácter; las cifras de estilo antiguo dan calidez editorial | menos precisión al escanear una tabla larga |
| B · Noto Serif | Noto Serif | Noto Serif | altura de x mayor, aguanta mejor en cuerpos pequeños y en oscuro | más neutra, menos personalidad |
| C · Serif + sans | Georgia | sans tabular | el hero conserva el carácter y la tabla se lee fría y exacta | dos voces en la misma pantalla |
| D · Serif + mono | Georgia | monoespaciada | alineación perfecta de importes, aire técnico | se acerca al cuadro de mandos, se aleja del papel |
| E · Serif salvo la tabla | Georgia | Georgia en hero y KPI, sans tabular en tablas y categorías | el carácter se queda donde se mira despacio y la precisión donde se compara deprisa | hay que respetar la frontera: si una cifra de tabla se pone en serif, se rompe |

Georgia está instalada en esta máquina (`Georgia.ttf`), así que se ve tal cual. En una
máquina sin ella el stack cae a Noto Serif, que es la pareja B: por eso conviene que la B
también resulte aceptable.

Cero fuentes web en las cuatro, según `design-system.md`.

## Fondo

- **Cálido** `#131110`: negro con una pizca de marrón; refuerza lo de "papel".
- **Neutro** `#0d0d0d`: el negro que TNT ya usa hoy.

## Decisión

- Pareja elegida (2026-09-08): **E · serif salvo la tabla**. Georgia en el hero, los
  titulares de sección y los tres KPI; sans tabular en las cifras de tabla y de categoría.
  La frontera es la regla: serif donde se mira despacio, sans donde se compara deprisa.
- Fondo elegido: **neutro** `#0d0d0d`, el negro que TNT ya usa. Nada de virar a cálido.
- Consecuencia para `tnt.css`: `--font-display` deja de ser Impact y pasa a
  `Georgia, "Noto Serif", serif`; hay que decidir qué pasa con la marca del topbar.
