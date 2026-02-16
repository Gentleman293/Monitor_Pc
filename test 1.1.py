'''import tkinter 
import GPUtil
import psutil
import pyqtgraph
import PyQt5
import setuptools
import queue
import threading
import time

root = tkinter.Tk()
root.title("Monitor GPU Usage")
root.geometry("1920x1080")




root.mainloop()'''

import tkinter as tk
from collections import deque

import psutil


class CpuChartApp:
    """
    Небольшое учебное приложение для мониторинга загрузки CPU.

    Что делает класс:
    1) Создаёт окно и элементы интерфейса (заголовок, текст с текущим %, Canvas).
    2) Рисует статичные элементы графика: оси и сетку.
    3) Хранит историю значений загрузки процессора.
    4) Раз в секунду получает новый показатель CPU и перерисовывает линию графика.
    """

    def __init__(self, root: tk.Tk) -> None:
        # Сохраняем ссылку на главное окно, чтобы дальше планировать обновления через root.after(...)
        self.root = root

        # Базовая настройка окна
        self.root.title("CPU Monitor (Tkinter Canvas)")
        self.root.geometry("1280x720")
        self.root.configure(bg="#111")

        # Параметры области графика
        self.width = 900
        self.height = 300
        self.padding = 40

        # max_points — сколько последних измерений держим в памяти и показываем на графике
        # Например 120 точек при обновлении 1 раз/сек ≈ история за 2 минуты
        self.max_points = 120

        # deque с фиксированной длиной автоматически удаляет самые старые значения
        # Это удобно для «скользящего окна» графика
        self.history = deque([0.0] * self.max_points, maxlen=self.max_points)

        # --- Верхняя часть интерфейса: заголовок и текст с текущей загрузкой ---
        self.title_label = tk.Label(
            root,
            text="Загрузка процессора (CPU)",
            font=("Segoe UI", 18, "bold"),
            fg="#f5f5f5",
            bg="#111",
        )
        self.title_label.pack(pady=(15, 5))

        # StringVar удобно тем, что можно менять текст без пересоздания Label
        self.value_var = tk.StringVar(value="Текущая загрузка: 0.0%")
        self.value_label = tk.Label(
            root,
            textvariable=self.value_var,
            font=("Segoe UI", 12),
            fg="#d0d0d0",
            bg="#111",
        )
        self.value_label.pack(pady=(0, 10))

        # --- Canvas: область, где рисуем диаграмму ---
        self.canvas = tk.Canvas(
            root,
            width=self.width,
            height=self.height,
            bg="#1c1c1c",
            highlightthickness=1,
            highlightbackground="#333",
        )
        self.canvas.pack(pady=10)

        # Сначала один раз рисуем статичные элементы (сетка, оси)
        self.draw_static_grid()

        # Запускаем бесконечный цикл обновления графика (через планировщик Tkinter)
        self.update_chart()

    def draw_static_grid(self) -> None:
        """Рисуем оси и сетку, которые не меняются каждый кадр."""

        # На случай перерисовки удаляем старые версии статичных элементов по тегам
        self.canvas.delete("grid")
        self.canvas.delete("axes")
        self.canvas.delete("labels")

        # Границы полезной области графика (внутри Canvas)
        plot_left = self.padding
        plot_top = self.padding / 2
        plot_right = self.width - self.padding / 2
        plot_bottom = self.height - self.padding

        # Горизонтальные линии сетки и подписи шкалы по Y: 0%, 20%, ... 100%
        for value in range(0, 101, 20):
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
                text=f"{value}%",
                anchor="e",
                fill="#9a9a9a",
                font=("Segoe UI", 9),
                tags="labels",
            )

        # Ось Y
        self.canvas.create_line(
            plot_left,
            plot_top,
            plot_left,
            plot_bottom,
            fill="#8a8a8a",
            width=2,
            tags="axes",
        )

        # Ось X
        self.canvas.create_line(
            plot_left,
            plot_bottom,
            plot_right,
            plot_bottom,
            fill="#8a8a8a",
            width=2,
            tags="axes",
        )

        # Подпись времени на оси X
        self.canvas.create_text(
            plot_right,
            plot_bottom + 16,
            text="Время →",
            anchor="e",
            fill="#9a9a9a",
            font=("Segoe UI", 9),
            tags="labels",
        )

    @staticmethod
    def value_to_y(value: float, top: float, bottom: float) -> float:
        """
        Преобразует значение загрузки CPU (0..100) в координату Y на Canvas.

        Важно: в Canvas ось Y направлена вниз,
        поэтому 0% должно быть внизу, а 100% — вверху.
        """
        # На всякий случай ограничиваем диапазон [0; 100]
        value = max(0.0, min(100.0, value))

        # Линейная интерполяция в пределах высоты графика
        return bottom - (value / 100.0) * (bottom - top)

    def draw_series(self) -> None:
        """Рисуем динамическую линию графика по накопленной истории значений."""

        # Удаляем только линию/точку серии, но не трогаем сетку и оси
        self.canvas.delete("series")

        plot_left = self.padding
        plot_top = self.padding / 2
        plot_right = self.width - self.padding / 2
        plot_bottom = self.height - self.padding

        if len(self.history) < 2:
            return

        # Шаг по X между соседними точками
        step_x = (plot_right - plot_left) / (self.max_points - 1)

        # Canvas.create_line ожидает список вида [x1, y1, x2, y2, ...]
        points = []
        for i, value in enumerate(self.history):
            x = plot_left + i * step_x
            y = self.value_to_y(value, plot_top, plot_bottom)
            points.extend((x, y))

        # Рисуем линию графика
        self.canvas.create_line(
            *points,
            fill="#2bd66f",
            width=2,
            smooth=True,
            tags="series",
        )

        # Дополнительно выделяем последнюю точку, чтобы визуально видеть «текущее состояние»
        last_x, last_y = points[-2], points[-1]
        self.canvas.create_oval(
            last_x - 3,
            last_y - 3,
            last_x + 3,
            last_y + 3,
            fill="#7fffac",
            outline="",
            tags="series",
        )

    def update_chart(self) -> None:
        """
        Один шаг обновления:
        1) Получить текущее значение CPU.
        2) Добавить его в историю.
        3) Обновить подпись и перерисовать линию.
        4) Запланировать следующий шаг через 1000 мс.
        """

        # interval=None даёт неблокирующее обновление (UI не подвисает)
        cpu_value = psutil.cpu_percent(interval=None)

        # Добавляем новое значение в историю
        self.history.append(cpu_value)

        # Обновляем текстовый индикатор
        self.value_var.set(f"Текущая загрузка: {cpu_value:.1f}%")

        # Перерисовываем графическую серию
        self.draw_series()

        # Планируем следующий тик через 1 секунду
        self.root.after(1000, self.update_chart)


if __name__ == "__main__":
    # Точка входа в приложение Tkinter
    root = tk.Tk()
    app = CpuChartApp(root)
    root.mainloop()
