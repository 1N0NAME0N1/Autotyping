# OCR generated-word batch test

30 sets: 10 Thai, 10 English, 10 mixed; 150 words per set; 4,500 total.
Path: `AutoTyper.read_image`, selected language, `mono=True`; Tesseract eng/tha data installed.
Black text on white, Windows Tahoma for Thai and Consolas for English. Controlled OCR, not noisy screenshots.
WER = word-level Levenshtein edits (substitutions + insertions + deletions) / 150.

| Set | Output | Substitutions | Insertions | Deletions | WER | Error |
|---|---:|---:|---:|---:|---:|---|
| TH-01 | 150/150 | 23 | 0 | 0 | 15.3% |  |
| TH-02 | 150/150 | 20 | 0 | 0 | 13.3% |  |
| TH-03 | 150/150 | 14 | 0 | 0 | 9.3% |  |
| TH-04 | 150/150 | 23 | 0 | 0 | 15.3% |  |
| TH-05 | 150/150 | 20 | 0 | 0 | 13.3% |  |
| TH-06 | 150/150 | 20 | 0 | 0 | 13.3% |  |
| TH-07 | 150/150 | 26 | 0 | 0 | 17.3% |  |
| TH-08 | 150/150 | 15 | 0 | 0 | 10.0% |  |
| TH-09 | 150/150 | 14 | 0 | 0 | 9.3% |  |
| TH-10 | 150/150 | 20 | 0 | 0 | 13.3% |  |
| EN-01 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-02 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-03 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-04 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-05 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-06 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-07 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-08 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-09 | 150/150 | 0 | 0 | 0 | 0.0% |  |
| EN-10 | 150/150 | 1 | 0 | 0 | 0.7% |  |
| MX-01 | 150/150 | 15 | 0 | 0 | 10.0% |  |
| MX-02 | 150/150 | 17 | 0 | 0 | 11.3% |  |
| MX-03 | 150/150 | 16 | 0 | 0 | 10.7% |  |
| MX-04 | 150/150 | 10 | 0 | 0 | 6.7% |  |
| MX-05 | 150/150 | 17 | 0 | 0 | 11.3% |  |
| MX-06 | 150/150 | 15 | 0 | 0 | 10.0% |  |
| MX-07 | 150/150 | 14 | 0 | 0 | 9.3% |  |
| MX-08 | 150/150 | 14 | 0 | 0 | 9.3% |  |
| MX-09 | 150/150 | 10 | 0 | 0 | 6.7% |  |
| MX-10 | 150/150 | 20 | 0 | 0 | 13.3% |  |

## Thai aggregate
10 sets; 1,500 source words; 1500 output words; 195 edit errors; WER 13.00%.

## English aggregate
10 sets; 1,500 source words; 1500 output words; 1 edit errors; WER 0.07%.

## Mixed aggregate
10 sets; 1,500 source words; 1500 output words; 148 edit errors; WER 9.87%.

## Forced line-wrap sentence checks
- WRAP-01: PASS — การพิมพ์สัมผัสเป็นทักษะที่ใช้ได้ตลอดชีวิต
- WRAP-02: PASS — ผมเป็นนักศึกษาที่วิทยาลัยการคอมพิวเตอร์
- WRAP-03: PASS — เราไปโรงเรียนด้วยกันทุกวัน

## Files
- `sets.json`: generated inputs.
- `results.json`: OCR text and per-set metrics.
- `sentence_wrap_results.json`: OCR results for the three wrapped sentences.
