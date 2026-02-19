from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def plot_curve(
    df_curve,
    x_col: str = "Dias al VTO",
    y_col: str = "TNA %",
    label_col: str = "Especie",
    title: str | None = None,
    x_unit: str = "years",  # "years" o "days"
    annotate: bool = True,
    max_labels: int = 30,
):
    """Grafica curva (TNA % vs tiempo) con una curva teórica logarítmica y coloreo:
    - Verde: bono sobre la curva teórica
    - Rojo: bono bajo la curva teórica

    Notas:
    - x_col se espera en días (recomendado). Si x_unit == "years" se convierte.
    - annotate: muestra labels (si hay pocos puntos, evita caos).
    """
    df = df_curve.copy()

    # Limpiar x/y
    x = np.array(df[x_col], dtype=float)
    y = np.array(df[y_col], dtype=float)

    # Convertir unidades (solo para el eje)
    if x_unit == "years":
        x_plot = x / 365.0
        x_label = "Años al Vencimiento"
    elif x_unit == "months":
        x_plot = x / 30.4375  # meses promedio (365.25/12)
        x_label = "Meses al Vencimiento"
    else:
        x_plot = x
        x_label = "Días al Vencimiento"

    # Filtrar NaNs / inf
    ok = np.isfinite(x_plot) & np.isfinite(y) & (x_plot > 0)
    x_ok = x_plot[ok]
    y_ok = y[ok]

    labels_ok = None
    if label_col in df.columns:
        labels_ok = df.loc[ok, label_col].astype(str).tolist()

    # Orden por X
    order = np.argsort(x_ok)
    x_ok = x_ok[order]
    y_ok = y_ok[order]
    if labels_ok is not None:
        labels_ok = [labels_ok[i] for i in order]

    # --- Ajuste logarítmico (suave) ---
    # Modelo: y = a + b * log(x)
    y_hat = None
    xx = None
    yy = None
    if len(x_ok) >= 3:
        x_safe = np.clip(x_ok, 1e-6, None)
        coeffs = np.polyfit(np.log(x_safe), y_ok, deg=1)
        y_hat = np.polyval(coeffs, np.log(x_safe))

        xx = np.linspace(x_ok.min(), x_ok.max(), 250)
        yy = np.polyval(coeffs, np.log(np.clip(xx, 1e-6, None)))

    # --- Plot ---
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(11, 5))

    if y_hat is not None:
        above = y_ok >= y_hat
        below = ~above

        ax.scatter(x_ok[above], y_ok[above], color="lime", label="Sobre la curva")
        ax.scatter(x_ok[below], y_ok[below], color="red", label="Bajo la curva")

        ax.plot(xx, yy, color="white", linewidth=2, label="Curva teórica")
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),  # fuera del gráfico (derecha)
            borderaxespad=0.0,
            framealpha=0.2,
        )
    else:
        ax.scatter(x_ok, y_ok)

    # Etiquetas (priorizar puntos importantes + evitar superposición)
    if annotate and labels_ok is not None and len(labels_ok) > 0:
        n = len(labels_ok)
        idx_all = np.arange(n)

        # 1) Prioridad: extremos de X (plazo)
        i_minx = int(np.nanargmin(x_ok))
        i_maxx = int(np.nanargmax(x_ok))

        selected = {i_minx, i_maxx}

        # 2) Prioridad: outliers vs curva (si existe curva)
        if y_hat is not None and len(y_hat) == n:
            resid = y_ok - y_hat  # + arriba / - abajo
            # top outliers arriba y abajo
            k_out = max(2, min(6, max_labels // 3))
            top_above = idx_all[np.argsort(resid)[-k_out:]]   # más positivos
            top_below = idx_all[np.argsort(resid)[:k_out]]    # más negativos
            selected.update(map(int, top_above))
            selected.update(map(int, top_below))

        # 3) Completar con puntos “parejos” en X hasta max_labels
        # Ordenamos por X y tomamos un muestreo uniforme
        order_x = idx_all[np.argsort(x_ok)]
        need = max_labels - len(selected)
        if need > 0:
            take = np.linspace(0, n - 1, min(need, n)).astype(int)
            selected.update(map(int, order_x[take]))

        # Si todavía sobran, recortamos
        selected = list(selected)
        # Orden final por X (queda más “limpio”)
        selected = sorted(selected, key=lambda i: x_ok[i])

        # Anti-superposición: no etiquetar si están muy pegados en X
        x_span = float(np.nanmax(x_ok) - np.nanmin(x_ok)) if n > 1 else 0.0
        min_dx = (x_span / max_labels) * 0.35 if x_span > 0 else 0.0  # menos agresivo

        last_x = None
        flip = 1
        shown = 0

        for i in selected:
            if shown >= max_labels:
                break

            xi, yi, lab = x_ok[i], y_ok[i], labels_ok[i]

            if last_x is not None and min_dx > 0 and abs(xi - last_x) < min_dx:
                continue

            y_off = 10 * flip
            flip *= -1

            ax.annotate(
                lab,
                (xi, yi),
                textcoords="offset points",
                xytext=(6, y_off),
                fontsize=9,
                alpha=0.9,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.35, edgecolor="none"),
            )

            last_x = xi
            shown += 1

    ax.set_xlabel(x_label)
    ax.set_ylabel("TNA %")
    if title:
        ax.set_title(title)

    ax.grid(True, alpha=0.25)

    if x_unit == "years":
        ax.xaxis.set_major_locator(MultipleLocator(1))
        ax.xaxis.set_minor_locator(MultipleLocator(0.5))
    elif x_unit == "months":
        # ticks "humanos" para corto plazo
        # si el rango llega hasta 12 meses: cada 1 mes; si no: cada 3 meses
        max_m = float(np.nanmax(x_ok)) if len(x_ok) else 0.0
        major = 1 if max_m <= 12 else 3
        minor = 0.5 if major == 1 else 1
        ax.xaxis.set_major_locator(MultipleLocator(major))
        ax.xaxis.set_minor_locator(MultipleLocator(minor))

    fig.tight_layout()
    return fig
