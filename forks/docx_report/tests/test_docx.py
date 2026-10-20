"""
Tests for docx_report — DOCX template loading.

Validates: Requirement 13.1
"""
import base64
import io
import zipfile

from odoo.tests.common import TransactionCase
from odoo.tests import tagged


def _make_minimal_docx():
    """
    Build a minimal valid DOCX (ZIP) file in memory and return it as base64.

    A DOCX is a ZIP archive containing at minimum:
      - [Content_Types].xml
      - word/document.xml
      - _rels/.rels
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml"'
            ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
            ' Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "</Relationships>",
        )
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


@tagged("post_install", "-at_install")
class TestDocxReport(TransactionCase):
    """
    Tests for docx.template — DOCX template loading.

    Validates: Requirement 13.1
    """

    def setUp(self):
        super().setUp()
        # Resolve the ir.model record for res.partner (a simple, always-present model)
        self.ir_model = self.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        self.docx_b64 = _make_minimal_docx()

    # ------------------------------------------------------------------
    # Requirement 13.1 — loading a DOCX template saves without errors
    # ------------------------------------------------------------------

    def test_create_docx_template_without_file_saves_ok(self):
        """
        Req 13.1 — creating a docx.template record without a template file
        (file uploaded later by the user) saves without errors.
        """
        template = self.env["docx.template"].create(
            {
                "name": "Test DOCX Template (no file)",
                "report_type": "docx-docx",
                "model": "res.partner",
                "docx_output_type": "docx",
                "docx_model_id": self.ir_model.id,
                "global_template": True,
            }
        )
        self.assertTrue(template.id, "docx.template record should be created with a valid id")
        self.assertEqual(template.name, "Test DOCX Template (no file)")
        self.assertEqual(template.model, "res.partner")

    def test_load_docx_template_file_saves_ok(self):
        """
        Req 13.1 — uploading a DOCX binary into report_docx_template and saving
        the docx.template record completes without errors.
        """
        template = self.env["docx.template"].create(
            {
                "name": "Test DOCX Template (with file)",
                "report_type": "docx-docx",
                "model": "res.partner",
                "docx_output_type": "docx",
                "docx_model_id": self.ir_model.id,
                "global_template": True,
                "report_docx_template": self.docx_b64,
                "report_docx_template_filename": "test_template.docx",
            }
        )
        self.assertTrue(template.id, "docx.template record should be created with a valid id")
        self.assertTrue(
            template.report_docx_template,
            "report_docx_template field should contain the uploaded binary",
        )
        self.assertEqual(
            template.report_docx_template_filename,
            "test_template.docx",
            "Filename should be stored correctly",
        )

    def test_write_docx_template_file_saves_ok(self):
        """
        Req 13.1 — writing a DOCX binary to an existing docx.template record
        via write() completes without errors.
        """
        template = self.env["docx.template"].create(
            {
                "name": "Test DOCX Template (write)",
                "report_type": "docx-docx",
                "model": "res.partner",
                "docx_output_type": "docx",
                "docx_model_id": self.ir_model.id,
            }
        )
        # Now upload the template file via write
        template.write(
            {
                "report_docx_template": self.docx_b64,
                "report_docx_template_filename": "updated_template.docx",
            }
        )
        self.assertTrue(
            template.report_docx_template,
            "report_docx_template should be set after write()",
        )
