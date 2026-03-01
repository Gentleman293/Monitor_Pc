import sqlite3
import tkinter as tk

from collections import deque
from datetime import datetime

import setuptools
import GPUtil
import psutil


class MetricsRepository:
    """
    Слой работы с SQLite.

    Что сохраняем:
    - общие метрики (CPU, RAM, GPU load, GPU temp) в таблицу measurements;
    """

    def __init__(self, db_path: str = "monitor.db") -> None:
        """Инициализирует подключение к SQLite и подготавливает схему БД."""
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA synchronous=NORMAL;")
        self.create_schema()

    def create_schema(self) -> None:
        """Создаёт таблицу measurements, если она ещё не существует."""
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
        """Сохраняет один снимок метрик в таблицу measurements."""
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
        """Закрывает соединение с базой данных."""
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
        """Создаёт виджет графика метрики и подготавливает историю значений."""
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
        """Рисует сетку, подписи и оси графика (статичный слой)."""
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
                plot_left - 2,
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
        """Преобразует значение метрики в координату Y в пределах рабочей области."""
        value = max(self.y_min, min(self.y_max, value))
        normalized = (value - self.y_min) / (self.y_max - self.y_min)
        return bottom - normalized * (bottom - top)

    def draw_series(self) -> None:
        """Перерисовывает линию истории и маркер последней точки."""
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
        """Добавляет новое значение в историю и обновляет отображение графика."""
        self.history.append(value)

        if display_text is None:
            display_text = f"Текущее значение: {value:.1f}{self.unit}"

        self.value_var.set(display_text)
        self.draw_series()


class PcMonitorApp:
    """Мониторинг CPU/RAM/GPU + запись в файл SQLite monitor.db."""

    def __init__(self, root: tk.Tk) -> None:
        """Собирает интерфейс приложения и запускает цикл обновления метрик."""
        self.root = root
        self.root.title("PC Monitor (CPU/RAM/GPU + SQLite)")
        self.root.configure(bg="#111")
        self.adapt_window_to_resolution()
        self.content_frame = tk.Frame(self.root, bg="#111")
        self.content_frame.pack(fill="both", expand=True)

        self.repo = MetricsRepository(db_path="monitor.db")
        self.cpu_core_labels: list[tk.Label] = []
        self.cpu_details_visible = False

        self.header = tk.Label(
            self.content_frame,
            text="Мониторинг ПК: CPU / RAM / GPU (сохранение в SQLite)",
            font=("Segoe UI", 16, "bold"),
            fg="#f5f5f5",
            bg="#111",
        )
        self.header.pack(pady=(10, 8), anchor="w", padx=14)

        self.main_frame = tk.Frame(self.content_frame, bg="#111")
        self.main_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.left_column = tk.Frame(self.main_frame, bg="#111")
        self.left_column.pack(side="left", fill="y", anchor="n")

        self.right_column = tk.Frame(self.main_frame, bg="#111")
        self.right_column.pack(side="left", fill="y", padx=(14, 0), anchor="n")

        self.right_panels_row = tk.Frame(self.right_column, bg="#111")
        self.right_panels_row.pack(fill="x", anchor="n")

        self.charts_grid_frame = tk.Frame(self.left_column, bg="#111")
        self.charts_grid_frame.pack(fill="both", expand=True)
        self.charts_grid_frame.grid_columnconfigure(0, weight=1)
        self.charts_grid_frame.grid_columnconfigure(1, weight=1)

        self.cpu_chart = self.create_chart_cell(
            row=0,
            column=0,
            title="Загрузка процессора (CPU)",
            line_color="#2bd66f",
            unit="%",
        )
        self.ram_chart = self.create_chart_cell(
            row=0,
            column=1,
            title="Загруженность оперативной памяти (RAM)",
            line_color="#4da3ff",
            unit="%",
        )
        self.gpu_load_chart = self.create_chart_cell(
            row=1,
            column=0,
            title="Нагруженность видеокарты (GPU)",
            line_color="#ff4d8b",
            unit="%",
        )
        self.gpu_temp_chart = self.create_chart_cell(
            row=1,
            column=1,
            title="Температура видеокарты (GPU)",
            line_color="#ff8f3d",
            y_min=0,
            y_max=100,
            unit="°C",
        )

        self.cpu_details_button = tk.Button(
            self.left_column,
            text="Подробнее",
            command=self.toggle_cpu_details_panel,
            bg="#2b2b2b",
            fg="#f5f5f5",
            activebackground="#3a3a3a",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
        )
        self.cpu_details_button.pack(anchor="w", pady=(4, 10))

        self.threshold_config = {
            "cpu": {"title": "CPU", "unit": "%", "default": 90.0, "max": 100.0},
            "ram": {"title": "RAM", "unit": "%", "default": 90.0, "max": 100.0},
            "gpu_load": {
                "title": "GPU load",
                "unit": "%",
                "default": 90.0,
                "max": 100.0,
            },
            "gpu_temp": {
                "title": "GPU temp",
                "unit": "°C",
                "default": 85.0,
                "max": 120.0,
            },
        }
        self.threshold_values = {
            key: float(config["default"])
            for key, config in self.threshold_config.items()
        }
        self.threshold_entries: dict[str, tk.Entry] = {}
        self.last_metrics: dict[str, float | None] = {
            "cpu": None,
            "ram": None,
            "gpu_load": None,
            "gpu_temp": None,
        }
        self.build_threshold_controls()

        self.info_label = tk.Label(
            self.content_frame,
            text=("Данные сохраняются в monitor.db: measurements (CPU/RAM/GPU)."),
            font=("Segoe UI", 10),
            fg="#cfcfcf",
            bg="#111",
            anchor="w",
        )
        self.info_label.pack(fill="x", padx=14, pady=(0, 10))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_all_metrics()

    def create_chart_cell(
        self,
        row: int,
        column: int,
        title: str,
        line_color: str,
        y_min: float = 0.0,
        y_max: float = 100.0,
        unit: str = "%",
    ) -> MetricChart:
        """Создаёт ячейку сетки и размещает в ней график метрики."""
        cell = tk.Frame(self.charts_grid_frame, bg="#111")
        cell.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")

        chart = MetricChart(
            parent=cell,
            title=title,
            line_color=line_color,
            width=360,
            height=130,
            padding=32,
            max_points=80,
            y_min=y_min,
            y_max=y_max,
            unit=unit,
        )
        return chart



    def adapt_window_to_resolution(self) -> None:
        """Подбирает размер окна под текущее разрешение монитора и центрирует его."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        target_width = min(1280, max(900, int(screen_width * 0.85)))
        target_height = min(900, max(680, int(screen_height * 0.85)))

        self.root.minsize(900, 680)

        pos_x = max((screen_width - target_width) // 2, 0)
        pos_y = max((screen_height - target_height) // 2, 0)
        self.root.geometry(f"{target_width}x{target_height}+{pos_x}+{pos_y}")

    def build_threshold_controls(self) -> None:
        """Создаёт панель ввода пороговых значений и блок предупреждений."""
        controls_frame = tk.Frame(self.right_panels_row, bg="#1a1a1a", padx=12, pady=12)
        controls_frame.pack(side="left", fill="y")
        self.threshold_controls_frame = controls_frame

        title_label = tk.Label(
            controls_frame,
            text="Критические пороги",
            font=("Segoe UI", 12, "bold"),
            fg="#f5f5f5",
            bg="#1a1a1a",
            anchor="w",
        )
        title_label.pack(fill="x", pady=(0, 6))

        subtitle_label = tk.Label(
            controls_frame,
            text="Если значение выше порога, появится предупреждение.",
            font=("Segoe UI", 9),
            fg="#bdbdbd",
            bg="#1a1a1a",
            anchor="w",
            justify="left",
            wraplength=250,
        )
        subtitle_label.pack(fill="x", pady=(0, 8))

        for key, config in self.threshold_config.items():
            row = tk.Frame(controls_frame, bg="#1a1a1a")
            row.pack(fill="x", pady=2)

            label = tk.Label(
                row,
                text=f"{config['title']} ({config['unit']}):",
                font=("Segoe UI", 10),
                fg="#e0e0e0",
                bg="#1a1a1a",
                anchor="w",
                width=16,
            )
            label.pack(side="left")

            entry = tk.Entry(row, width=8, font=("Segoe UI", 10))
            entry.insert(0, str(config["default"]))
            entry.bind("<Return>", lambda _event: self.apply_thresholds())
            entry.pack(side="left", padx=(6, 0))
            self.threshold_entries[key] = entry

        self.threshold_status_var = tk.StringVar(
            value="Пороги установлены по умолчанию."
        )
        status_label = tk.Label(
            controls_frame,
            textvariable=self.threshold_status_var,
            font=("Segoe UI", 9),
            fg="#cfcfcf",
            bg="#1a1a1a",
            anchor="w",
        )
        status_label.pack(fill="x", pady=(8, 6))

        apply_button = tk.Button(
            controls_frame,
            text="Применить пороги",
            command=self.apply_thresholds,
            bg="#2b2b2b",
            fg="#f5f5f5",
            activebackground="#3a3a3a",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
        )
        apply_button.pack(anchor="w")

        self.warning_var = tk.StringVar(value="Предупреждений нет.")
        self.warning_label = tk.Label(
            self.right_column,
            textvariable=self.warning_var,
            font=("Segoe UI", 10, "bold"),
            fg="#58c46b",
            bg="#111",
            justify="left",
            anchor="w",
            wraplength=290,
        )
        self.warning_label.pack(fill="x", pady=(8, 0))

    def apply_thresholds(self) -> None:
        """Проверяет и применяет пороги из полей ввода."""
        updated_values: dict[str, float] = {}

        for key, entry in self.threshold_entries.items():
            raw_value = entry.get().strip().replace(",", ".")
            try:
                parsed_value = float(raw_value)
            except ValueError:
                self.threshold_status_var.set(
                    f"Ошибка: некорректное значение для {self.threshold_config[key]['title']}."
                )
                return

            max_allowed = self.threshold_config[key]["max"]
            if parsed_value < 0 or parsed_value > max_allowed:
                self.threshold_status_var.set(
                    "Ошибка: порог для "
                    f"{self.threshold_config[key]['title']} должен быть в диапазоне 0..{max_allowed:.0f}."
                )
                return

            updated_values[key] = parsed_value

        self.threshold_values = updated_values
        self.threshold_status_var.set("Новые пороги успешно применены.")

        if (
            self.last_metrics["cpu"] is not None
            and self.last_metrics["ram"] is not None
        ):
            self.evaluate_threshold_warnings(
                cpu_percent=float(self.last_metrics["cpu"]),
                ram_percent=float(self.last_metrics["ram"]),
                gpu_load_percent=self.last_metrics["gpu_load"],
                gpu_temp_c=self.last_metrics["gpu_temp"],
            )

    def build_cpu_details_panel(self) -> None:
        """Создаёт встроенную панель с нагрузкой по каждому логическому ядру CPU."""
        self.cpu_details_frame = tk.Frame(
            self.right_panels_row, bg="#1a1a1a", padx=12, pady=12
        )

        title_label = tk.Label(
            self.cpu_details_frame,
            text="Загрузка каждого ядра CPU",
            font=("Segoe UI", 12, "bold"),
            fg="#f5f5f5",
            bg="#1a1a1a",
            anchor="w",
        )
        title_label.pack(fill="x", pady=(0, 8))

        self.cpu_core_labels = []
        core_count = psutil.cpu_count(logical=True) or 0
        for core_index in range(core_count):
            core_label = tk.Label(
                self.cpu_details_frame,
                text=f"Ядро {core_index + 1}: 0.0%",
                font=("Segoe UI", 10),
                fg="#cfcfcf",
                bg="#1a1a1a",
                anchor="w",
                width=22,
            )
            core_label.pack(fill="x", pady=2)
            self.cpu_core_labels.append(core_label)

    def toggle_cpu_details_panel(self) -> None:
        """Переключает видимость панели детальной загрузки CPU."""
        if self.cpu_details_visible:
            self.hide_cpu_details_panel()
        else:
            self.show_cpu_details_panel()

    def show_cpu_details_panel(self) -> None:
        """Показывает панель CPU-деталей и сдвигает блок порогов вправо."""
        if not hasattr(self, "cpu_details_frame"):
            self.build_cpu_details_panel()

        self.cpu_details_frame.pack(side="left", fill="y", padx=(0, 10))
        self.threshold_controls_frame.pack_forget()
        self.threshold_controls_frame.pack(side="left", fill="y")

        self.cpu_details_visible = True
        self.cpu_details_button.configure(text="Скрыть подробности")
        self.update_cpu_details_panel()

    def hide_cpu_details_panel(self) -> None:
        """Скрывает панель CPU-деталей и возвращает блок порогов на место."""
        if hasattr(self, "cpu_details_frame"):
            self.cpu_details_frame.pack_forget()

        self.threshold_controls_frame.pack_forget()
        self.threshold_controls_frame.pack(side="left", fill="y")

        self.cpu_details_visible = False
        self.cpu_details_button.configure(text="Подробнее")

    def update_cpu_details_panel(self) -> None:
        """Обновляет проценты загрузки по ядрам (раз в секунду при видимой панели)."""
        if not self.cpu_details_visible:
            return

        per_core_values = psutil.cpu_percent(interval=None, percpu=True)
        for index, label in enumerate(self.cpu_core_labels):
            value = per_core_values[index] if index < len(per_core_values) else 0.0
            label.configure(text=f"Ядро {index + 1}: {value:.1f}%")

        self.root.after(1000, self.update_cpu_details_panel)

    def evaluate_threshold_warnings(
        self,
        cpu_percent: float,
        ram_percent: float,
        gpu_load_percent: float | None,
        gpu_temp_c: float | None,
    ) -> None:
        """Сравнивает текущие метрики с порогами и обновляет текст предупреждений."""
        warnings = []

        if cpu_percent >= self.threshold_values["cpu"]:
            warnings.append(
                f"CPU: {cpu_percent:.1f}% (порог {self.threshold_values['cpu']:.1f}%)"
            )

        if ram_percent >= self.threshold_values["ram"]:
            warnings.append(
                f"RAM: {ram_percent:.1f}% (порог {self.threshold_values['ram']:.1f}%)"
            )

        if (
            gpu_load_percent is not None
            and gpu_load_percent >= self.threshold_values["gpu_load"]
        ):
            warnings.append(
                "GPU load: "
                f"{gpu_load_percent:.1f}% (порог {self.threshold_values['gpu_load']:.1f}%)"
            )

        if gpu_temp_c is not None and gpu_temp_c >= self.threshold_values["gpu_temp"]:
            warnings.append(
                f"GPU temp: {gpu_temp_c:.1f}°C (порог {self.threshold_values['gpu_temp']:.1f}°C)"
            )

        if warnings:
            self.warning_var.set(
                "⚠ Превышены критические уровни:\n" + "\n".join(warnings)
            )
            self.warning_label.configure(fg="#ff5a5a")
        else:
            self.warning_var.set("Предупреждений нет.")
            self.warning_label.configure(fg="#58c46b")

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
        """Считывает метрики, обновляет графики, пишет данные в БД и планирует следующий цикл."""
        captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cpu_percent = psutil.cpu_percent(interval=None)
        ram_percent = psutil.virtual_memory().percent
        gpu_load_percent, gpu_temp_c = self.read_gpu_metrics()

        self.cpu_chart.update_value(
            cpu_percent, f"Текущая загрузка CPU: {cpu_percent:.1f}%"
        )
        self.ram_chart.update_value(
            ram_percent, f"Текущая загрузка RAM: {ram_percent:.1f}%"
        )

        if gpu_load_percent is None:
            self.gpu_load_chart.update_value(
                0.0, "GPU load: N/A (видеокарта не обнаружена)"
            )
        else:
            self.gpu_load_chart.update_value(
                gpu_load_percent, f"Текущая загрузка GPU: {gpu_load_percent:.1f}%"
            )

        if gpu_temp_c is None:
            self.gpu_temp_chart.update_value(0.0, "GPU temp: N/A")
        else:
            self.gpu_temp_chart.update_value(
                gpu_temp_c, f"Текущая температура GPU: {gpu_temp_c:.1f}°C"
            )

        self.repo.insert_measurement(
            captured_at=captured_at,
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            gpu_load_percent=gpu_load_percent,
            gpu_temp_c=gpu_temp_c,
        )

        self.last_metrics = {
            "cpu": cpu_percent,
            "ram": ram_percent,
            "gpu_load": gpu_load_percent,
            "gpu_temp": gpu_temp_c,
        }

        self.evaluate_threshold_warnings(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            gpu_load_percent=gpu_load_percent,
            gpu_temp_c=gpu_temp_c,
        )

        self.root.after(2000, self.update_all_metrics)

    def on_close(self) -> None:
        """Корректно завершает приложение и освобождает ресурсы."""
        self.repo.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PcMonitorApp(root)
    root.mainloop()
