#!/usr/bin/env python3
"""Tests for dmarc_report.py. Run: python3 scripts/test_dmarc_report.py"""

import gzip
import io
import unittest

import dmarc_report as dr

# A real-shaped Google aggregate report: the two spoof IPs from an actual cohns.net
# report (both fail SPF+DKIM), plus one legitimate Google-signed row that passes.
REPORT = b"""<?xml version="1.0"?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <report_id>10539656839091403633</report_id>
    <date_range><begin>1785888000</begin><end>1785974399</end></date_range>
  </report_metadata>
  <policy_published>
    <domain>cohns.net</domain>
    <adkim>r</adkim><aspf>r</aspf><p>quarantine</p><sp>quarantine</sp><pct>100</pct>
  </policy_published>
  <record>
    <row><source_ip>84.54.71.157</source_ip><count>1</count>
      <policy_evaluated><disposition>quarantine</disposition><dkim>fail</dkim><spf>fail</spf></policy_evaluated>
    </row>
    <identifiers><header_from>cohns.net</header_from></identifiers>
    <auth_results><spf><domain>cohns.net</domain><result>softfail</result></spf></auth_results>
  </record>
  <record>
    <row><source_ip>37.150.241.69</source_ip><count>1</count>
      <policy_evaluated><disposition>quarantine</disposition><dkim>fail</dkim><spf>fail</spf></policy_evaluated>
    </row>
    <identifiers><header_from>cohns.net</header_from></identifiers>
    <auth_results><spf><domain>cohns.net</domain><result>softfail</result></spf></auth_results>
  </record>
  <record>
    <row><source_ip>209.85.220.41</source_ip><count>5</count>
      <policy_evaluated><disposition>none</disposition><dkim>pass</dkim><spf>pass</spf></policy_evaluated>
    </row>
    <identifiers><header_from>cohns.net</header_from></identifiers>
    <auth_results>
      <dkim><domain>cohns.net</domain><result>pass</result><selector>google</selector></dkim>
      <spf><domain>cohns.net</domain><result>pass</result></spf>
    </auth_results>
  </record>
</feedback>"""


class Counts(unittest.TestCase):
    def _summ(self, data):
        buf = io.StringIO()
        return dr.summarize(dr.load_xml(data), out=buf), buf.getvalue()

    def test_pass_fail_totals(self):
        (total, passed, failed), _ = self._summ(REPORT)
        self.assertEqual((total, passed, failed), (7, 5, 2))  # 1+1+5 msgs; the Google row (5) passes

    def test_output_marks_spoof_and_pass(self):
        _, text = self._summ(REPORT)
        self.assertIn("84.54.71.157", text)
        self.assertIn("FAIL (spoof?)", text)
        self.assertIn("PASS", text)
        self.assertIn("2 FAILED", text)

    def test_dmarc_passes_on_either_mechanism(self):
        # A row that fails DKIM but passes SPF still passes DMARC.
        xml = REPORT.replace(b"<dkim>pass</dkim><spf>pass</spf>", b"<dkim>fail</dkim><spf>pass</spf>")
        (_, passed, failed), _ = self._summ(xml)
        self.assertEqual((passed, failed), (5, 2))  # the 5-count row still passes on SPF alone


class Wrappers(unittest.TestCase):
    def test_plain_xml(self):
        self.assertEqual(dr.load_xml(REPORT).find("policy_published/domain").text, "cohns.net")

    def test_gzip(self):
        root = dr.load_xml(gzip.compress(REPORT))
        self.assertEqual(root.find("report_metadata/org_name").text, "google.com")

    def test_namespaced_xml_is_handled(self):
        ns = b'<feedback xmlns="http://dmarc.org/dmarc-xml/0.1"><policy_published><domain>x.net</domain></policy_published></feedback>'
        self.assertEqual(dr.load_xml(ns).find("policy_published/domain").text, "x.net")


class ExitCode(unittest.TestCase):
    def test_main_exits_nonzero_when_failures(self):
        import os
        import tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=".xml", delete=False) as f:
            f.write(REPORT)
            path = f.name
        try:
            with self.assertRaises(SystemExit) as cm:
                dr.main([path])
            self.assertEqual(cm.exception.code, 1)  # there were failures
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
