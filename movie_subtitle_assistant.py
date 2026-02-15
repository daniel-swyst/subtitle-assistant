import tkinter as tk
from tkinter import filedialog
import threading
import time
import os
import ctypes
from ctypes import wintypes

CONTROL_HIDE_DELAY = 2000  # GUI hide time interval ms
START_MONITOR = 0  # 0 = first screen, 1 = second screen etc.

def get_monitors():
    monitors = []

    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append({
            "x": r.left,
            "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top
        })
        return 1

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_double
    )

    ctypes.windll.user32.EnumDisplayMonitors(
        0, 0, MONITORENUMPROC(callback), 0
    )

    return monitors


# ---------- SRT parsing ----------
def parse_srt(file_path):
    subs = []
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    entries = [e for e in content.strip().split("\n\n") if e.strip()]
    for entry in entries:
        lines = entry.splitlines()
        if "-->" not in entry:
            continue
        if "-->" in lines[0]:
            times = lines[0]
            text = "\n".join(lines[1:])
        else:
            times = lines[1]
            text = "\n".join(lines[2:])
        start, end = times.split(" --> ")
        subs.append((srt_time(start), srt_time(end), text.strip()))
    return subs

def srt_time(t):
    h, m, s = t.split(":")
    s, ms = s.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def format_time(t):
    t = int(max(0, t))
    return f"{t//3600:02}:{(t%3600)//60:02}:{t%60:02}"

# ---------- Timer ----------
class SubtitleTimer:
    def __init__(self):
        self.start = None
        self.elapsed = 0
        self.running = False
        self.lock = threading.Lock()

    def play(self):
        with self.lock:
            if not self.running:
                self.start = time.time() - self.elapsed
                self.running = True

    def pause(self):
        with self.lock:
            if self.running:
                self.elapsed = time.time() - self.start
                self.running = False

    def forward(self, d):
        with self.lock:
            if self.running:
                self.elapsed = time.time() - self.start
            self.elapsed = max(0, self.elapsed + d)
            if self.running:
                self.start = time.time() - self.elapsed

    def current(self):
        return time.time() - self.start if self.running else self.elapsed


# ---------- GUI ----------
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-transparentcolor", "white")
root.configure(bg="white")

canvas = tk.Canvas(root, bg="white", highlightthickness=0)
canvas.pack(fill="both", expand=True)

text_item = canvas.create_text(
    600, 60, text="", font=("Arial", 28, "bold"),
    fill="yellow", justify="center", width=1160
)

timer_label = tk.Label(root, text="00:00:00",
                       font=("Segoe UI", 14, "bold"),
                       bg="white", fg="red")
timer_label.place(x=1090, y=5)


# ---------- Monitor positioning ----------
current_monitor = START_MONITOR

def set_monitor(index=0):
    monitors = get_monitors()
    if not monitors:
        return

    if index >= len(monitors):
        index = 0

    m = monitors[index]

    width = 1200
    height = 120

    x = m["x"] + (m["width"] - width) // 2
    y = m["y"] + int(m["height"] * 0.875)

    root.geometry(f"{width}x{height}+{x}+{y}")

    cw.update_idletasks()
    cw.geometry(
        f"{cw.winfo_reqwidth()}x{cw.winfo_reqheight()}+"
        f"{m['x'] + m['width'] - cw.winfo_reqwidth() - 10}+"
        f"{m['y'] + 10}"
    )

def switch_monitor():
    global current_monitor
    monitors = get_monitors()
    if not monitors:
        return
    current_monitor = (current_monitor + 1) % len(monitors)
    set_monitor(current_monitor)

timer = SubtitleTimer()
subs = []

def load_srt():
    path = filedialog.askopenfilename(filetypes=[("SRT", "*.srt")])
    if path:
        subs.clear()
        subs.extend(parse_srt(path))
        timer.elapsed = 0
        timer.start = None
        srt_label.config(text=f"SRT: {os.path.basename(path)}", fg="black")

def subtitle_loop():
    while True:
        t = timer.current()
        root.after(0, lambda v=t: timer_label.config(text=format_time(v)))

        txt = ""
        for s, e, text in subs:
            if s <= t <= e:
                txt = text
                break

        root.after(0, lambda v=txt: canvas.itemconfig(text_item, text=v))
        time.sleep(0.01)

threading.Thread(target=subtitle_loop, daemon=True).start()


# ---------- Control window ----------
cw = tk.Toplevel(root)
cw.overrideredirect(True)
cw.attributes("-topmost", True)
cw.configure(bg="white")

btns = tk.Frame(cw, bg="white")
btns.pack(padx=6, pady=4)

def jump(txt, d):
    tk.Button(btns, text=txt, command=lambda: timer.forward(d)).pack(side="left", padx=2)

jump("⏪5", -5)
jump("⏪1", -1)
jump("◀︎0.2", -0.2)
jump("▶︎0.2", 0.2)
jump("⏩1", 1)
jump("⏩5", 5)

tk.Button(btns, text="▶", command=timer.play).pack(side="left", padx=4)
tk.Button(btns, text="❚❚", command=timer.pause).pack(side="left", padx=4)
tk.Button(btns, text="📂", command=load_srt).pack(side="left", padx=4)
tk.Button(btns, text="🖥", command=switch_monitor).pack(side="left", padx=4)
tk.Button(btns, text="❌", command=root.destroy).pack(side="left", padx=4)

srt_label = tk.Label(cw, text="Brak wczytanego pliku SRT",
                     font=("Segoe UI", 9),
                     bg="white", fg="gray")
srt_label.pack(fill="x", padx=6, pady=(0, 4))


# ---------- Auto-hide logic ----------
hide_job = None
mouse_over_timer = False
mouse_over_controls = False

def schedule_hide():
    global hide_job
    if hide_job:
        root.after_cancel(hide_job)
    hide_job = root.after(CONTROL_HIDE_DELAY, hide_controls)

def hide_controls():
    global hide_job
    hide_job = None
    if not (mouse_over_timer or mouse_over_controls):
        cw.attributes("-alpha", 0)

def show_controls():
    cw.attributes("-alpha", 1.0)

def on_timer_enter(event):
    global mouse_over_timer
    mouse_over_timer = True
    show_controls()
    if hide_job:
        root.after_cancel(hide_job)

def on_timer_leave(event):
    global mouse_over_timer
    mouse_over_timer = False
    schedule_hide()

def on_controls_enter(event):
    global mouse_over_controls
    mouse_over_controls = True
    show_controls()
    if hide_job:
        root.after_cancel(hide_job)

def on_controls_leave(event):
    global mouse_over_controls
    mouse_over_controls = False
    schedule_hide()

timer_label.bind("<Enter>", on_timer_enter)
timer_label.bind("<Leave>", on_timer_leave)
cw.bind("<Enter>", on_controls_enter)
cw.bind("<Leave>", on_controls_leave)

cw.attributes("-alpha", 0)


# ---------- Keyboard ----------
def toggle_play(e=None):
    timer.pause() if timer.running else timer.play()

root.bind_all("<space>", toggle_play)
root.bind_all("<Left>", lambda e: timer.forward(-2))
root.bind_all("<Right>", lambda e: timer.forward(2))
root.bind_all("<Shift-Left>", lambda e: timer.forward(-10))
root.bind_all("<Shift-Right>", lambda e: timer.forward(10))
root.bind_all("<Escape>", lambda e: root.destroy())

set_monitor(current_monitor)

root.mainloop()
