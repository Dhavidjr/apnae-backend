"""
Generates PNG graphs from sensor readings using matplotlib (Agg backend,
so it works headlessly on a server with no display).
"""
import io
from typing import List, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.models import SensorReading  # noqa: E402

Metric = Literal["body_temperature", "heart_rate", "spo2", "heart_beat_height", "all"]

METRIC_LABELS = {
    "body_temperature": ("Body Temperature", "°C"),
    "heart_rate": ("Heart Rate", "bpm"),
    "spo2": ("SpO2", "%"),
    "heart_beat_height": ("Heart Beat Height (accelerometer)", "a.u."),
}


def plot_readings(readings: List[SensorReading], metric: Metric, device_label: str) -> io.BytesIO:
    """Builds a PNG plot for the given metric ('all' -> 4 stacked subplots)."""
    timestamps = [r.recorded_at for r in readings]

    if not readings:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "No data available for the requested range", ha="center", va="center")
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    if metric == "all":
        metrics = list(METRIC_LABELS.keys())
        fig, axes = plt.subplots(len(metrics), 1, figsize=(11, 10), sharex=True)
        fig.suptitle(f"Sensor Readings - {device_label}", fontsize=14)
        for ax, m in zip(axes, metrics):
            values = [getattr(r, m) for r in readings]
            label, unit = METRIC_LABELS[m]
            ax.plot(timestamps, values, marker=".", linewidth=1)
            ax.set_ylabel(f"{label}\n({unit})", fontsize=9)
            ax.grid(True, alpha=0.3)
        axes[-1].set_xlabel("Time")
        fig.autofmt_xdate()
    else:
        label, unit = METRIC_LABELS[metric]
        values = [getattr(r, metric) for r in readings]
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(timestamps, values, marker=".", linewidth=1.2, color="#1f77b4")
        ax.set_title(f"{label} - {device_label}")
        ax.set_xlabel("Time")
        ax.set_ylabel(f"{label} ({unit})")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf
