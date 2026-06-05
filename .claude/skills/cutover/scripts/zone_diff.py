#!/usr/bin/env python3
"""DNS zone diff. Usage: python3 zone_diff.py <before.txt> <after.txt>
Accepts zone-file-ish exports (one record per line). ERRORS on missing/changed
MX, TXT(spf/dkim/dmarc), or any record present before but absent after."""
import re, sys

CRITICAL = ("MX", "TXT")

def parse(path):
    recs = set()
    for line in open(path):
        line = line.split(";")[0].strip()
        if not line or line.startswith("$"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 3:
            name = parts[0].lower()
            rtype = next((p for p in parts if p.upper() in
                          ("A","AAAA","CNAME","MX","TXT","NS","SRV","CAA")), parts[-2].upper())
            value = " ".join(parts[parts.index(rtype)+1:]) if rtype in parts else parts[-1]
            recs.add((name, rtype.upper(), value.strip('"').lower()))
    return recs

def main():
    before, after = parse(sys.argv[1]), parse(sys.argv[2])
    missing = before - after
    added = after - before
    errors = 0
    for name, rtype, value in sorted(missing):
        crit = rtype in CRITICAL or any(k in value for k in ("spf", "dkim", "dmarc"))
        tag = "ERROR" if crit else "WARN "
        errors += crit
        print(f"[{tag}] removed: {name} {rtype} {value[:90]}")
    for name, rtype, value in sorted(added):
        print(f"[info ] added:   {name} {rtype} {value[:90]}")
    if not missing and not added:
        print("zones identical")
    print(f"\nRESULT: {'FAIL — email/auth records lost' if errors else 'PASS — no critical records lost'}")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
