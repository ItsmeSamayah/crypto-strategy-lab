"""
Exhaustive search for any 8-char hex color or alpha-appended hex in dashboard.py
"""
with open("dashboard.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== All lines containing 'fillcolor' ===")
for i, line in enumerate(lines, 1):
    if "fillcolor" in line.lower():
        print(f"  L{i}: {line.rstrip()}")

print("\n=== All lines where hex color is concatenated ===")
for i, line in enumerate(lines, 1):
    stripped = line.rstrip()
    # Look for any string ending in 2 hex chars being concatenated
    if ("'up'" in stripped or "'down'" in stripped or "theme_colors" in stripped) and (
        "22'" in stripped or '22"' in stripped or
        "33'" in stripped or '33"' in stripped or
        "44'" in stripped or '44"' in stripped or
        "55'" in stripped or '55"' in stripped or
        "66'" in stripped or '66"' in stripped or
        "88'" in stripped or '88"' in stripped
    ):
        print(f"  L{i}: {stripped}")

print("\n=== update_traces calls ===")
for i, line in enumerate(lines, 1):
    if "update_traces" in line:
        # print block of 10 lines around it
        start = max(0, i-1)
        end = min(len(lines), i+12)
        print(f"  --- update_traces at L{i} ---")
        for j in range(start, end):
            print(f"    L{j+1}: {lines[j].rstrip()}")
        print()
