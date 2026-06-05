"""
Auto Converter: input/ --> output/
วางไฟล์ใน input/ แล้วรัน script นี้
รองรับ: .json .jsonl .sql .xml .csv .txt .log .xlsx
"""

import os
import sys
import csv
import json
import re
import time

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR   = os.path.join(BASE_DIR, "input")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
CHUNK_SIZE  = 50_000
ENCODING    = "utf-8"

SUPPORTED = (".json", ".jsonl", ".ndjson", ".sql", ".xml", ".csv", ".txt", ".log", ".xlsx", ".tsv")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── helpers ────────────────────────────────────────────────────────────────────
def detect_format(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":            return "json"
    if ext in (".jsonl",".ndjson"): return "jsonl"
    if ext == ".sql":             return "sql"
    if ext == ".xml":             return "xml"
    if ext in (".xlsx",".xls"):   return "xlsx"
    return "flat"

def flatten(d, parent="", sep="_"):
    items = {}
    for k, v in d.items():
        key = f"{parent}{sep}{k}" if parent else k
        if isinstance(v, dict):   items.update(flatten(v, key, sep))
        elif isinstance(v, list): items[key] = json.dumps(v, ensure_ascii=False)
        else:                     items[key] = v
    return items

def out_path(input_path, part=None):
    name = os.path.splitext(os.path.basename(input_path))[0]
    suffix = f"_part{part:03d}" if part else ""
    return os.path.join(OUTPUT_DIR, f"{name}{suffix}.csv")

def write_chunk(rows, headers, path):
    with open(path, "w", newline="", encoding=ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"    Saved {len(rows):,} rows  -->  {os.path.basename(path)}")

# ── converters ────────────────────────────────────────────────────────────────
def conv_json(path):
    with open(path, "r", encoding=ENCODING, errors="replace") as f:
        data = json.load(f)
    if isinstance(data, dict): data = [data]
    rows = [flatten(r) if isinstance(r, dict) else {"value": r} for r in data]
    headers = list(dict.fromkeys(k for r in rows for k in r))
    for i in range(0, len(rows), CHUNK_SIZE):
        part = i // CHUNK_SIZE + 1
        write_chunk(rows[i:i+CHUNK_SIZE], headers,
                    out_path(path, part) if len(rows) > CHUNK_SIZE else out_path(path))
    return len(rows)

def conv_jsonl(path):
    headers, buf, part, total, seen = [], [], 1, 0, set()
    with open(path, "r", encoding=ENCODING, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: obj = flatten(json.loads(line))
            except: continue
            for k in obj:
                if k not in seen: seen.add(k); headers.append(k)
            buf.append(obj); total += 1
            if len(buf) >= CHUNK_SIZE:
                write_chunk(buf, headers, out_path(path, part)); part += 1; buf = []
    if buf: write_chunk(buf, headers, out_path(path, part) if part > 1 else out_path(path))
    return total

def conv_sql(path):
    pat = re.compile(r"INSERT\s+INTO\s+`?(\w+)`?\s*\(([^)]+)\)\s*VALUES\s*(.+?);", re.I | re.DOTALL)
    vp  = re.compile(r"\(([^()]*(?:'[^']*'[^()]*)*)\)")
    tables, bufs, parts, total = {}, {}, {}, 0
    with open(path, "r", encoding=ENCODING, errors="replace") as f:
        content = ""
        for line in f:
            content += line
            if ";" not in content: continue
            for m in pat.finditer(content):
                tbl  = m.group(1)
                cols = [c.strip().strip("`'\"") for c in m.group(2).split(",")]
                if tbl not in tables:
                    tables[tbl] = cols; bufs[tbl] = []; parts[tbl] = 1
                for vm in vp.finditer(m.group(3)):
                    raw  = vm.group(1)
                    vals = [v.strip().strip("'") for v in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", raw)]
                    bufs[tbl].append(dict(zip(cols, vals))); total += 1
                    if len(bufs[tbl]) >= CHUNK_SIZE:
                        p = os.path.join(OUTPUT_DIR, f"{tbl}_part{parts[tbl]:03d}.csv")
                        write_chunk(bufs[tbl], tables[tbl], p); parts[tbl] += 1; bufs[tbl] = []
            content = ""
    for tbl in tables:
        if bufs[tbl]:
            p = os.path.join(OUTPUT_DIR, f"{tbl}_part{parts[tbl]:03d}.csv")
            write_chunk(bufs[tbl], tables[tbl], p)
    return total

def conv_xml(path):
    import xml.etree.ElementTree as ET
    buf, headers, part, total, seen = [], [], 1, 0, set()
    for event, elem in ET.iterparse(path, events=("end",)):
        children = list(elem)
        if not children: continue
        row = {child.tag: (child.text or "").strip() for child in children}
        if not row: continue
        for k in row:
            if k not in seen: seen.add(k); headers.append(k)
        buf.append(row); total += 1; elem.clear()
        if len(buf) >= CHUNK_SIZE:
            write_chunk(buf, headers, out_path(path, part)); part += 1; buf = []
    if buf: write_chunk(buf, headers, out_path(path, part) if part > 1 else out_path(path))
    return total

def conv_xlsx(path):
    try: import openpyxl
    except ImportError: os.system("pip install openpyxl"); import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    total = 0
    for sheet in wb.sheetnames:
        ws   = wb[sheet]
        rows = ws.iter_rows(values_only=True)
        hdrs = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(next(rows))]
        buf, part = [], 1
        for row in rows:
            buf.append(dict(zip(hdrs, [str(v) if v is not None else "" for v in row]))); total += 1
            if len(buf) >= CHUNK_SIZE:
                name = os.path.splitext(os.path.basename(path))[0]
                write_chunk(buf, hdrs, os.path.join(OUTPUT_DIR, f"{name}_{sheet}_part{part:03d}.csv"))
                part += 1; buf = []
        if buf:
            name = os.path.splitext(os.path.basename(path))[0]
            write_chunk(buf, hdrs, os.path.join(OUTPUT_DIR, f"{name}_{sheet}.csv"))
    return total

def conv_flat(path):
    with open(path, "r", encoding=ENCODING, errors="replace") as s:
        sniff = s.read(4096)
    try:    delim = csv.Sniffer().sniff(sniff).delimiter
    except: delim = "\t" if "\t" in sniff else ","
    with open(path, "r", encoding=ENCODING, errors="replace") as f:
        reader  = csv.DictReader(f, delimiter=delim)
        headers = reader.fieldnames or []
        buf, part, total = [], 1, 0
        for row in reader:
            buf.append(row); total += 1
            if len(buf) >= CHUNK_SIZE:
                write_chunk(buf, headers, out_path(path, part)); part += 1; buf = []
        if buf: write_chunk(buf, headers, out_path(path, part) if part > 1 else out_path(path))
    return total

CONVERTERS = {"json": conv_json, "jsonl": conv_jsonl, "sql": conv_sql,
              "xml": conv_xml, "xlsx": conv_xlsx, "flat": conv_flat}

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    files = [f for f in os.listdir(INPUT_DIR)
             if os.path.splitext(f)[1].lower() in SUPPORTED]

    if not files:
        print("=" * 55)
        print("  ไม่มีไฟล์ใน input/")
        print("  วางไฟล์ของคุณไว้ที่:")
        print(f"  {INPUT_DIR}")
        print("  แล้วรัน script นี้อีกครั้ง")
        print("=" * 55)
        return

    print("=" * 55)
    print(f"  พบ {len(files)} ไฟล์ใน input/")
    print(f"  Output --> {OUTPUT_DIR}")
    print("=" * 55)

    success, failed = [], []
    for fname in files:
        fpath = os.path.join(INPUT_DIR, fname)
        size  = os.path.getsize(fpath) / (1024**2)
        fmt   = detect_format(fpath)
        print(f"\n[{fmt.upper()}] {fname}  ({size:.1f} MB)")
        t = time.time()
        try:
            total = CONVERTERS[fmt](fpath)
            elapsed = time.time() - t
            print(f"  Done: {total:,} rows  |  {elapsed:.1f}s")
            success.append(fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append((fname, str(e)))

    print("\n" + "=" * 55)
    print(f"  สำเร็จ : {len(success)} ไฟล์")
    if failed:
        print(f"  ล้มเหลว: {len(failed)} ไฟล์")
        for f, e in failed:
            print(f"    - {f}: {e}")
    print(f"  CSV files อยู่ที่: {OUTPUT_DIR}")
    print("=" * 55)

if __name__ == "__main__":
    main()
