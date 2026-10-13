# Auto Typer

ใช้สำหรับเพื่อการศึกษาเท่านั้น

โปรแกรม Windows สำหรับอ่านข้อความจากพื้นที่หน้าจอด้วย Tesseract OCR แล้วพิมพ์ข้อความผ่านคีย์บอร์ด

## สิ่งที่ต้องติดตั้ง

1. ติดตั้ง Python 3.10 ขึ้นไป
2. ติดตั้งแพ็กเกจ Python:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. ติดตั้ง [Tesseract OCR สำหรับ Windows](https://github.com/UB-Mannheim/tesseract/wiki) และเลือกชุดภาษา `English` และ/หรือ `Thai` ให้ตรงกับภาษาที่จะอ่าน
4. เปิด `auto_typer.py` ด้วย Python บน Windows

โปรแกรมค้นหา Tesseract จาก `PATH` และตำแหน่งติดตั้ง Windows ทั่วไป หากติดตั้งไว้ที่อื่น ให้กำหนดตัวแปรสภาพแวดล้อม `AUTO_TYPER_TESSERACT` เป็น path เต็มของ `tesseract.exe` ก่อนเปิดโปรแกรม เช่น:

```powershell
$env:AUTO_TYPER_TESSERACT = 'D:\Tools\Tesseract\tesseract.exe'
py .\auto_typer.py
```

ภาษาที่พิมพ์ในช่องภาษา OCR ต้องมีชุดภาษาใน Tesseract ด้วย เช่น `eng`, `tha` หรือ `eng+tha` โปรแกรมจะตรวจสอบก่อนเริ่มงาน

## ปุ่มควบคุม

- `F8`: เริ่ม
- `F9`: หยุด

ก่อนเริ่ม ให้เลือกพื้นที่ข้อความบนหน้าจอและเตรียมช่องปลายทางให้พร้อม โปรแกรมจะนับถอยหลัง 3 วินาทีก่อนเริ่มพิมพ์


## PaddleOCR Runtime (Windows)

For the optional Thai + English word re-reader, keep the environment and downloaded models on `D:\Personal Program`:

```powershell
py -3.12 -m venv --system-site-packages "D:\Personal Program\OCRRuntime"
& "D:\Personal Program\OCRRuntime\Scripts\python.exe" -m pip install -r .\requirements-paddleocr.txt
```

The runtime uses PaddleOCR 3.7.0 with PaddlePaddle 3.2.2. The application launcher is `D:\Personal Program\Run Auto Typer.bat`; the model cache is stored at `D:\Personal Program\OCRRuntime\model-cache`.

The launcher also uses the Tesseract copy at `D:\Personal Program\Tesseract` and the English/Thai language data at `D:\Personal Program\OCRRuntime\tessdata`.
