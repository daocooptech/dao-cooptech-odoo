# Copyright 2024 DOB
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo.tests.common import TransactionCase


class TestUserRoleCron(TransactionCase):
    """Tests for the scheduled role synchronization cron job.

    Validates: Requirement 7.3
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, no_reset_password=True)
        )
        cls.role_model = cls.env["res.users.role"]
        cls.user_model = cls.env["res.users"]

        cls.group_user = cls.env.ref("base.group_user")
        cls.group_no_one = cls.env.ref("base.group_no_one")

        cls.role = cls.role_model.create(
            {
                "name": "CRON_TEST_ROLE",
                "implied_ids": [(6, 0, [cls.group_user.id, cls.group_no_one.id])],
            }
        )

        cls.user1 = cls.user_model.create(
            {"name": "Cron Test User 1", "login": "cron_test_user_1"}
        )
        cls.user2 = cls.user_model.create(
            {"name": "Cron Test User 2", "login": "cron_test_user_2"}
        )

    def test_cron_update_users_syncs_group_membership(self):
        """WHEN the role sync cron is called, group membership is updated
        for all users with roles.

        Validates: Requirement 7.3
        """
        # Assign the role to both users
        self.user1.write({"role_line_ids": [(0, 0, {"role_id": self.role.id})]})
        self.user2.write({"role_line_ids": [(0, 0, {"role_id": self.role.id})]})

        expected_groups = set(
            self.role.group_id.ids
            + self.role.implied_ids.ids
            + self.role.trans_implied_ids.ids
        )

        # Manually clear groups to simulate a desync state
        for user in (self.user1, self.user2):
            super(type(user), user).write({"group_ids": [(5,)]})

        # Verify groups are cleared
        self.assertFalse(
            expected_groups.issubset(set(self.user1.group_ids.ids)),
            "Groups should be cleared before cron runs",
        )

        # Run the cron
        self.role_model.cron_update_users()

        # Verify groups are restored for both users
        for user in (self.user1, self.user2):
            user_group_ids = set(user.group_ids.ids)
            self.assertTrue(
                expected_groups.issubset(user_group_ids),
                f"User {user.name} should have all role groups after cron sync",
            )
