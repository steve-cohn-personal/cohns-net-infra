#!/usr/bin/env python3
"""Summarize DMARC aggregate reports as a plain-English table.

These are the .xml / .xml.gz / .zip attachments that land in the `rua` mailbox
(steve@cohns.net — see the DMARC record in terraform/live/shared-services/email.tf).
Rather than read the XML by hand, this prints, per sending IP: the message count,
the disposition the receiver applied, and the DMARC-*aligned* SPF/DKIM results — then
a verdict: how many messages passed DMARC (your legitimate mail) vs failed (usually
someone forging your From: address).

    ./scripts/dmarc_report.py report.xml.gz
    ./scripts/dmarc_report.py ~/Downloads/*.zip *.xml
    cat report.xml | ./scripts/dmarc_report.py -

Stdlib only — no network, no whois lookups; just what the report itself contains.
A row passes DMARC when the aligned DKIM *or* aligned SPF result is 'pass' (that is
the DMARC rule); anything else is a fail and, under p=quarantine/reject, gets
dispositioned accordingly.
"""

import gzip
import io
import sys
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET


def load_xml(data: bytes) -> ET.Element:
    """Parse a report's bytes, transparently handling gzip and zip wrappers."""
    if data[:2] == b"\x1f\x8b":  # gzip magic
        data = gzip.decompress(data)
    elif data[:2] == b"PK":  # zip magic
        zf = zipfile.ZipFile(io.BytesIO(data))
        members = [n for n in zf.namelist() if n.lower().endswith(".xml")] or zf.namelist()
        if not members:
            raise ValueError("zip contains no report")
        data = zf.read(members[0])
    root = ET.fromstring(data)
    # Some reporters namespace the XML; drop namespaces so plain tag paths work.
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(elem, path, default=""):
    if elem is None:
        return default
    found = elem.find(path)
    return found.text.strip() if found is not None and found.text else default


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return ts or "?"


def summarize(root: ET.Element, out=sys.stdout) -> tuple[int, int, int]:
    """Print a summary of one report. Returns (total, passed, failed) message counts."""
    meta = root.find("report_metadata")
    pol = root.find("policy_published")

    org = _text(meta, "org_name", "?")
    rid = _text(meta, "report_id")
    begin, end = _text(meta, "date_range/begin"), _text(meta, "date_range/end")
    domain = _text(pol, "domain", "?")

    print(f"── {org}  ·  {domain}", file=out)
    print(f"   {_fmt_ts(begin)} → {_fmt_ts(end)}   report {rid}", file=out)
    print(
        "   published: p={p} sp={sp} pct={pct} adkim={adkim} aspf={aspf}".format(
            p=_text(pol, "p", "?"), sp=_text(pol, "sp", "-"), pct=_text(pol, "pct", "-"),
            adkim=_text(pol, "adkim", "-"), aspf=_text(pol, "aspf", "-"),
        ),
        file=out,
    )

    header = f"   {'source ip':<20} {'msgs':>5} {'disposition':<12} {'dkim':<5} {'spf':<5} {'from':<20} verdict"
    print("\n" + header, file=out)
    print("   " + "-" * (len(header) - 3), file=out)

    total = passed = failed = 0
    for rec in root.findall("record"):
        row = rec.find("row")
        ip = _text(row, "source_ip", "?")
        count = int(_text(row, "count", "0") or 0)
        disp = _text(row, "policy_evaluated/disposition", "?")
        dkim = _text(row, "policy_evaluated/dkim", "-")   # aligned result
        spf = _text(row, "policy_evaluated/spf", "-")     # aligned result
        hfrom = _text(rec, "identifiers/header_from", "")
        ok = dkim == "pass" or spf == "pass"              # the DMARC rule
        total += count
        if ok:
            passed += count
        else:
            failed += count
        print(
            f"   {ip:<20} {count:>5} {disp:<12} {dkim:<5} {spf:<5} {hfrom:<20} "
            f"{'PASS' if ok else 'FAIL (spoof?)'}",
            file=out,
        )

    verdict = f"{total} message(s): {passed} passed DMARC"
    if failed:
        verdict += f", {failed} FAILED (aligned on neither SPF nor DKIM — usually a forged From:)"
    print(f"\n   → {verdict}\n", file=out)
    return total, passed, failed


def _read(arg: str) -> bytes:
    return sys.stdin.buffer.read() if arg == "-" else open(arg, "rb").read()


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        sys.exit("usage: dmarc_report.py <report.xml|.gz|.zip> [...]   (or - for stdin)")

    grand = [0, 0, 0]
    for arg in args:
        try:
            t, p, f = summarize(load_xml(_read(arg)))
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile) as e:
            print(f"!! {arg}: could not parse — {e}\n", file=sys.stderr)
            continue
        grand[0] += t
        grand[1] += p
        grand[2] += f

    if len(args) > 1:
        print(f"= across {len(args)} reports: {grand[0]} messages, {grand[1]} passed, {grand[2]} failed")
    # Exit non-zero if any message failed, so this can gate an alert if piped.
    sys.exit(1 if grand[2] else 0)


if __name__ == "__main__":
    main()
