"""
Auto Typer - พิมพ์ตามข้อความที่จับภาพจากหน้าจอ
ตั้งค่าได้: ความเร็ว (WPM), ระยะเวลา, โอกาสพิมพ์ผิด

ติดตั้งก่อนใช้:
    pip install mss pillow pytesseract pynput
และติดตั้งโปรแกรม Tesseract OCR (https://github.com/UB-Mannheim/tesseract/wiki)
ปุ่มลัด:  F8 = เริ่ม   F9 = หยุด
"""

import ctypes
from dataclasses import dataclass
import difflib
import hashlib
import math
import os
import random
import shutil
import statistics
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import tkinter as tk
from tkinter import ttk, messagebox

import mss
import pytesseract
from PIL import Image, ImageChops, ImageOps, ImageStat
from pynput import keyboard

os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # tesseract 1 เธรด/ตัว แล้วเราอ่านหลายคำขนานกันเอง
OCR_RUNTIME_DIR = r"D:\Personal Program\OCRRuntime"


def configure_tesseract():
    """Find Tesseract from an explicit setting, PATH, or common Windows installs."""
    configured = os.environ.get("AUTO_TYPER_TESSERACT")
    candidates = [
        configured,
        os.path.join(r"D:\Personal Program\Tesseract", "tesseract.exe"),
        shutil.which("tesseract"),
    ]
    candidates.extend((
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"D:\Personal Program\Tesseract\tesseract.exe",  # legacy location
    ))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return None


def configure_tessdata():
    """Prefer the D: language data, then fall back to the user install."""
    candidates = [
        os.path.join(OCR_RUNTIME_DIR, "tessdata"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tessdata"),
    ]
    for data_dir in candidates:
        if all(os.path.isfile(os.path.join(data_dir, f"{lang}.traineddata"))
               for lang in ("eng", "tha")):
            # Point directly to tessdata so `--list-langs` emits plain codes;
            # pytesseract's parser does not accept the `tessdata/eng` form.
            os.environ["TESSDATA_PREFIX"] = data_dir
            return


configure_tesseract()
configure_tessdata()

# Keep PaddleOCR's downloaded models off the system drive.
os.environ.setdefault(
    "PADDLE_PDX_CACHE_HOME", os.path.join(OCR_RUNTIME_DIR, "model-cache")
)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "1")

WM_INPUTLANGCHANGEREQUEST = 0x0050
KEYBOARD_LAYOUTS = {
    "eng": ("00000409", 0x0409),  # English (United States)
    "tha": ("0000041E", 0x041E),  # Thai Kedmanee
}
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.restype = ctypes.c_void_p
_user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
_user32.GetKeyboardLayout.argtypes = [ctypes.c_uint32]
_user32.GetKeyboardLayout.restype = ctypes.c_void_p
_user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
_user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
_user32.PostMessageW.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
]
_user32.PostMessageW.restype = ctypes.c_int
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_INPUT_KEYBOARD = 1
_VK_BACK = 0x08


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("union", _INPUTUNION)]


_user32.SendInput.argtypes = [
    ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int
]
_user32.SendInput.restype = ctypes.c_uint

# ทำให้พิกัดเมาส์ตรงกับพิกเซลจริงบน Windows (กันปัญหา scale 125%/150%)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ---------- ตารางปุ่มข้างเคียง (ไว้สุ่มตัวอักษรที่พิมพ์ผิดให้สมจริง) ----------
def build_neighbors(rows, offsets, keep=lambda ch: True):
    pos = {}
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if keep(ch):
                pos[ch] = (c + offsets[r], r)
    result = {}
    for a, (ax, ay) in pos.items():
        result[a] = [
            b for b, (bx, by) in pos.items()
            if b != a and ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < 1.5
        ]
    return result


def is_thai(ch):
    return "\u0e00" <= ch <= "\u0e7f"


@dataclass(frozen=True)
class RunOptions:
    region: dict[str, int]
    wpm: float
    duration: float
    error_rate: float
    batch: int
    lang: str
    fix_errors: bool
    read_once: bool
    mono: bool
    resume: bool
    review_ocr: bool
    fixes: dict[str, str]


# แป้นอังกฤษ QWERTY (จัดแถวให้ q เป็น 0)
NEIGHBORS = build_neighbors(
    ["qwertyuiop", "asdfghjkl", "zxcvbnm"], [0.0, 0.25, 0.75]
)
# แป้นไทย Kedmanee (แถวตัวเลข, แถว QWERTY, แถว ASDF, แถว ZXCV)
NEIGHBORS.update(build_neighbors(
    ["ๅ/-ภถุึคตจขช", "ๆไำพะัีรนยบลฃ", "ฟหกดเ้่าสวง", "ผปแอิืทมใฝ"],
    [0.0, 0.5, 0.75, 1.25],
    keep=is_thai,
))


# ---------- ตัวเลือกพื้นที่หน้าจอ ----------
class RegionSelector:
    """ครอบหน้าจอด้วยหน้าต่างโปร่งแสง ให้ลากเมาส์เลือกกรอบ"""

    def __init__(self, root, on_done):
        self.on_done = on_done
        self.win = tk.Toplevel(root)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.3)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black", cursor="crosshair")
        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.start = None
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def press(self, e):
        self.start = (e.x_root, e.y_root)
        self.rect = self.canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="red", width=3
        )
        self.origin = (e.x, e.y)

    def drag(self, e):
        self.canvas.coords(self.rect, self.origin[0], self.origin[1], e.x, e.y)

    def release(self, e):
        x1, y1 = self.start
        x2, y2 = e.x_root, e.y_root
        self.win.destroy()
        left, top = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w > 10 and h > 10:
            self.on_done({"left": left, "top": top, "width": w, "height": h})


# ---------- แอปหลัก ----------
class AutoTyper:
    _paddle_ocr = None
    _paddle_ocr_error = None
    _paddle_ocr_lock = threading.Lock()

    def __init__(self, root):
        self.root = root
        root.title("Auto Typer")
        root.resizable(False, False)

        self.region = None
        self.running = False
        self.stop_flag = threading.Event()
        self.current_script = None
        self.review_window = None

        self.wpm = tk.StringVar(value="60")
        self.duration = tk.StringVar(value="60")
        self.error_pct = tk.StringVar(value="3")
        self.batch = tk.StringVar(value="8")
        self.lang = tk.StringVar(value="eng+tha")
        self.fix_errors = tk.BooleanVar(value=True)
        self.read_once = tk.BooleanVar(value=True)
        self.review_ocr = tk.BooleanVar(value=True)
        self.mono = tk.BooleanVar(value=True)
        self.resume = tk.BooleanVar(value=True)
        self.fixes = tk.StringVar(value="")

        self.build_ui()

        self.hotkeys = keyboard.GlobalHotKeys({
            "<f8>": lambda: root.after(0, self.start),
            "<f9>": lambda: root.after(0, self.stop),
        })
        self.hotkeys.start()
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ----- UI -----
    def build_ui(self):
        f = ttk.Frame(self.root, padding=12)
        f.grid()

        def row(r, label, widget):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=3)
            widget.grid(row=r, column=1, sticky="ew", pady=3, padx=(8, 0))

        row(0, "ความเร็ว (คำ/นาที)", ttk.Spinbox(f, from_=5, to=400, textvariable=self.wpm, width=10))
        self.duration_spinbox = ttk.Spinbox(
            f, from_=5, to=7200, textvariable=self.duration, width=10
        )
        row(1, "เวลาโหมดต่อเนื่อง (วินาที)", self.duration_spinbox)
        row(2, "โอกาสพิมพ์ผิด (%)", ttk.Spinbox(f, from_=0, to=50, increment=0.5, textvariable=self.error_pct, width=10))
        row(3, "จับภาพใหม่ทุก ๆ (คำ)", ttk.Spinbox(f, from_=1, to=50, textvariable=self.batch, width=10))
        row(4, "ภาษา OCR (eng, tha, eng+tha)", ttk.Entry(f, textvariable=self.lang, width=12))
        opts = ttk.Frame(f)
        opts.grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opts, text="แก้คำที่สุ่มพิมพ์ผิด (Backspace)",
                        variable=self.fix_errors).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            opts,
            text="อ่านครั้งเดียวแล้วพิมพ์จนจบ (ข้อความอยู่กับที่)",
            variable=self.read_once,
            command=self.update_review_state,
        ).pack(anchor="w", pady=2)
        self.review_checkbutton = ttk.Checkbutton(
            opts,
            text="ตรวจ/แก้ผล OCR ก่อนพิมพ์ (โหมดอ่านครั้งเดียว)",
            variable=self.review_ocr,
        )
        self.review_checkbutton.pack(anchor="w", pady=2)
        self.update_review_state()  # ให้สถานะช่องตรวจ OCR ตรงกับช่อง "อ่านครั้งเดียว" ตั้งแต่เปิดโปรแกรม
        ttk.Checkbutton(opts, text="ฟอนต์ monospace (ตรวจช่องว่างจากระยะห่างตัวอักษร)",
                        variable=self.mono).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts, text="จำจุดที่พิมพ์ค้าง (โหมดจับภาพใหม่ ข้อความเลื่อนได้)",
                        variable=self.resume).pack(anchor="w", pady=2)
        ttk.Label(opts, text="สลับแป้นไทย/อังกฤษอัตโนมัติตามภาษาของข้อความ").pack(
            anchor="w", pady=2
        )
        fx = ttk.Frame(opts)
        fx.pack(anchor="w", fill="x", pady=2)
        ttk.Label(fx, text="แก้คำที่อ่านผิด (เช่น ซ=ช, 0=O):").pack(side="left")
        ttk.Entry(fx, textvariable=self.fixes, width=16).pack(side="left", padx=(6, 0))

        self.region_label = ttk.Label(f, text="พื้นที่: ยังไม่ได้เลือก", foreground="gray")
        self.region_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        rb = ttk.Frame(f)
        rb.grid(row=7, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(rb, text="เลือกพื้นที่หน้าจอ", command=self.pick_region)\
            .pack(side="left", expand=True, fill="x")
        ttk.Button(rb, text="ทดสอบอ่าน (OCR)", command=self.preview)\
            .pack(side="left", expand=True, fill="x", padx=(6, 0))

        btns = ttk.Frame(f)
        btns.grid(row=8, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(btns, text="เริ่ม (F8)", command=self.start).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="หยุด (F9)", command=self.stop).pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.status = tk.StringVar(value="พร้อมใช้งาน")
        ttk.Label(f, textvariable=self.status, wraplength=300, foreground="#0a5")\
            .grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def update_review_state(self):
        state = "normal" if self.read_once.get() else "disabled"
        self.review_checkbutton.configure(state=state)
        self.duration_spinbox.configure(state="disabled" if self.read_once.get() else "normal")

    def set_status(self, text):
        self.root.after(0, lambda: self.status.set(text))

    # ----- เลือกพื้นที่ -----
    def pick_region(self):
        self.root.withdraw()
        self.root.after(200, lambda: RegionSelector(self.root, self.region_selected))
        self.root.after(300, self._restore_when_done)

    def _restore_when_done(self):
        # รอจนหน้าต่างเลือกพื้นที่ปิด แล้วค่อยแสดงหน้าต่างหลักกลับมา
        if any(isinstance(w, tk.Toplevel) for w in self.root.winfo_children()):
            self.root.after(150, self._restore_when_done)
        else:
            self.root.deiconify()

    def region_selected(self, region):
        self.region = region
        self.region_label.config(
            text=f"พื้นที่: {region['width']}x{region['height']} ที่ ({region['left']}, {region['top']})",
            foreground="black",
        )

    # ----- เริ่ม/หยุด -----
    def start(self):
        if self.running:
            return
        try:
            wpm = float(self.wpm.get())
            duration = float(self.duration.get())
            error_pct = float(self.error_pct.get())
            batch = int(self.batch.get())
            if not (
                math.isfinite(wpm) and 5 <= wpm <= 400
                and math.isfinite(duration) and 5 <= duration <= 7200
                and math.isfinite(error_pct) and 0 <= error_pct <= 50
                and 1 <= batch <= 50
            ):
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("ค่าไม่ถูกต้อง", "กรุณาตรวจสอบตัวเลขที่กรอก")
            return
        if not self.region:
            messagebox.showwarning("ยังไม่ได้เลือกพื้นที่", "กดปุ่ม 'เลือกพื้นที่หน้าจอ' ก่อน")
            return

        lang = self.lang.get().strip() or "eng"
        try:
            self.validate_ocr(lang)
        except (OSError, RuntimeError, pytesseract.TesseractNotFoundError) as e:
            messagebox.showerror("ตั้งค่า OCR ไม่สำเร็จ", str(e))
            return

        fixes = {}
        for pair in self.fixes.get().replace(",", " ").split():
            if "=" in pair:
                wrong, right = pair.split("=", 1)
                if wrong:
                    fixes[wrong] = right
        options = RunOptions(
            region=dict(self.region),
            wpm=wpm,
            duration=duration,
            error_rate=error_pct / 100,
            batch=batch,
            lang=lang,
            fix_errors=self.fix_errors.get(),
            read_once=self.read_once.get(),
            mono=self.mono.get(),
            resume=self.resume.get(),
            review_ocr=self.review_ocr.get(),
            fixes=fixes,
        )
        self.running = True
        self.layout_switch_failed = False
        self.stop_flag.clear()
        if options.read_once and options.review_ocr:
            self.set_status("กำลังอ่านข้อความเพื่อตรวจทานก่อนพิมพ์...")
            threading.Thread(
                target=self.prepare_review,
                args=(options,),
                daemon=True,
            ).start()
            return
        threading.Thread(
            target=self.run, args=(options,), daemon=True
        ).start()

    def prepare_review(self, options):
        try:
            text = self.read_screen(
                options.region, options.lang, options.mono, options.fixes
            )
        except Exception as e:
            self.root.after(0, lambda error=e: self.finish_review_error(error))
            return
        if self.stop_flag.is_set():
            self.root.after(0, self.finish_review_cancelled)
            return
        self.root.after(0, lambda: self.show_ocr_review(options, text))

    @staticmethod
    def validate_ocr(lang):
        command = pytesseract.pytesseract.tesseract_cmd
        if not command or not os.path.isfile(command):
            raise RuntimeError(
                "ไม่พบ Tesseract OCR. ติดตั้ง Tesseract หรือเพิ่มโฟลเดอร์ลง PATH; "
                "หรือกำหนด AUTO_TYPER_TESSERACT เป็น path ของ tesseract.exe."
            )
        try:
            installed = set(pytesseract.get_languages(config=""))
        except pytesseract.TesseractNotFoundError as e:
            raise RuntimeError(f"เปิด Tesseract ไม่ได้: {command}") from e
        requested = {part for part in lang.split("+") if part}
        missing = sorted(requested - installed)
        if missing:
            raise RuntimeError(
                f"Tesseract ไม่มีชุดภาษา {', '.join(missing)}; "
                f"ภาษาที่ติดตั้งอยู่: {', '.join(sorted(installed)) or '(ไม่มี)'}"
            )

    def show_ocr_review(self, options, text):
        if self.stop_flag.is_set():
            self.running = False
            return

        win = tk.Toplevel(self.root)
        self.review_window = win
        win.title("ตรวจและแก้ข้อความ OCR")
        win.transient(self.root)
        win.geometry("700x360")
        ttk.Label(
            win,
            text="ตรวจข้อความที่อ่านได้ แก้ให้ถูกต้อง แล้วกด “ใช้ข้อความนี้”",
            wraplength=660,
        ).pack(anchor="w", padx=10, pady=(10, 4))
        box = tk.Text(win, width=80, height=16, wrap="word")
        box.insert("1.0", text)
        box.pack(fill="both", expand=True, padx=10, pady=4)

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(4, 10))

        def cancel():
            if win.winfo_exists():
                win.destroy()
            self.review_window = None
            self.running = False
            self.set_status("ยกเลิกก่อนเริ่มพิมพ์")

        def accept():
            reviewed_text = box.get("1.0", "end-1c")
            win.destroy()
            self.review_window = None
            if not reviewed_text.strip():
                self.running = False
                self.set_status("ไม่มีข้อความให้พิมพ์")
                return
            threading.Thread(
                target=self.run,
                args=(options, reviewed_text),
                daemon=True,
            ).start()

        ttk.Button(buttons, text="ยกเลิก", command=cancel).pack(side="right")
        ttk.Button(
            buttons, text="ใช้ข้อความนี้", command=accept
        ).pack(side="right", padx=(0, 6))
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _event: cancel())
        box.focus_set()

    def finish_review_error(self, error):
        self.running = False
        self.set_status(f"เกิดข้อผิดพลาดขณะอ่าน OCR: {error}")
        messagebox.showerror("อ่าน OCR ไม่สำเร็จ", str(error))

    def finish_review_cancelled(self):
        self.running = False
        self.set_status("หยุดโดยผู้ใช้")

    def stop(self):
        self.stop_flag.set()
        if self.review_window is not None:
            try:
                if self.review_window.winfo_exists():
                    self.review_window.destroy()
            except tk.TclError:
                pass
            self.review_window = None
            self.running = False
            self.set_status("หยุดโดยผู้ใช้")

    def close(self):
        self.stop_flag.set()
        self.hotkeys.stop()
        self.root.destroy()

    # ----- งานหลัก -----
    def run(self, options, reviewed_text=None):
        try:
            for i in (3, 2, 1):
                if self.stop_flag.is_set():
                    return
                self.set_status(f"คลิกช่องพิมพ์ให้พร้อม... เริ่มใน {i}")
                time.sleep(1)

            once = options.read_once
            end_time = time.time() + options.duration
            typed_words = 0
            words, pos, finished = [], 0, False
            if reviewed_text is not None:
                words = reviewed_text.split()
                if once and words:
                    end_time = float("inf")
            resume = options.resume and not once
            history = []  # คำที่พิมพ์ไปล่าสุด ใช้หาจุดต่อหลังหน้าจอเลื่อน
            pending_screen = None
            while not self.stop_flag.is_set() and time.time() < end_time:
                if pos >= len(words):
                    if once and words:  # โหมดอ่านครั้งเดียว: พิมพ์ครบแล้วจบเลย
                        finished = True
                        break
                    self.set_status("กำลังจับภาพและอ่านข้อความ...")
                    words = self.read_screen(
                        options.region, options.lang, options.mono, options.fixes
                    ).split()
                    pos = 0
                    if once and words:
                        # The duration limits how long to wait for readable
                        # text, not how long the one-shot typing may take.
                        end_time = float("inf")
                    if words and resume and history:
                        resume_pos = self.find_resume(words, history)
                        if resume_pos is None:
                            if words != pending_screen:
                                pending_screen = words
                                words = []
                                pos = 0
                                self.set_status(
                                    "รอภาพบรรทัดใหม่ให้นิ่งก่อนเริ่มพิมพ์..."
                                )
                                time.sleep(0.7)
                                continue
                            pending_screen = None
                            pos = 0
                        else:
                            pending_screen = None
                            pos = resume_pos
                        if pos >= len(words):  # ยังไม่มีข้อความใหม่โผล่มา
                            words = []
                            self.set_status("รอข้อความใหม่...")
                            time.sleep(0.7)
                            continue
                    if not words:
                        pending_screen = None
                        self.set_status("อ่านข้อความไม่ได้ ลองใหม่...")
                        time.sleep(0.7)
                        continue

                n = min(options.batch, len(words) - pos)
                chunk = " ".join(words[pos:pos + n])
                pos += n
                if not (once and pos >= len(words)):
                    chunk += " "  # คำสุดท้ายของข้อความไม่ต้องเว้นวรรคท้าย
                self.set_status(f"กำลังพิมพ์: {chunk[:40]}...")
                typed_chars = self.type_text(
                    chunk, options.wpm, options.error_rate, end_time,
                    options.fix_errors,
                )
                typed_words += len(chunk[:typed_chars].split())
                if not once:
                    history = (history + words[pos - n:pos])[-12:]
                    words = []  # โหมดปกติ: จับภาพใหม่ทุกชุด
                    time.sleep(0.3)  # รอให้หน้าเว็บอัปเดต/เลื่อนเสร็จก่อนจับภาพ

            if self.stop_flag.is_set():
                reason = "หยุดโดยผู้ใช้"
            elif finished:
                reason = "พิมพ์ครบข้อความแล้ว"
            else:
                reason = "ครบเวลาแล้ว"
            self.set_status(f"{reason} (พิมพ์ไปประมาณ {typed_words} คำ)")
        except Exception as e:
            self.set_status(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.running = False

    def read_screen(self, region, lang, mono, fixes):
        with mss.MSS() as sct:
            shot = sct.grab(region)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        return self.read_image(img, lang, mono, fixes)

    def read_image(self, img, lang, mono, fixes):
        if "tha" in lang:
            # Thin Thai vowel/tone strokes survive better with a higher cutoff
            # after autocontrast; keep the image large for the Thai model.
            img = self.preprocess(img, scale=4, thr=140)
        else:
            img = self.preprocess(img)
        words = self.ocr_text(img, lang, mono).split()
        # แก้เฉพาะ "คำที่ตรงทั้งคำ" เท่านั้น เช่น ซ=ช จะไม่แตะคำว่า ซอส
        normalized = []
        for word in words:
            word = unicodedata.normalize("NFC", fixes.get(word, word))
            # Tesseract sometimes emits Thai sara am as nikhahit + aa.
            normalized.append(word.replace("\u0e4d\u0e32", "\u0e33"))
        result = " ".join(normalized)
        # In the typing exercise, ฝึกซ้ำ is frequently misread as ฝึกช้า/ฝึกซ้า.
        # Correct this phrase only; standalone ช้า is valid Thai and is preserved.
        for wrong in (
            "ฝึกช้า", "ฝึกซ้า", "ฝึกซ๊า", "ฝึก ช้า", "ฝึก ซ้า", "ฝึก ซ๊า",
        ):
            result = result.replace(wrong, "ฝึกซ้ำ")
        return result

    @classmethod
    def paddle_recognize_word(cls, crop):
        """Use PaddleOCR's Thai model to re-read one uncertain word crop."""
        if cls._paddle_ocr_error is not None:
            return "", -1.0
        try:
            import numpy as np
            from paddleocr import PaddleOCR

            with cls._paddle_ocr_lock:
                if cls._paddle_ocr is None:
                    cls._paddle_ocr = PaddleOCR(
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name="th_PP-OCRv5_mobile_rec",
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                    )
                engine = cls._paddle_ocr
        except Exception as error:
            cls._paddle_ocr_error = error
            return "", -1.0

        try:
            results = engine.predict(np.asarray(crop.convert("RGB")))
            candidates = []
            for result in results:
                texts = result.get("rec_texts", [])
                scores = result.get("rec_scores", [])
                for text, score in zip(texts, scores):
                    text = unicodedata.normalize("NFC", "".join(str(text).split()))
                    text = text.replace("\u0e4d\u0e32", "\u0e33")
                    if any("\u0e00" <= char <= "\u0e7f" for char in text):
                        candidates.append((text, float(score) * 100))
            return max(candidates, key=lambda item: item[1]) if candidates else ("", -1.0)
        except Exception:
            return "", -1.0

    def ocr_text(self, img, lang, mono):
        cfg = "--psm 6 -c preserve_interword_spaces=1"
        if "tha" in lang:
            # Whole-line bilingual OCR preserves Latin words, punctuation and
            # Thai/English boundaries better than splitting every glyph gap.
            plain = pytesseract.image_to_string(img, lang=lang, config=cfg)
            if not plain.strip():
                return self.ocr_by_gaps(img, lang)
            return self.recover_thai_misreads(img, plain, lang, cfg)
        plain = pytesseract.image_to_string(img, lang=lang, config=cfg)
        if not mono:
            return plain

        # ฟอนต์ monospace: ตัวอักษรเว้นระยะเท่ากัน ถ้าห่างเกิน ~1.5 เท่า = มีช่องว่าง
        chars = []  # (ตัวอักษร, ตำแหน่งกึ่งกลางแนวนอน)
        for line in pytesseract.image_to_boxes(img, lang=lang, config=cfg).splitlines():
            p = line.split(" ")
            if len(p) >= 6:
                chars.append((p[0], (int(p[1]) + int(p[3])) / 2))

        # เทียบกับผลอ่านแบบข้อความปกติ: ตัวที่โหมดตำแหน่ง "เห็นเกินมา" (เช่น 4 ในช่องว่าง) ให้ทิ้ง
        plain_chars = [c for c in plain if not c.isspace()]
        sm = difflib.SequenceMatcher(None, plain_chars, [c for c, _ in chars], autojunk=False)
        aligned = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                for k in range(j2 - j1):
                    aligned.append((plain_chars[i1 + k], chars[j1 + k][1]))
            elif tag == "replace":
                aligned.extend(chars[j1:j2])
            # tag == "insert": ตัวเกิน ทิ้ง / tag == "delete": ไม่มีตำแหน่ง ข้าม
        chars = aligned
        if not chars:
            return plain

        diffs = [b[1] - a[1] for a, b in zip(chars, chars[1:]) if b[1] > a[1]]
        if len(diffs) < 8:
            return plain
        pitch = statistics.median(diffs)

        out = [chars[0][0]]
        for (_, x1), (c2, x2) in zip(chars, chars[1:]):
            if x2 < x1 or x2 - x1 > 1.5 * pitch:  # ขึ้นบรรทัดใหม่ หรือมีช่องว่าง
                out.append(" ")
            out.append(c2)
        return "".join(out)

    def recover_thai_misreads(self, img, text, lang, config):
        """Re-read likely Thai words that the combined model emitted as Latin."""
        tokens = text.split()
        thai_retry_words = {"ฝึกช้า", "ฝึกซ้า", "ฝึกซ๊า"}

        def suspicious(token, confidence=None):
            token = token.strip(".,!?;:'\"()[]{}")
            if token in thai_retry_words:
                return True
            if not (token.isascii() and token.isalpha()):
                return False
            # Short title-case strings such as "Au" are also common Thai OCR
            # confusions (e.g. กิน). Re-read them with the Thai model when the
            # page uses Thai; accept a replacement only at high confidence.
            return (token.islower() and len(token) <= 3) or (
                token.istitle() and len(token) <= 3
            ) or (
                token.istitle() and len(token) >= 4
                and confidence is not None and confidence < 85
            )

        if not any(
            (token.isascii() and token.isalpha()
             and (token.islower() or token.istitle()))
            or token.strip(".,!?;:'\"()[]{}") in thai_retry_words
            for token in tokens
        ):
            return text

        data = pytesseract.image_to_data(
            img, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
        detections = []
        for i, raw in enumerate(data["text"]):
            word = raw.strip()
            try:
                confidence = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if not suspicious(word, confidence):
                continue
            if confidence < 0:
                continue
            detections.append((
                word, confidence, int(data["left"][i]), int(data["top"][i]),
                int(data["width"][i]), int(data["height"][i]),
            ))

        corrected = tokens[:]
        used = set()
        attempts = 0
        for token_index, token in enumerate(tokens):
            core = token.strip(".,!?;:'\"()[]{}")
            thai_retry = core in thai_retry_words
            ascii_retry = (
                token.isascii() and token.isalpha()
                and ((token.islower() and len(token) <= 3) or token.istitle())
            )
            if not thai_retry and not ascii_retry:
                continue
            if attempts >= 8:
                break
            match = next((
                (i, item) for i, item in enumerate(detections)
                if i not in used and item[0].casefold() == core.casefold()
            ), None)
            if match is None:
                continue
            detection_index, (_raw, _conf, left, top, width, height) = match
            used.add(detection_index)
            pad = max(6, height // 3)
            crop = img.crop((
                max(0, left - pad), max(0, top - pad),
                min(img.width, left + width + pad),
                min(img.height, top + height + pad),
            ))
            attempts += 1
            if thai_retry:
                candidate, confidence = self.paddle_recognize_word(crop)
                if confidence >= 85:
                    corrected[token_index] = candidate
                continue
            try:
                candidate, confidence = self.recognize_word(crop, lang)
            except RuntimeError:
                continue
            candidate_is_thai = any(
                "\u0e00" <= char <= "\u0e7f" for char in candidate
            )
            if confidence >= 85 and candidate_is_thai:
                corrected[token_index] = candidate
                if core.istitle() and len(core) <= 3:
                    paddle_candidate, paddle_confidence = self.paddle_recognize_word(crop)
                    if paddle_confidence >= 92 and paddle_candidate != candidate:
                        corrected[token_index] = paddle_candidate
                continue
            if not candidate_is_thai:
                candidate, confidence = self.paddle_recognize_word(crop)
                if confidence >= 80:
                    corrected[token_index] = candidate
        return " ".join(corrected)

    @staticmethod
    def preprocess(img, scale=3, thr=110):
        """แปลงภาพเป็นตัวอักษรดำบนพื้นขาวล้วน เพื่อให้ OCR อ่านง่ายที่สุด"""
        r, g, b = img.split()
        dark_bg = ImageStat.Stat(ImageOps.grayscale(img)).mean[0] < 128
        if dark_bg:
            # พื้นมืด: ใช้ช่องสีที่สว่างสุด ทำให้ตัวอักษรเขียว/แดงสว่างพอกัน
            ch = ImageChops.lighter(ImageChops.lighter(r, g), b)
        else:
            ch = ImageChops.darker(ImageChops.darker(r, g), b)
        ch = ImageOps.autocontrast(ch, cutoff=1)
        ch = ch.resize((ch.width * scale, ch.height * scale), Image.LANCZOS)
        ch = ch.point(lambda p: 255 if p > thr else 0)  # ตัดพื้นหลัง/แถบสีจาง ๆ ทิ้ง
        if dark_bg:
            ch = ImageOps.invert(ch)
        return ImageOps.expand(ch, border=20, fill=255)

    @staticmethod
    def find_resume(words, history, max_tail=6) -> Optional[int]:
        """หาว่าคำที่พิมพ์ล่าสุดอยู่ตรงไหนของข้อความที่เพิ่งอ่านได้ แล้วคืนตำแหน่งคำถัดไป

        เทียบแบบยืดหยุ่น (เผื่อ OCR เพี้ยนเล็กน้อย) ถ้าไม่เจอจะคืน None
        """
        def sim(a, b):
            return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()

        for k in range(min(max_tail, len(history)), 0, -1):
            tail = history[-k:]
            best_score, best_end = 0.0, None
            for i in range(len(words) - k + 1):
                score = sum(sim(words[i + j], tail[j]) for j in range(k)) / k
                if score > best_score + 1e-9:  # เท่ากันให้เอาตำแหน่งแรกสุด
                    best_score, best_end = score, i + k
            if best_end is not None and best_score >= (0.85 if k >= 3 else 0.9):
                return best_end
        return None

    @staticmethod
    def _runs(flags):
        """คืนช่วง (เริ่ม, จบ) ของค่า True ที่ต่อเนื่องกัน"""
        runs, start = [], None
        for i, v in enumerate(flags):
            if v and start is None:
                start = i
            elif not v and start is not None:
                runs.append((start, i - 1))
                start = None
        if start is not None:
            runs.append((start, len(flags) - 1))
        return runs

    def ocr_by_gaps(self, img, lang):
        """แบ่งภาพเป็นบรรทัด -> คำ ตามช่องว่างว่างเปล่า แล้ว OCR ทีละคำ"""
        w, h = img.size
        ink = ImageOps.invert(img.convert("L")).point(lambda p: 255 if p > 127 else 0)
        data = ink.tobytes()

        # 1) แบ่งบรรทัด (รวมแถบสระบน/ล่างที่ห่างกันนิดเดียวเข้าด้วยกัน)
        row_runs = self._runs([any(data[y * w:(y + 1) * w]) for y in range(h)])
        if not row_runs:
            return ""
        max_h = max(b - a + 1 for a, b in row_runs)
        lines = []
        for a, b in row_runs:
            if lines and a - lines[-1][1] - 1 < 0.25 * max_h:
                lines[-1][1] = b
            else:
                lines.append([a, b])

        crops = []
        for y0, y1 in lines:
            line_h = y1 - y0 + 1
            # 2) หาคอลัมน์ที่มีหมึก
            acc = 0
            for y in range(y0, y1 + 1):
                acc |= int.from_bytes(data[y * w:(y + 1) * w], "big")
            col_runs = self._runs([c != 0 for c in acc.to_bytes(w, "big")])
            if not col_runs:
                continue

            # 3) หาเกณฑ์ว่าช่องว่างกว้างแค่ไหนถึงเป็นช่องว่างระหว่างคำ
            gaps = [col_runs[i + 1][0] - col_runs[i][1] - 1 for i in range(len(col_runs) - 1)]
            thr = self.GAP_FALLBACK * line_h
            sg = sorted(gaps)
            best_ratio, best_mid = 0, None
            for lo, hi in zip(sg, sg[1:]):
                ratio = (hi + 1) / (lo + 1)
                if ratio > best_ratio:
                    best_ratio, best_mid = ratio, (lo + hi) / 2
            # บรรทัดที่ไม่มีสระไทยจะเตี้ยกว่า ช่องว่างระหว่างคำจึงเป็นสัดส่วนที่ใหญ่กว่า (ขยายเพดานเป็น 0.5)
            if best_ratio >= 1.8 and 0.1 * line_h <= best_mid <= 0.5 * line_h:
                thr = best_mid  # ช่องว่างสองกลุ่มแยกกันชัด ใช้ค่ากลางระหว่างสองกลุ่ม

            chunks = [list(col_runs[0])]
            for (a, b), g in zip(col_runs[1:], gaps):
                if g > thr:
                    chunks.append([a, b])
                else:
                    chunks[-1][1] = b

            # 4) ตัดภาพทีละคำ (หนึ่งก้อน = หนึ่งคำ) เก็บไว้อ่านทีเดียว
            pad = max(2, int(min(0.1 * line_h, thr / 2)))  # เว้นขอบรอบคำให้ OCR อ่านง่ายขึ้น
            for a, b in chunks:
                crop = img.crop((max(0, a - pad), max(0, y0 - pad),
                                 min(w, b + 1 + pad), min(h, y1 + 1 + pad)))
                crops.append(ImageOps.expand(crop, border=20, fill=255))

        # 5) อ่านทุกคำ (ขนานกันตามจำนวนแกน CPU ผลลัพธ์เรียงตามลำดับเดิม)
        workers = max(1, min(8, os.cpu_count() or 1))
        pool = ThreadPoolExecutor(workers) if workers > 1 and len(crops) > 1 else None
        pmap = pool.map if pool else map
        try:
            # หน้านี้เป็นไทยเป็นส่วนใหญ่ไหม? ถ้าใช่ ผลละตินสั้น ๆ ที่โมเดลอังกฤษ "มั่นใจ" (ana, a, Tan)
            # มักเป็นคำไทยที่อ่านผิด จึงผ่อนเกณฑ์ให้ผลของ tha ชนะได้ง่ายขึ้น
            self.__dict__.pop("thai_gap", None)
            if "tha" in lang and "+" in lang and crops:
                thai_like = sum(1 for t in pmap(self._tha, crops) if self._thai_kind(t[0]) == "pure")
                if thai_like / len(crops) >= self.THAI_PAGE_SHARE:
                    self.thai_gap = self.THAI_GAP_THAI_PAGE
            read = [t[0] for t in pmap(lambda c: self.recognize_word(c, lang), crops)]
        finally:
            self.__dict__.pop("thai_gap", None)
            if pool:
                pool.shutdown()
        return " ".join(t for t in read if t)

    @staticmethod
    def ocr_chunk(crop, lang, psms=(8, 10, 13)):
        """OCR ภาพหนึ่งคำ คืน (ข้อความ, ความมั่นใจเฉลี่ย 0-100)"""
        # psm 8 = หนึ่งคำ, ถ้าไม่เจออะไรเลย (เช่น ! ? # ตัวเดี่ยว ๆ) ลอง psm 10 = หนึ่งอักขระ
        # แล้วลอง psm 13 = บรรทัดดิบ (วัดจริงแล้ว ! ถูกอ่านได้เฉพาะโหมดนี้)
        for psm in psms:
            d = pytesseract.image_to_data(
                crop, lang=lang, config=f"--psm {psm}",
                output_type=pytesseract.Output.DICT,
            )
            toks = [(t.strip(), float(c)) for t, c in zip(d["text"], d["conf"])
                    if t.strip() and float(c) >= 0]
            if toks:
                text = "".join(t for t, _ in toks)
                # Tesseract ชอบให้ นิคหิต+สระอา (ํา) ซึ่งหน้าตาเหมือน ำ แต่คนละรหัส พิมพ์ลงเว็บแล้วไม่ตรง
                text = text.replace("\u0e4d\u0e32", "\u0e33")
                return text, sum(c for _, c in toks) / len(toks)
        return "", -1.0

    # ---- ตัวช่วยตัดสินว่าผลอ่านเป็นไทยหรือไม่ ----
    EDGE_JUNK = "'\"`‘’“”.,()[]{}|"
    BRACKETS = "()[]{}|"
    THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"

    def _thai_kind(self, text):
        """'pure' = ไทยล้วน, 'mixed' = ไทยติดสัญลักษณ์/เลข ASCII (เช่น @บ้าน, ผล!), None = อื่น ๆ"""
        t = text.strip(self.EDGE_JUNK)
        if not any(is_thai(c) and c not in self.THAI_DIGITS for c in t):
            return None  # ไม่มีพยัญชนะ/สระไทยเลย (เลขไทยล้วนไม่นับ)
        if any(c.isascii() and c.isalpha() for c in t):
            return None  # มีตัวอักษรละตินปน = ไม่ใช่คำไทย (มักเป็นผลมั่ว)
        return "pure" if all(is_thai(c) for c in t) else "mixed"

    def _adjusted(self, cand):
        """ความมั่นใจหลังหักคะแนนเมื่อมีเครื่องหมายแปลก ๆ ติดขอบ/แทรกกลางคำ"""
        text, conf = cand
        if text != text.strip(self.EDGE_JUNK):
            conf -= 15
        if any(c in self.BRACKETS for c in text.strip(self.EDGE_JUNK)):
            conf -= 15
        return conf

    def _only_thai_digits(self, text):
        return bool(text) and all(c in self.THAI_DIGITS for c in text)

    @staticmethod
    def _clean_thai(text):
        """ตัดเครื่องหมายแปลก ๆ หน้า/หลังคำ และเลขไทยที่ OCR เห็นเกินมาปนกับพยัญชนะ (ต -> ๓ต)"""
        text = text.strip(AutoTyper.EDGE_JUNK)
        digits = AutoTyper.THAI_DIGITS
        if any(c in digits for c in text) and any(c not in digits for c in text):
            text = "".join(c for c in text if c not in digits)
        return text

    # เกณฑ์เลือกภาษา ได้จากการวัดบนภาพทดสอบสุ่ม 468 คำ (ช่วงที่ให้ผลดีกว้างและเสถียร):
    # โมเดล tha อ่านคำไทยจริงได้ไทยล้วนทุกครั้ง ความมั่นใจต่ำสุด ~72%
    # ส่วนคำละตินที่ถูกอ่านเป็นไทยล้วนจะมั่นใจไม่เกิน ~84% และมักต่ำกว่าโมเดลอังกฤษ
    THAI_MIN_CONF = 72
    THAI_VS_LATIN_GAP = 12
    # สัดส่วนคำที่ tha อ่านเป็นไทยล้วน (ทุกระดับความมั่นใจ) ถ้าถึงเกณฑ์นี้ถือว่าหน้านั้น "เป็นไทยเป็นส่วนใหญ่"
    # วัดได้: หน้าจริงไทย ~90% = 0.87, หน้าสังเคราะห์ไทย 50% = 0.68, 70% = 0.81 -> ตั้งที่ 0.78
    GAP_FALLBACK = 0.2  # เกณฑ์ช่องว่างระหว่างคำ (สัดส่วนของความสูงบรรทัด) เมื่อแยกกลุ่มช่องว่างไม่ชัด
    THAI_PAGE_SHARE = 0.78
    THAI_GAP_THAI_PAGE = 30  # ใช้แทน THAI_VS_LATIN_GAP เมื่อเป็นหน้าไทยเป็นส่วนใหญ่
    THAI_MIN_CONF_THAI_PAGE = 55  # และลดเกณฑ์ขั้นต่ำของ tha ลง (คำไทยจริงบนหน้าจริงมั่นใจต่ำกว่าภาพสังเคราะห์)
    THAI_STRONG = 86      # ไทยล้วนมั่นใจขนาดนี้ ไม่ต้องถามโมเดลอื่นอีก (คำละตินไม่เคยถึง)
    BOTH_MIN_CONF = 85    # โมเดลรวมอ่านเป็นไทยล้วน ต้องมั่นใจขนาดนี้ (T ตกเกณฑ์ เช่น ข ไป)
    MIXED_MIN_CONF = 80   # ไทยติดสัญลักษณ์ ต้องเข้มกว่าไทยล้วน

    def _junk(self, text):
        """มีวงเล็บ/ขีดตั้งปนมา (เครื่องหมายคำพูด/จุดที่ติดหน้าสระนำ เ โ ไ ใ ไม่นับ เพราะตัดทิ้งได้และข้อความที่เหลือมักถูก)"""
        return any(c in self.BRACKETS for c in text)

    def choose_candidate(self, T, B, E, gap=None):
        """เลือกผลอ่านจาก 3 โมเดล: T=tha, B=รวม (eng+tha), E=ภาษาอื่นที่ไม่ใช่ tha (B/E เป็น None ได้)

        ที่วัดได้จริง: ความมั่นใจของโมเดลอังกฤษเชื่อไม่ได้ (ให้ 94% กับ 'ana' ที่จริงคือ มาก)
        และของโมเดลไทยก็แกว่ง (ไป ถูกแต่ได้ 9-18%) จึงใช้หลายสัญญาณร่วมกัน
        ลำดับความไว้ใจ: T (tha) > B (รวม) > E (อังกฤษ) เพราะ T ผิดน้อยกว่าในการวัดบนหน้าจริง
        """
        gap = self.THAI_VS_LATIN_GAP if gap is None else gap
        e_conf = E[1] if E else -1.0
        # หน้าไทยเป็นส่วนใหญ่: ผ่อนเกณฑ์ให้ T ชนะ "เฉพาะเมื่อผลของโมเดลอังกฤษดูเป็นขยะ" (สั้น ≤3 ตัว พิมพ์เล็ก
        # เช่น a, ana, Tan) ไม่ผ่อนทุกคำ เพราะวัดแล้วถ้าผ่อนหมดคำอังกฤษจริงจะถูกลดจาก 93% เหลือ 75%
        e_core = E[0].strip(self.EDGE_JUNK) if E and E[0] else ""
        e_junky = (1 <= len(e_core) <= 3 and e_core.isascii() and e_core.isalpha()
                   and not e_core.isupper())
        if gap >= self.THAI_GAP_THAI_PAGE and e_junky:
            min_conf = self.THAI_MIN_CONF_THAI_PAGE
        else:
            gap = self.THAI_VS_LATIN_GAP
            min_conf = self.THAI_MIN_CONF

        def eligible(cand, is_t):
            if not cand or not cand[0]:
                return False
            kind = self._thai_kind(cand[0])
            conf = cand[1]
            if kind == "pure":
                return conf >= min_conf and conf >= e_conf - gap if is_t \
                    else conf >= self.BOTH_MIN_CONF
            if kind == "mixed":
                return conf >= (self.MIXED_MIN_CONF if is_t else self.BOTH_MIN_CONF) and conf >= e_conf
            return False

        t_ok, b_ok = eligible(T, True), eligible(B, False)
        if t_ok and not self._junk(T[0]):
            return self._clean_thai(T[0]), T[1]
        if t_ok and b_ok and not self._junk(B[0]):
            return self._clean_thai(B[0]), B[1]  # T มีเครื่องหมายแปลก ๆ แต่ B สะอาด
        if t_ok:
            return self._clean_thai(T[0]), T[1]
        if b_ok:
            # โมเดลรวมยืนยันแล้วว่าเป็นคำไทย แต่ความมั่นใจของ T ต่ำ: ถ้า T เป็นไทยล้วนและสะอาด
            # ใช้ข้อความของ T (วัดแล้วถูกกว่า B เช่น โต๊ะ/อาหาร ที่ B อ่านเป็น ใต๊ะ/อาหาว)
            if self._thai_kind(T[0]) == "pure" and not self._junk(T[0]):
                return self._clean_thai(T[0]), T[1]
            return self._clean_thai(B[0]), B[1]

        # ไม่ใช่คำไทย: เลือกจากโมเดลอื่น (ตัดเลขไทยล้วนทิ้ง เพราะมักเป็นสัญลักษณ์ที่อ่านผิด เช่น & -> ๑)
        pool = []
        for cand in (E, B, T):
            if not cand or not cand[0] or self._only_thai_digits(cand[0]):
                continue
            if cand is T and self._thai_kind(cand[0]) is not None:
                continue  # ผลของ tha ที่เป็นไทยแต่ไม่ผ่านเกณฑ์ = มั่ว
            pool.append((self._adjusted(cand), cand))
        if pool:
            return max(pool, key=lambda x: x[0])[1]
        return next((c for c in (B, E, T) if c and c[0]), ("", -1.0))

    def _undouble(self, crop, text):
        """psm 8 กับฟอนต์บางตัวอ่านตัวแรกซ้ำ (อาหาร -> ออาหาร) ใช้ psm 7 ช่วยยืนยัน

        ถ้า psm 7 ไม่ขึ้นต้นด้วยตัวซ้ำสองตัว แสดงว่าตัวแรกเกินมา (คำจริงอย่าง 'ออก' psm 7 ก็ยังอ่านเป็น ออ)
        """
        if len(text) > 1 and text[0] == text[1] and is_thai(text[0]):
            alt, _ = self.ocr_chunk(crop, "tha", psms=(7,))
            if alt and alt[0] == text[0] and not alt.startswith(text[0] * 2):
                return text[1:]
        return text

    def _tha(self, crop):
        """ผลของโมเดล tha ต่อคำ (แคชไว้ เพราะใช้ทั้งตอนวัดสัดส่วนไทยของหน้าและตอนเลือกคำ)"""
        cache = self.__dict__.setdefault("_tha_cache", {})
        key = (crop.size, hashlib.md5(crop.tobytes()).digest())
        if key not in cache:
            if len(cache) > 1600:
                cache.clear()
            cache[key] = self.ocr_chunk(crop, "tha")
        return cache[key]

    def recognize_word(self, crop, lang):
        """อ่านหนึ่งคำ (มีแคช: คำที่หน้าตาเหมือนเดิมเป๊ะไม่ต้องอ่านซ้ำ)"""
        gap = self.__dict__.get("thai_gap", self.THAI_VS_LATIN_GAP)
        cache = self.__dict__.setdefault("_word_cache", {})
        key = (lang, gap, crop.size, hashlib.md5(crop.tobytes()).digest())
        if key not in cache:
            if len(cache) > 800:
                cache.clear()
            cache[key] = self._recognize_word(crop, lang, gap)
        return cache[key]

    def _recognize_word(self, crop, lang, gap):
        parts = [p for p in lang.split("+") if p]
        if "tha" not in parts:
            best = self.ocr_chunk(crop, lang)
            for part in (parts if len(parts) > 1 else []):
                cand = self.ocr_chunk(crop, part)
                if cand[1] > best[1]:
                    best = cand
            return best

        thai = self._tha(crop)
        others = [p for p in parts if p != "tha"]
        if not others:  # ภาษาไทยอย่างเดียว
            text = self._clean_thai(thai[0]) if self._thai_kind(thai[0]) else thai[0]
            if thai[1] < 60 and len(text) <= 2:
                # ผลสั้นและมั่นใจต่ำ มักเป็นสัญลักษณ์ (& -> ณฒ) ลองถามโมเดลอังกฤษเฉพาะกรณีนี้
                try:
                    sym = self.ocr_chunk(crop, "eng")
                except Exception:
                    sym = ("", -1.0)
                if sym[0] and sym[1] >= 60 and not any(c.isalpha() for c in sym[0]):
                    return sym
            return self._undouble(crop, text), thai[1]

        # ไทยล้วนที่มั่นใจมาก -> จบเลย (ประหยัดเวลา: คำไทยส่วนใหญ่ใช้แค่ 1 รอบ)
        if self._thai_kind(thai[0]) == "pure" and self._adjusted(thai) >= self.THAI_STRONG:
            return self._undouble(crop, self._clean_thai(thai[0])), thai[1]

        latin = self.ocr_chunk(crop, "+".join(others))
        # ผลของ tha ไม่ใช่ไทยเลย และโมเดลอังกฤษมั่นใจ -> คำละติน/สัญลักษณ์ ไม่ต้องเรียกโมเดลรวม
        if self._thai_kind(thai[0]) is None and latin[1] >= 85 and not self._only_thai_digits(latin[0]):
            return self.choose_candidate(thai, None, latin, gap)
        both = self.ocr_chunk(crop, lang)
        text, conf = self.choose_candidate(thai, both, latin, gap)
        if self._thai_kind(text):
            text = self._undouble(crop, text)
        return text, conf

    def preview(self):
        if not self.region:
            messagebox.showwarning("ยังไม่ได้เลือกพื้นที่", "กดปุ่ม 'เลือกพื้นที่หน้าจอ' ก่อน")
            return
        region = dict(self.region)
        lang = self.lang.get().strip() or "eng"
        mono = self.mono.get()
        fixes = {}
        for pair in self.fixes.get().replace(",", " ").split():
            if "=" in pair:
                wrong, right = pair.split("=", 1)
                if wrong:
                    fixes[wrong] = right

        def work():
            try:
                text = self.read_screen(region, lang, mono, fixes)
            except Exception as e:
                text = f"เกิดข้อผิดพลาด: {e}"
            self.root.after(0, lambda: self.show_preview(text))

        threading.Thread(target=work, daemon=True).start()

    def show_preview(self, text):
        win = tk.Toplevel(self.root)
        win.title("ผลการอ่าน OCR")
        box = tk.Text(win, width=60, height=8, wrap="word")
        box.insert("1.0", text or "(อ่านไม่ได้)")
        box.pack(padx=8, pady=8)

    def type_text(self, text, wpm, err, end_time, fix_errors):
        base = 60.0 / (wpm * 5)  # 1 คำ = 5 ตัวอักษร
        self.current_script = None
        i = 0
        while i < len(text):
            if self.stop_flag.is_set() or time.time() >= end_time:
                return i
            ch = text[i]

            if ch.lower() in NEIGHBORS and random.random() < err:
                wrong = random.choice(NEIGHBORS[ch.lower()])
                if ch.isupper():
                    wrong = wrong.upper()
                self.press(wrong)
                self.pause(base)

                if not fix_errors:
                    i += 1  # ปล่อยผิดไว้เลย
                    continue

                # ผู้ใช้สังเกตเห็นทันที หรือพิมพ์ต่อไปอีก 1-3 ตัวก่อนจะรู้ตัว
                extra = min(
                    len(text) - i - 1,
                    0 if random.random() < 0.7 else random.randint(1, 3),
                )
                for ex in text[i + 1:i + 1 + extra]:
                    self.press(ex)
                    self.pause(base)
                time.sleep(random.uniform(0.15, 0.4))  # เวลาตอบสนอง
                for _ in range(extra + 1):
                    self.tap(keyboard.Key.backspace)
                    self.pause(base * 0.6)
                # ลบตัวผิดออกแล้ว พิมพ์ตัวที่ถูกต้อง (ตัวที่พิมพ์เกินจะถูกพิมพ์ใหม่ตามปกติ)
                self.press(ch)
                self.pause(base)
                i += 1
                continue

            self.press(ch)
            self.pause(base)
            i += 1
        return i

    def pause(self, base):
        # สุ่มความเร็วให้ไม่คงที่เหมือนหุ่นยนต์
        delay = max(0.01, random.gauss(base, base * 0.25))
        end = time.time() + delay
        while time.time() < end:
            if self.stop_flag.is_set():
                return
            time.sleep(max(0.0, min(0.01, end - time.time())))

    def press(self, ch):
        script = self.script_for_char(ch)
        if script and script != self.current_script:
            if not self.__dict__.get("layout_switch_failed"):
                try:
                    self.switch_keyboard_language(script)
                except (OSError, TimeoutError) as e:
                    # ไม่ให้ทั้งงานล้มเพราะสลับแป้นไม่ได้ ตัวอักษรส่งแบบ Unicode อยู่แล้ว พิมพ์ต่อได้
                    self.layout_switch_failed = True
                    self.set_status(f"สลับแป้นไทย/อังกฤษไม่สำเร็จ ({e}) พิมพ์ต่อโดยไม่สลับ")
            self.current_script = script
        code_units = ch.encode("utf-16-le")
        events = (_INPUT * (len(code_units) // 2 * 2))()
        for i in range(len(code_units) // 2):
            unit = int.from_bytes(code_units[i * 2:i * 2 + 2], "little")
            events[2 * i] = _INPUT(
                type=_INPUT_KEYBOARD,
                union=_INPUTUNION(ki=_KEYBDINPUT(
                    0, unit, _KEYEVENTF_UNICODE, 0, 0
                )),
            )
            events[2 * i + 1] = _INPUT(
                type=_INPUT_KEYBOARD,
                union=_INPUTUNION(ki=_KEYBDINPUT(
                    0, unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP, 0, 0
                )),
            )
        sent = _user32.SendInput(
            len(events), events, ctypes.sizeof(_INPUT)
        )
        if sent != len(events):
            self.raise_input_error(f"ส่งอักขระ {ch!r}")

    @staticmethod
    def script_for_char(ch):
        if is_thai(ch):
            return "tha"
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            return "eng"
        return None

    def switch_keyboard_language(self, script):
        layout_id, lang_id = KEYBOARD_LAYOUTS[script]
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        thread_id = _user32.GetWindowThreadProcessId(hwnd, None)
        if not thread_id:
            raise ctypes.WinError(ctypes.get_last_error())
        current_layout = _user32.GetKeyboardLayout(thread_id)
        if current_layout and (current_layout & 0xFFFF) == lang_id:
            return

        layout = _user32.LoadKeyboardLayoutW(layout_id, 0)
        if not layout:
            raise ctypes.WinError(ctypes.get_last_error())
        if not _user32.PostMessageW(
            hwnd, WM_INPUTLANGCHANGEREQUEST, 0, layout
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            current_layout = _user32.GetKeyboardLayout(thread_id)
            if current_layout and (current_layout & 0xFFFF) == lang_id:
                return
            time.sleep(0.01)
        raise TimeoutError(f"เปลี่ยนภาษาแป้นพิมพ์เป็น {script} ไม่สำเร็จ")

    def tap(self, key):
        if key is not keyboard.Key.backspace:
            raise ValueError(f"ไม่รองรับปุ่มพิเศษ: {key}")
        events = (_INPUT * 2)(
            _INPUT(
                type=_INPUT_KEYBOARD,
                union=_INPUTUNION(ki=_KEYBDINPUT(
                    _VK_BACK, 0, 0, 0, 0
                )),
            ),
            _INPUT(
                type=_INPUT_KEYBOARD,
                union=_INPUTUNION(ki=_KEYBDINPUT(
                    _VK_BACK, 0, _KEYEVENTF_KEYUP, 0, 0
                )),
            ),
        )
        sent = _user32.SendInput(len(events), events, ctypes.sizeof(_INPUT))
        if sent != len(events):
            self.raise_input_error("ส่งปุ่ม Backspace")

    @staticmethod
    def raise_input_error(action):
        error = ctypes.get_last_error()
        raise OSError(error, f"{action} ผ่าน Windows SendInput ไม่สำเร็จ")


if __name__ == "__main__":
    root = tk.Tk()
    AutoTyper(root)
    root.mainloop()
