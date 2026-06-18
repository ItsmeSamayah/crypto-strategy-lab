"""
Finds and replaces all 8-digit hex color transparency hacks in dashboard.py
with proper rgba() values using hex_to_rgba().
"""
import re

INPUT_FILE = "dashboard.py"

# Pattern: theme_colors['xxx'] + "22"  or  theme_colors['xxx']+"33"  etc.
# Captures the dict expression and the 2-digit alpha hex
PATTERN = re.compile(
    r"(theme_colors\[['\"][a-z_]+['\"]\])\s*\+\s*['\"]([0-9a-fA-F]{2})['\"]"
)

def hex2dec(h):
    return int(h, 16)

def alpha_from_hex(h2):
    """Convert 2-digit hex (00-ff) to alpha float 0.0-1.0, rounded to 2dp."""
    return round(hex2dec(h2) / 255, 2)

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

hits = PATTERN.findall(content)
print(f"Found {len(hits)} hex alpha hacks:")
for expr, alpha_hex in hits:
    alpha = alpha_from_hex(alpha_hex)
    print(f"  {expr} + '{alpha_hex}'  =>  hex_to_rgba({expr}, {alpha})")

def replacer(m):
    expr = m.group(1)
    alpha_hex = m.group(2)
    alpha = alpha_from_hex(alpha_hex)
    return f"hex_to_rgba({expr}, {alpha})"

new_content = PATTERN.sub(replacer, content)

# Also fix any update_traces calls that still pass 8-char hex directly
# (e.g. increasing_fillcolor='#00e67622')
DIRECT_PATTERN = re.compile(
    r"((?:increasing|decreasing)_fillcolor)\s*=\s*['\"]#([0-9a-fA-F]{6})([0-9a-fA-F]{2})['\"]"
)

direct_hits = DIRECT_PATTERN.findall(new_content)
print(f"\nFound {len(direct_hits)} direct 8-digit hex fillcolor assignments:")
for prop, rgb_hex, alpha_hex in direct_hits:
    r = hex2dec(rgb_hex[0:2])
    g = hex2dec(rgb_hex[2:4])
    b = hex2dec(rgb_hex[4:6])
    alpha = alpha_from_hex(alpha_hex)
    print(f"  {prop}='#{rgb_hex}{alpha_hex}'  =>  {prop}='rgba({r},{g},{b},{alpha})'")

def direct_replacer(m):
    prop = m.group(1)
    rgb_hex = m.group(2)
    alpha_hex = m.group(3)
    r = hex2dec(rgb_hex[0:2])
    g = hex2dec(rgb_hex[2:4])
    b = hex2dec(rgb_hex[4:6])
    alpha = alpha_from_hex(alpha_hex)
    return f"{prop}='rgba({r},{g},{b},{alpha})'"

new_content = DIRECT_PATTERN.sub(direct_replacer, new_content)

if new_content == content:
    print("\nNo changes needed — file already clean.")
else:
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("\nFile updated successfully.")

# Final syntax check
import py_compile, sys
try:
    py_compile.compile(INPUT_FILE, doraise=True)
    print("Syntax check: PASSED")
except py_compile.PyCompileError as e:
    print(f"Syntax check: FAILED — {e}")
    sys.exit(1)
