"""
CSV Splitter - แบ่งไฟล์ CSV ขนาดใหญ่เป็นไฟล์ละ 800 MB
วางไฟล์ CSV ใน input/  -->  ไฟล์แบ่งออกมาที่ output/split/
"""

import os
import csv
import time

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR     = os.path.join(BASE_DIR, "input")
OUTPUT_DIR    = os.path.join(BASE_DIR, "output", "split")
SPLIT_SIZE_MB = 800
ENCODING      = "utf-8"
SPLIT_BYTES   = SPLIT_SIZE_MB * 1024 * 1024

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def split_csv(filepath):
    filename  = os.path.splitext(os.path.basename(filepath))[0]
    file_size = os.path.getsize(filepath) / (1024 ** 2)

    print(f"\n  File  : {os.path.basename(filepath)}")
    print(f"  Size  : {file_size:,.1f} MB")
    print(f"  Split : {SPLIT_SIZE_MB} MB each")

    with open(filepath, "r", encoding=ENCODING, errors="replace") as f:
        reader  = csv.reader(f)
        headers = next(reader, None)

        if headers is None:
            print("  ERROR: ไฟล์ว่างเปล่าหรือไม่มี header")
            return 0, 0, []

        part          = 1
        row_count     = 0
        total_rows    = 0
        bytes_written = 0
        parts_created = []

        def new_part(part_num):
            out_path = os.path.join(OUTPUT_DIR, f"{filename}_part{part_num:03d}.csv")
            fout     = open(out_path, "w", newline="", encoding=ENCODING)
            w        = csv.writer(fout)
            w.writerow(headers)
            hdr_bytes = len((",".join(headers) + "\n").encode(ENCODING))
            return fout, w, out_path, hdr_bytes

        fout, writer, current_path, bytes_written = new_part(part)
        parts_created.append(current_path)

        for row in reader:
            row_bytes = len((",".join(str(c) for c in row) + "\n").encode(ENCODING))

            if bytes_written + row_bytes > SPLIT_BYTES:
                fout.close()
                print(f"    Part {part:03d}: {row_count:,} rows  -->  {os.path.basename(current_path)}")
                part         += 1
                row_count     = 0
                fout, writer, current_path, bytes_written = new_part(part)
                parts_created.append(current_path)

            writer.writerow(row)
            bytes_written += row_bytes
            row_count     += 1
            total_rows    += 1

        fout.close()
        print(f"    Part {part:03d}: {row_count:,} rows  -->  {os.path.basename(current_path)}")

    return total_rows, part, parts_created


def main():
    csv_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".csv")]

    if not csv_files:
        print("=" * 55)
        print("  ไม่พบไฟล์ .csv ใน input/")
        print(f"  วางไฟล์ CSV ที่นี่: {INPUT_DIR}")
        print("=" * 55)
        return

    print("=" * 55)
    print(f"  พบ {len(csv_files)} ไฟล์ CSV ใน input/")
    print(f"  Output --> {OUTPUT_DIR}")
    print("=" * 55)

    success, skipped = [], []

    for fname in csv_files:
        fpath   = os.path.join(INPUT_DIR, fname)
        size_mb = os.path.getsize(fpath) / (1024 ** 2)

        if size_mb <= SPLIT_SIZE_MB:
            print(f"\n  SKIP: {fname} ({size_mb:.1f} MB) -- เล็กกว่า {SPLIT_SIZE_MB} MB ไม่ต้องแบ่ง")
            skipped.append(fname)
            continue

        t = time.time()
        try:
            total_rows, parts, _ = split_csv(fpath)
            elapsed = time.time() - t
            print(f"  Done: {total_rows:,} rows  |  {parts} parts  |  {elapsed:.1f}s")
            success.append((fname, parts, total_rows))
        except Exception as e:
            print(f"  ERROR: {fname} --> {e}")

    print("\n" + "=" * 55)
    print(f"  สำเร็จ : {len(success)} ไฟล์")
    for fname, parts, rows in success:
        print(f"    - {fname}  -->  {parts} parts  ({rows:,} rows)")
    if skipped:
        print(f"  ข้าม   : {len(skipped)} ไฟล์ (ขนาดไม่ถึง {SPLIT_SIZE_MB} MB)")
    print(f"  ไฟล์อยู่ที่: {OUTPUT_DIR}")
    print("=" * 55)


if __name__ == "__main__":
    main()
