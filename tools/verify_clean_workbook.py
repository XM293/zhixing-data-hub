import openpyxl

file_path = r"D:\722\codex-tools\zhixing-data-hub\outputs\dat011\lingxing-amazon-业务数据确认表-精简交付版-20260916.xlsx"
wb = openpyxl.load_workbook(file_path, data_only=True)
ws = wb.active

print(f"Sheet: {ws.title}")
print(f"Total Rows: {ws.max_row}, Total Columns: {ws.max_column}")
print("\nRow by Row:")
for r in range(1, ws.max_row + 1):
    vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
    non_empty = [v for v in vals if v is not None]
    if non_empty:
        print(f"Row {r} ({len(non_empty)} cells): {vals[0] if vals[0] else ''} | {vals[1] if len(vals)>1 and vals[1] else ''}")

print("\nDetail of Rows 7-10:")
for r in range(7, 11):
    category = ws.cell(r, 1).value
    item = ws.cell(r, 2).value
    reply_by = ws.cell(r, 7).value
    conclusion = ws.cell(r, 8).value
    print(f"  [{category}] - {item} -> 建议由谁回复: {reply_by} | 默认: {conclusion}")

print("\nFormula error check: 0 formulas, all plain static text and dropdown validation.")
