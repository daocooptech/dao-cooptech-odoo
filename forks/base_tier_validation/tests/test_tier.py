# Copyright 2024 DOB
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo_test_helper import FakeModelLoader

from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase

from .tier_validation_tester import (
    TierDefinition,
    TierValidationTester,
)


class TestTierDefinition(TransactionCase):
    """Tests for base_tier_validation: TierDefinition creation and workflow.

    Validates: Requirements 8.1, 8.2, 8.3, 8.4
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        cls.loader.update_registry((TierValidationTester, TierDefinition))

        cls.test_model = cls.env[TierValidationTester._name]
        cls.tester_model = cls.env["ir.model"].search(
            [("model", "=", TierValidationTester._name)]
        )

        # Grant access to the fake model
        cls.env["ir.model.access"].create(
            {
                "name": "access tier.validation.tester",
                "model_id": cls.tester_model.id,
                "perm_read": 1,
                "perm_write": 1,
                "perm_create": 1,
                "perm_unlink": 1,
            }
        )

        # Minimal form view to avoid auto-view issues
        cls.env["ir.ui.view"].create(
            {
                "model": TierValidationTester._name,
                "name": "test_tier_tester_form",
                "arch": """<form>
                    <header>
                        <button name="action_confirm" type="object" string="Confirm" />
                        <field name="state" widget="statusbar" />
                    </header>
                    <sheet>
                        <field name="test_field" />
                    </sheet>
                </form>""",
            }
        )

        # Users: reviewer (admin) and requester (regular)
        cls.reviewer = new_test_user(
            cls.env,
            name="Reviewer",
            login="tier_reviewer",
            groups="base.group_system",
        )
        cls.requester = new_test_user(
            cls.env,
            name="Requester",
            login="tier_requester",
        )

        cls.tier_def_obj = cls.env["tier.definition"]

    @classmethod
    def tearDownClass(cls):
        cls.loader.restore_registry()
        super().tearDownClass()

    def test_01_create_tier_definition(self):
        """WHEN a TierDefinition is created for a model with approval levels,
        base_tier_validation SHALL create the record without errors.

        Validates: Requirement 8.1
        """
        tier_def = self.tier_def_obj.create(
            {
                "model_id": self.tester_model.id,
                "review_type": "individual",
                "reviewer_id": self.reviewer.id,
                "definition_domain": "[]",
                "sequence": 10,
            }
        )
        self.assertTrue(tier_def.id, "TierDefinition should be created without errors")
        self.assertEqual(tier_def.model_id, self.tester_model)
        self.assertEqual(tier_def.reviewer_id, self.reviewer)

    def test_02_request_validation_creates_tier_reviews(self):
        """WHEN a document is submitted for approval,
        base_tier_validation SHALL create TierReview records for each level.

        Validates: Requirement 8.2
        """
        # Create two tier definitions (two approval levels)
        self.tier_def_obj.create(
            {
                "model_id": self.tester_model.id,
                "review_type": "individual",
                "reviewer_id": self.reviewer.id,
                "definition_domain": "[('test_field', '>', 0.0)]",
                "sequence": 10,
            }
        )
        self.tier_def_obj.create(
            {
                "model_id": self.tester_model.id,
                "review_type": "individual",
                "reviewer_id": self.reviewer.id,
                "definition_domain": "[('test_field', '>', 0.0)]",
                "sequence": 20,
            }
        )

        record = self.test_model.create({"test_field": 1.0})
        self.assertFalse(record.review_ids, "No reviews before request")

        reviews = record.with_user(self.requester).request_validation()

        self.assertTrue(reviews, "Reviews should be created after request_validation")
        self.assertEqual(
            len(reviews),
            2,
            "One TierReview should be created per approval level",
        )

    def test_03_approve_all_tiers_sets_validated_status(self):
        """WHEN all approval levels are approved,
        base_tier_validation SHALL set the document validation_status to 'validated'.

        Validates: Requirement 8.3
        """
        self.tier_def_obj.create(
            {
                "model_id": self.tester_model.id,
                "review_type": "individual",
                "reviewer_id": self.reviewer.id,
                "definition_domain": "[('test_field', '>', 0.0)]",
                "sequence": 10,
            }
        )

        record = self.test_model.create({"test_field": 1.0})
        record.with_user(self.requester).request_validation()

        record_as_reviewer = record.with_user(self.reviewer)
        record_as_reviewer.validate_tier()

        self.assertEqual(
            record.validation_status,
            "validated",
            "validation_status should be 'validated' after all tiers approved",
        )

    def test_04_reject_tier_sets_rejected_status(self):
        """IF one approval level is rejected,
        base_tier_validation SHALL set the document validation_status to 'rejected'.

        Validates: Requirement 8.4
        """
        self.tier_def_obj.create(
            {
                "model_id": self.tester_model.id,
                "review_type": "individual",
                "reviewer_id": self.reviewer.id,
                "definition_domain": "[('test_field', '>', 0.0)]",
                "sequence": 10,
            }
        )

        record = self.test_model.create({"test_field": 1.0})
        record.with_user(self.requester).request_validation()

        record_as_reviewer = record.with_user(self.reviewer)
        record_as_reviewer.reject_tier()

        self.assertEqual(
            record.validation_status,
            "rejected",
            "validation_status should be 'rejected' after a tier is rejected",
        )
