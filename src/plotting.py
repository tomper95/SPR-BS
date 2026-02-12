import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def plot_curve(
    df_curve,
    x_col="Dias al VTO",
    y_col="TNA %",
    label_col="Especie",
    title: str | None = None,
    x_unit: str = "years",  # "years" o "days"
):
    plt.style.use("dark_background")

    x = df_curve[x_col].astype(float).values
    y = df_curve[y_col].astype(float).values
    labels = df_curve[label_col].astype(str).values

    # =========================
    # Convertir eje X (días -> años)
    # =========================
    if x_unit == "years":
        x = x / 365.0
        x_label = "Años al Vencimiento"
        x_major = 1.0   # 1 año
        x_minor = 0.5   # 6 meses
    else:
        x_label = x_col
        x_major = 30.0  # 30 días
        x_minor = 15.0  # 15 días

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    # =========================
    # Ticks del eje X
    # =========================
    ax.xaxis.set_major_locator(MultipleLocator(x_major))
    ax.xaxis.set_minor_locator(MultipleLocator(x_minor))

    ax.tick_params(axis="x", which="major", length=6)
    ax.tick_params(axis="x", which="minor", length=3)

    ax.grid(True, axis="x", which="major", linestyle="--", alpha=0.25)
    ax.grid(True, axis="y", which="major", alpha=0.25)

    # ===== curva de tendencia =====
    mask = np.isfinite(x) & np.isfinite(y)
    x_ok, y_ok = x[mask], y[mask]
    labels_ok = labels[mask]

    if len(x_ok) >= 2:
        # =========================
        # Ajuste log suave: y = a*ln(1+x) + b
        # - funciona bien con mezcla de plazos cortos/largos
        # - evita problemas cerca de 0 usando ln(1+x)
        # =========================
        x_fit = np.log1p(np.clip(x_ok, 0, None))  # ln(1+x), con x>=0
        a, b = np.polyfit(x_fit, y_ok, 1)

        x_line = np.linspace(max(0.0, x_ok.min()), x_ok.max(), 200)
        y_line = a * np.log1p(x_line) + b
        ax.plot(x_line, y_line, color="white", linewidth=2, alpha=0.8, label="Curva teórica (log)")

        y_teorica = a * np.log1p(x_ok) + b
        above = y_ok >= y_teorica
        below = ~above

        ax.scatter(x_ok[above], y_ok[above], color="#00ff88", s=70, edgecolors="black", label="Sobre la curva")
        ax.scatter(x_ok[below], y_ok[below], color="#ff5555", s=70, edgecolors="black", label="Bajo la curva")

        for xi, yi, lab in zip(x_ok, y_ok, labels_ok):
            ax.annotate(lab, (xi, yi), textcoords="offset points", xytext=(6, 4), fontsize=9, alpha=0.9)
    else:
        ax.scatter(x, y, s=70, edgecolors="black")

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_col)

    if title is None:
        title = f"Curva de Bonos ({y_col} vs {x_label})"
    ax.set_title(title)
    ax.legend()

    return fig