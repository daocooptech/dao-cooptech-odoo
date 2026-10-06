# -*- coding: utf-8 -*-
"""
Tests for docx_report_generation — DOCX report generation from templates.

Validates: Requirements 13.2, 13.3
"""
import base64
import io
import zipfile

from odoo.tests.common import TransactionCase
from odoo.tests import tagged


def _make_docx_with_template(body_text="Hello World"):
    """
    Build a minimal valid DOCX file with the given body text and return it as base64 bytes.
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
            "<w:body><w:p><w:r><w:t>"
            + body_text
            + "</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "</Relationships>",
        )
    buf.seek(0)
    return base64.b64encode(buf.read())


@tagged("post_install", "-at_install")
class TestDocxGeneration(TransactionCase):
    """
    Tests for docx_report_generation — generating DOCX reports from templates.

    Validates: Requirements 13.2, 13.3
    """

    def setUp(self):
        super().setUp()
        # Create a minimal ir.actions.report record of type docx-docx
        self.ir_model = self.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        self.partner = self.env["res.partner"].create({"name": "Test Partner"})

        # Template with a simple static body (no Jinja2 variables)
        self.valid_template_b64 = _make_docx_with_template("Hello World")

        # Template with an invalid/undefined Jinja2 variable reference
        # docxtpl uses {{ variable }} syntax; an undefined variable with strict mode raises
        self.invalid_template_b64 = _make_docx_with_template(
            "{{ undefined_variable_xyz | raise_exception }}"
        )

        self.report = self.env["ir.actions.report"].create(
            {
                "name": "Test DOCX Generation Report",
                "model": "res.partner",
                "report_type": "docx-docx",
                "report_docx_template": self.valid_template_b64,
            }
        )

    # ------------------------------------------------------------------
    # Requirement 13.2 — generation returns non-empty binary content
    # ------------------------------------------------------------------

    def test_render_docx_template_returns_nonempty_binary(self):
        """
        Req 13.2 — _render_docx_template with a valid DOCX template and a
        res.partner record returns non-empty binary content (BytesIO with data).
        """
        values = {
            "docs": self.partner,
            "report_type": "docx",
        }
        result = self.report._render_docx_template(
            self.valid_template_b64, values=values
        )
        content = result.getvalue()
        self.assertTrue(
            content,
            "_render_docx_template should return non-empty binary content",
        )
        self.assertGreater(
            len(content),
            0,
            "Generated DOCX content must have non-zero length",
        )

    # ------------------------------------------------------------------
    # Requirement 13.3 — invalid Jinja2 variables raise an exception
    # ------------------------------------------------------------------

    def test_render_docx_template_invalid_jinja2_raises(self):
        """
        Req 13.3 — _render_docx_template with a DOCX template containing an
        invalid/undefined Jinja2 expression raises an exception describing the
        template error.
        """
        # Build a template that uses an invalid Jinja2 filter which does not exist
        invalid_b64 = _make_docx_with_template("{{ partner.nonexistent_method() }}")
        values = {
            "docs": self.partner,
            "report_type": "docx",
        }
        with self.assertRaises(Exception) as ctx:
            self.report._render_docx_template(invalid_b64, values=values)
        # The exception message should contain some description of the error
        error_msg = str(ctx.exception)
        self.assertTrue(
            error_msg,
            "Exception raised for invalid Jinja2 template should have a non-empty message",
        )
