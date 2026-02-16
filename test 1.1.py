import sqlite3
import tkinter as tk
from collections import deque
from datetime import datetime

import GPUtil
import psutil


class MetricsRepository:
    """
    Слой работы с SQLite.

    Что сохраняем:
    - общие метрики (CPU, RAM, GPU load, GPU temp) в таблицу measurements;
        """

    def __init__(self, db_path: str = "monitor.db") -> None:
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA synchronous=NORMAL;")
        self.create_schema()

    def create_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                cpu_percent REAL NOT NULL,
                ram_percent REAL NOT NULL,
                gpu_load_percent REAL,
                gpu_temp_c REAL
            )
            """
        )

        self.connection.commit()

    def insert_measurement(
        self,
        captured_at: str,
        cpu_percent: float,
        ram_percent: float,
        gpu_load_percent: float | None,
        gpu_temp_c: float | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO measurements (
                captured_at, cpu_percent, ram_percent, gpu_load_percent, gpu_temp_c
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (captured_at, cpu_percent, ram_percent, gpu_load_percent, gpu_temp_c),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class MetricChart:
    """Универсальный Canvas-график одной метрики."""

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        line_color: str,
        width: int = 520,
        height: int = 150,
        padding: int = 40,
        max_points: int = 90,
        y_min: float = 0.0,
        y_max: float = 100.0,
        unit: str = "%",
    ) -> None:
        self.width = width
        self.height = height
        self.padding = padding
        self.max_points = max_points
        self.y_min = y_min
        self.y_max = y_max
        self.unit = unit

        self.history = deque([0.0] * self.max_points, maxlen=self.max_points)

        self.frame = tk.Frame(parent, bg="#111")
        self.frame.pack(fill="x", pady=(0, 10))

        self.title_label = tk.Label(
            self.frame,
            text=title,
            font=("Segoe UI", 11, "bold"),
            fg="#f5f5f5",
            bg="#111",
            anchor="w",
        )
        self.title_label.pack(fill="x")

        self.value_var = tk.StringVar(value=f"Текущее значение: 0.0{self.unit}")
        self.value_label = tk.Label(
            self.frame,
            textvariable=self.value_var,
            font=("Segoe UI", 10),
            fg="#cfcfcf",
            bg="#111",
            anchor="w",
        )
        self.value_label.pack(fill="x", pady=(0, 4))

        self.canvas = tk.Canvas(
            self.frame,
            width=self.width,
            height=self.height,
            bg="#1c1c1c",
            highlightthickness=1,
            highlightbackground="#333",
        )
        self.canvas.pack()

        self.line_color = line_color
        self.point_color = "#b2ffd0"

        self.draw_static_grid()
        self.draw_series()

    def draw_static_grid(self) -> None:
        self.canvas.delete("grid")
        self.canvas.delete("axes")
        self.canvas.delete("labels")

        plot_left = self.padding
        plot_top = self.padding / 2
        plot_right = self.width - self.padding / 2
        plot_bottom = self.height - self.padding

        steps = 5
        step_value = (self.y_max - self.y_min) / steps if steps else 1

        for i in range(steps + 1):
            value = self.y_min + i * step_value
            y = self.value_to_y(value, plot_top, plot_bottom)

            self.canvas.create_line(
                plot_left,
                y,
                plot_right,
                y,
                fill="#2e2e2e",
                dash=(2, 4),
                tags="grid",
            )

            self.canvas.create_text(
                plot_left - 12,
                y,
                text=f"{value:.0f}{self.unit}",
                anchor="e",
                fill="#9a9a9a",
                font=("Segoe UI", 9),
                tags="labels",
            )

        self.canvas.create_line(
            plot_left,
            plot_top,
            plot_left,
            plot_bottom,
            fill="#8a8a8a",
            width=2,
            tags="axes",
        )

        self.canvas.create_line(
            plot_left,
            plot_bottom,
            plot_right,
            plot_bottom,
            fill="#8a8a8a",
            width=2,
            tags="axes",
        )

    def value_to_y(self, value: float, top: float, bottom: float) -> float:
        value = max(self.y_min, min(self.y_max, value))
        normalized = (value - self.y_min) / (self.y_max - self.y_min)
        return bottom - normalized * (bottom - top)

    def draw_series(self) -> None:
        self.canvas.delete("series")

        plot_left = self.padding
        plot_top = self.padding / 2
        plot_right = self.width - self.padding / 2
        plot_bottom = self.height - self.padding

        if len(self.history) < 2:
            return

        step_x = (plot_right - plot_left) / (self.max_points - 1)
        points = []

        for i, value in enumerate(self.history):
            x = plot_left + i * step_x
            y = self.value_to_y(value, plot_top, plot_bottom)
            points.extend((x, y))

        self.canvas.create_line(
            *points,
            fill=self.line_color,
            width=2,
            smooth=True,
            tags="series",
        )

        last_x, last_y = points[-2], points[-1]
        self.canvas.create_oval(
            last_x - 3,
            last_y - 3,
            last_x + 3,
            last_y + 3,
            fill=self.point_color,
            outline="",
            tags="series",
        )

    def update_value(self, value: float, display_text: str | None = None) -> None:
        self.history.append(value)

        if display_text is None:
            display_text = f"Текущее значение: {value:.1f}{self.unit}"

        self.value_var.set(display_text)
        self.draw_series()


class PcMonitorApp:
    """Мониторинг CPU/RAM/GPU + запись в файл SQLite monitor.db."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PC Monitor (CPU/RAM/GPU + SQLite)")
        self.root.geometry("900x760")
        self.root.configure(bg="#111")

        self.repo = MetricsRepository(db_path="monitor.db")

        self.header = tk.Label(
            root,
            text="Мониторинг ПК: CPU / RAM / GPU (сохранение в SQLite)",
            font=("Segoe UI", 16, "bold"),
            fg="#f5f5f5",
            bg="#111",
        )
        self.header.pack(pady=(10, 8), anchor="w", padx=14)

        self.main_frame = tk.Frame(root, bg="#111")
        self.main_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.left_column = tk.Frame(self.main_frame, bg="#111")
        self.left_column.pack(side="left", fill="y", anchor="n")

        self.cpu_chart = MetricChart(
            parent=self.left_column,
            title="Загрузка процессора (CPU)",
            line_color="#2bd66f",
            unit="%",
        )
        self.ram_chart = MetricChart(
            parent=self.left_column,
            title="Загруженность оперативной памяти (RAM)",
            line_color="#4da3ff",
            unit="%",
        )
        self.gpu_load_chart = MetricChart(
            parent=self.left_column,
            title="Нагруженность видеокарты (GPU)",
            line_color="#ff4d8b",
            unit="%",
        )
        self.gpu_temp_chart = MetricChart(
            parent=self.left_column,
            title="Температура видеокарты (GPU)",
            line_color="#ff8f3d",
            y_min=0,
            y_max=120,
            unit="°C",
        )

        self.info_label = tk.Label(
            root,
            text=(
                "Данные сохраняются в monitor.db: measurements (CPU/RAM/GPU)."
            ),
            font=("Segoe UI", 10),
            fg="#cfcfcf",
            bg="#111",
            anchor="w",
        )
        self.info_label.pack(fill="x", padx=14, pady=(0, 10))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_all_metrics()

    @staticmethod
    def read_gpu_metrics() -> tuple[float | None, float | None]:
        """Читаем первую доступную GPU через GPUtil: (load%, tempC)."""
        try:
            gpus = GPUtil.getGPUs()
        except Exception:
            return None, None

        if not gpus:
            return None, None

        gpu = gpus[0]
        load_percent = float(gpu.load * 100.0)
        temp_c = float(gpu.temperature) if gpu.temperature is not None else None
        return load_percent, temp_c

    def update_all_metrics(self) -> None:
        captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cpu_percent = psutil.cpu_percent(interval=None)
        ram_percent = psutil.virtual_memory().percent
        gpu_load_percent, gpu_temp_c = self.read_gpu_metrics()

        self.cpu_chart.update_value(cpu_percent, f"Текущая загрузка CPU: {cpu_percent:.1f}%")
        self.ram_chart.update_value(ram_percent, f"Текущая загрузка RAM: {ram_percent:.1f}%")

        if gpu_load_percent is None:
            self.gpu_load_chart.update_value(0.0, "GPU load: N/A (видеокарта не обнаружена)")
        else:
            self.gpu_load_chart.update_value(gpu_load_percent, f"Текущая загрузка GPU: {gpu_load_percent:.1f}%")

        if gpu_temp_c is None:
            self.gpu_temp_chart.update_value(0.0, "GPU temp: N/A")
        else:
            self.gpu_temp_chart.update_value(gpu_temp_c, f"Текущая температура GPU: {gpu_temp_c:.1f}°C")

        self.repo.insert_measurement(
            captured_at=captured_at,
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            gpu_load_percent=gpu_load_percent,
            gpu_temp_c=gpu_temp_c,
        )

        self.root.after(1000, self.update_all_metrics)

    def on_close(self) -> None:
        self.repo.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PcMonitorApp(root)
    root.mainloop()
