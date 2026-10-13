"""Generate and OCR 30 deterministic 150-word test images."""
import json
import random
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pytesseract

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auto_typer


THAI = """ฉัน คุณ เขา เรา พวกเขา คน เด็ก ผู้ใหญ่ ครอบครัว เพื่อน ครู นักเรียน หมอ พยาบาล ตำรวจ วิศวกร เกษตรกร พนักงาน เจ้าของ ลูกค้า บ้าน ห้อง ประตู หน้าต่าง โต๊ะ เก้าอี้ เตียง หมอน ผ้าห่ม ตู้ ชั้น พื้น เพดาน หลังคา สวน ถนน สะพาน ตลาด ร้านค้า โรงเรียน โรงพยาบาล สถานี สนามบิน เมือง หมู่บ้าน ประเทศ จังหวัด อำเภอ ตำบล แม่น้ำ ทะเล ภูเขา ป่า ทุ่งนา เกาะ ชายหาด ท้องฟ้า เมฆ ฝน ลม แดด อากาศ น้ำ ไฟ ดิน หิน ต้นไม้ ดอกไม้ ใบไม้ ผลไม้ อาหาร ข้าว ขนม ผัก เนื้อ ปลา ไข่ นม กาแฟ ชา น้ำตาล เกลือ พริก มะนาว กล้วย มะม่วง ส้ม มะพร้าว ขนุน แตงโม ข้าวโพด ถั่ว ขนมปัง ซุป ก๋วยเตี๋ยว รถ จักรยาน รถไฟ เครื่องบิน เรือ รถเมล์ แท็กซี่ มอเตอร์ไซค์ คอมพิวเตอร์ โทรศัพท์ หน้าจอ แป้นพิมพ์ เมาส์ กล้อง นาฬิกา วิทยุ โทรทัศน์ หนังสือ สมุด ปากกา ดินสอ ยางลบ กระดาษ จดหมาย ข้อความ คำถาม คำตอบ ภาษา คำ ประโยค เรื่อง ข่าว เพลง ภาพยนตร์ เกม กีฬา ฟุตบอล บาสเกตบอล ว่ายน้ำ วิ่ง เดิน นอน ตื่น กิน ดื่ม อ่าน เขียน พูด ฟัง ดู คิด เรียน สอน ทำงาน เล่น พัก เดินทาง ซื้อ ขาย จ่าย รับ ส่ง เปิด ปิด เริ่ม หยุด สร้าง ใช้ ช่วย รอ ค้นหา เลือก เปลี่ยน แก้ไข ตรวจสอบ ทดลอง สำเร็จ ผิดพลาด ถูกต้อง ง่าย ยาก เร็ว ช้า ใหม่ เก่า ใหญ่ เล็ก สูง ต่ำ ยาว สั้น กว้าง แคบ ร้อน เย็น หนาว สดใส สวย ดี แย่ สำคัญ ปลอดภัย สะดวก อร่อย หวาน เปรี้ยว ขม เค็ม สะอาด สกปรก เช้า กลางวัน เย็น กลางคืน วันนี้ พรุ่งนี้ เมื่อวาน เวลา นาที ชั่วโมง วัน เดือน ปี เงิน ราคา งาน ความคิด ความรู้ ความสุข ความรัก ความหวัง โอกาส ปัญหา วิธี เหตุผล ผลลัพธ์ ข้อมูล ระบบ โปรแกรม ไฟล์ โฟลเดอร์ อินเทอร์เน็ต เว็บไซต์ เครือข่าย บัญชี รหัสผ่าน ผู้ใช้ เครื่องมือ พลังงาน สุขภาพ ร่างกาย หัวใจ สมอง มือ เท้า ตา หู ปาก เสียง สี แดง เขียว น้ำเงิน เหลือง ขาว ดำ เทา น้ำตาล ม่วง หนึ่ง สอง สาม สิบ ร้อย พัน ล้าน ฝึกช้า กระจก กระเป๋า รองเท้า เสื้อผ้า หมวก แว่นตา กุญแจ จาน ชาม ช้อน ส้อม มีด แก้ว ขวด กล่อง ของขวัญ สัตว์ สุนัข แมว นก ม้า วัว ควาย ไก่ เป็ด หมู ลิง ช้าง เสือ หมี ผีเสื้อ แมลง ผึ้ง มด ปลาโลมา เต่า งู กบ จิ้งจก""".split()
ENGLISH = """I you he she it we they person people child adult family friend teacher student doctor nurse police engineer farmer worker owner customer house room door window table chair bed pillow blanket cabinet shelf floor ceiling roof garden street bridge market store school hospital station airport city village country province river sea mountain forest field island beach sky cloud rain wind sunlight weather water fire earth stone tree flower leaf fruit food rice snack vegetable meat fish egg milk coffee tea sugar salt pepper lemon banana mango orange coconut jackfruit watermelon corn bean bread soup noodle car bicycle train airplane boat bus taxi motorcycle computer telephone screen keyboard mouse camera clock radio television book notebook pen pencil eraser paper letter message question answer language word sentence story news song movie game sport football basketball swimming running walking sleep wake eat drink read write speak listen watch think learn teach work play rest travel buy sell pay receive send open close begin stop build use help wait search choose change edit check test succeed failure correct easy difficult fast slow new old large small high low long short wide narrow hot cold bright beautiful good bad important safe convenient delicious sweet sour bitter clean dirty morning noon evening night today tomorrow yesterday time minute hour day month year money price job idea knowledge happiness love hope chance problem method reason result data system program file folder internet website network account password user tool energy health body heart brain hand foot eye ear mouth sound color red green blue yellow white black gray brown purple one two three ten hundred thousand million technology science nature culture keyboard typing desktop window garden flower orange light right night through thought enough quality service performance accuracy example generate dataset random reproducible compare actual result report summary word token edit distance space line font sample varied text display screen mouse pointer control image source test branch status commit push""".split()


def render(words, font):
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_width, margin, gap, line_height = 1900, 40, 24, 58
    lines, line, width = [], [], 0
    for word in words:
        word_width = measure.textlength(word, font=font)
        if line and width + gap + word_width > max_width:
            lines.append(line)
            line, width = [], 0
        width += (gap if line else 0) + word_width
        line.append(word)
    if line:
        lines.append(line)
    image = Image.new(
        "RGB", (max_width + 2 * margin, 2 * margin + line_height * len(lines)), "white"
    )
    draw = ImageDraw.Draw(image)
    for row, words_in_line in enumerate(lines):
        x, y = margin, margin + row * line_height
        for word in words_in_line:
            draw.text((x, y), word, font=font, fill="black")
            x += measure.textlength(word, font=font) + gap
    return image


def edit_counts(expected, actual):
    previous = [(j, 0, j) for j in range(len(actual) + 1)]
    for i, left in enumerate(expected, 1):
        current = [(i, i, 0)]
        for j, right in enumerate(actual, 1):
            current.append(min(
                (previous[j][0] + 1, previous[j][1] + 1, previous[j][2]),
                (current[j - 1][0] + 1, current[j - 1][1], current[j - 1][2] + 1),
                (previous[j - 1][0] + (left != right),
                 previous[j - 1][1] + (left != right), previous[j - 1][2]),
                key=lambda item: item[0],
            ))
        previous = current
    return previous[-1]


def main():
    assert {"eng", "tha"} <= set(pytesseract.get_languages(config=""))
    rng = random.Random(20261013)
    cases = []
    for kind, vocabulary, lang in (("thai", THAI, "tha"), ("english", ENGLISH, "eng")):
        for number in range(1, 11):
            words = rng.choices(vocabulary, k=150)
            if kind == "thai" and number == 1:
                words[0] = "ฝึกช้า"  # Exercise the app's phrase-correction rule.
            cases.append({"id": f"{kind[:2].upper()}-{number:02}", "kind": kind,
                          "lang": lang, "words": words})
    for number in range(1, 11):
        words = rng.choices(THAI, k=75) + rng.choices(ENGLISH, k=75)
        if number == 1:
            words[0] = "ฝึกช้า"
        rng.shuffle(words)
        cases.append({"id": f"MX-{number:02}", "kind": "mixed", "lang": "eng+tha",
                      "words": words})

    output_dir = Path(__file__).parent
    (output_dir / "sets.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    thai_font = ImageFont.truetype(r"C:\Windows\Fonts\tahoma.ttf", 36)
    english_font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 36)
    engine = auto_typer.AutoTyper.__new__(auto_typer.AutoTyper)
    results = []
    for case in cases:
        font = english_font if case["kind"] == "english" else thai_font
        try:
            text = engine.read_image(render(case["words"], font), case["lang"], True, {})
            error = None
        except Exception as exc:
            text, error = "", f"{type(exc).__name__}: {exc}"
        expected = [unicodedata.normalize("NFC", w).casefold() for w in case["words"]]
        actual = [unicodedata.normalize("NFC", w).casefold() for w in text.split()]
        distance, substitutions, insertions = edit_counts(expected, actual)
        results.append({"id": case["id"], "kind": case["kind"], "expected": 150,
                        "actual": len(actual), "word_errors": distance,
                        "wer": round(distance / 150, 4), "substitutions": substitutions,
                        "insertions": insertions, "deletions": distance - substitutions - insertions,
                        "error": error, "output": text})
        print(f"{case['id']} {len(actual)}/150 errors={distance} WER={distance / 150:.1%}",
              flush=True)
    (output_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# OCR generated-word batch test", "",
             "30 sets: 10 Thai, 10 English, 10 mixed; 150 words per set; 4,500 total.",
             "Path: `AutoTyper.read_image`, selected language, `mono=True`; Tesseract eng/tha data installed.",
             "Black text on white, Windows Tahoma for Thai and Consolas for English. Controlled OCR, not noisy screenshots.",
             "WER = word-level Levenshtein edits (substitutions + insertions + deletions) / 150.", "",
             "| Set | Output | Substitutions | Insertions | Deletions | WER | Error |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for result in results:
        lines.append(f"| {result['id']} | {result['actual']}/150 | {result['substitutions']} | "
                     f"{result['insertions']} | {result['deletions']} | {result['wer']:.1%} | "
                     f"{result['error'] or ''} |")
    for kind in ("thai", "english", "mixed"):
        group = [r for r in results if r["kind"] == kind]
        errors = sum(r["word_errors"] for r in group)
        lines += ["", f"## {kind.title()} aggregate",
                  f"10 sets; 1,500 source words; {sum(r['actual'] for r in group)} output words; "
                  f"{errors} edit errors; WER {errors / 1500:.2%}."]
    lines += ["", "## Files", "- `sets.json`: generated inputs.",
              "- `results.json`: OCR text and per-set metrics."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
