"""
Tests for Contract_Model (l10n_ru_contract).

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10
"""
from odoo.tests.common import TransactionCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_profile(env):
    """Return an existing contract.profile or create a minimal one."""
    profile = env['contract.profile'].search([], limit=1)
    if not profile:
        profile = env['contract.profile'].create({'name': 'Test Profile'})
    return profile


def _get_or_create_partner(env):
    """Return an existing external partner or create one."""
    partner = env['res.partner'].search(
        [('is_company', '=', True), ('id', 'not in', env.companies.ids)], limit=1
    )
    if not partner:
        partner = env['res.partner'].create({'name': 'Test Partner', 'is_company': True})
    return partner


def _make_contract(env, **kwargs):
    """Create a minimal PartnerContractCustomer record."""
    profile = _get_or_create_profile(env)
    partner = _get_or_create_partner(env)
    vals = {
        'date_start': '2024-01-01',
        'date_end': '2024-12-31',
        'type': 'customer',
        'profile_id': profile.id,
        'partner_id': partner.id,
        'partner_type': 'company',
        'company_id': env.company.id,
    }
    vals.update(kwargs)
    return env['partner.contract.customer'].create(vals)


# ---------------------------------------------------------------------------
# TestContractCreate
# ---------------------------------------------------------------------------

class TestContractCreate(TransactionCase):
    """Validates: Requirement 4.1 — unique contract number assigned via sequence on create."""

    def test_create_assigns_unique_name_via_sequence(self):
        """Req 4.1 — creating a customer contract assigns a non-empty unique name."""
        contract1 = _make_contract(self.env)
        contract2 = _make_contract(self.env)

        self.assertTrue(contract1.name, "Contract 1 should have a name assigned")
        self.assertTrue(contract2.name, "Contract 2 should have a name assigned")
        self.assertNotEqual(
            contract1.name, contract2.name,
            "Each contract should receive a unique number from the sequence"
        )

    def test_create_supplier_contract_assigns_name(self):
        """Req 4.1 — creating a supplier contract also assigns a name via sequence."""
        contract = _make_contract(self.env, type='supplier')
        self.assertTrue(contract.name, "Supplier contract should have a name assigned")


# ---------------------------------------------------------------------------
# TestContractStates
# ---------------------------------------------------------------------------

class TestContractStates(TransactionCase):
    """Validates: Requirements 4.2, 4.3 — state transitions."""

    def setUp(self):
        super().setUp()
        self.contract = _make_contract(self.env)

    def test_contract_action_confirm_draft_to_progress(self):
        """Req 4.2 — contract_action_confirm moves draft → progress."""
        self.assertEqual(self.contract.state, 'draft')
        self.contract.contract_action_confirm()
        self.assertEqual(
            self.contract.state, 'progress',
            "contract_action_confirm should move draft contract to progress"
        )

    def test_contract_action_confirm_progress_to_signed(self):
        """Req 4.2 — second call to contract_action_confirm moves progress → signed."""
        self.contract.contract_action_confirm()  # draft → progress
        self.contract.contract_action_confirm()  # progress → signed
        self.assertEqual(
            self.contract.state, 'signed',
            "Second contract_action_confirm should move progress contract to signed"
        )

    def test_contract_in_draft_returns_to_draft(self):
        """Req 4.3 — contract_in_draft moves any state back to draft."""
        self.contract.contract_action_confirm()  # draft → progress
        self.assertEqual(self.contract.state, 'progress')

        self.contract.contract_in_draft()
        self.assertEqual(
            self.contract.state, 'draft',
            "contract_in_draft should return contract to draft state"
        )

    def test_contract_in_draft_from_signed(self):
        """Req 4.3 — contract_in_draft from signed state returns to draft."""
        self.contract.contract_action_confirm()  # draft → progress
        self.contract.contract_action_confirm()  # progress → signed
        self.assertEqual(self.contract.state, 'signed')

        self.contract.contract_in_draft()
        self.assertEqual(
            self.contract.state, 'draft',
            "contract_in_draft should return signed contract to draft"
        )


# ---------------------------------------------------------------------------
# TestContractHelpers
# ---------------------------------------------------------------------------

class TestContractHelpers(TransactionCase):
    """Validates: Requirements 4.4–4.10 — helper methods on the contract model."""

    def setUp(self):
        super().setUp()
        self.contract = _make_contract(self.env, date_start='2024-01-15')

    def test_get_dateend_returns_date_11_months_later(self):
        """Req 4.4 — get_dateend returns a date 11 months after date_start."""
        result = self.contract.get_dateend()
        self.assertTrue(result, "get_dateend should return a non-empty string")
        # date_start = 2024-01-15, +11 months = 2024-12-15
        self.assertIn('2024-12-15', result,
                      "get_dateend should return date 11 months after date_start")

    def test_initials_full_name(self):
        """Req 4.5 — initials('Иванов Иван Иванович') returns 'Иванов И.И.'"""
        result = self.contract.initials('Иванов Иван Иванович')
        self.assertEqual(result, 'Иванов И.И.',
                         "initials should format full name as 'Фамилия И.О.'")

    def test_initials_empty_string(self):
        """Req 4.5 — initials('') returns empty string."""
        result = self.contract.initials('')
        self.assertFalse(result, "initials with empty string should return falsy value")

    def test_ru_date_returns_russian_format(self):
        """Req 4.6 — ru_date returns date in Russian format with quoted day."""
        result = self.contract.ru_date('2024-03-15')
        self.assertTrue(result, "ru_date should return a non-empty string")
        self.assertIn('2024', result, "ru_date result should contain the year")
        self.assertIn('15', result, "ru_date result should contain the day")

    def test_rubles_returns_string_with_rubles_word(self):
        """Req 4.7 — rubles(1500.50) returns string containing a rubles word."""
        result = self.contract.rubles(1500.50)
        self.assertTrue(result, "rubles should return a non-empty string")
        has_rubles_word = any(
            word in result for word in ('рублей', 'рубля', 'рубль')
        )
        self.assertTrue(has_rubles_word,
                        "rubles result should contain 'рублей', 'рубля', or 'рубль'")

    def test_rubles_1500_50_exact(self):
        """Req 4.7 — rubles(1500.50) returns expected Russian text."""
        result = self.contract.rubles(1500.50)
        self.assertIn('тысяча', result, "1500 should produce 'тысяча' in result")
        self.assertIn('пятьсот', result, "1500 should produce 'пятьсот' in result")
        self.assertIn('копеек', result, "0.50 kopecks should appear in result")

    def test_numeral_choose_plural_1_returns_rubly(self):
        """Req 4.8 — numeral_choose_plural(1, ...) returns 'рубль'."""
        result = self.contract.numeral_choose_plural(1, ('рубль', 'рубля', 'рублей'))
        self.assertEqual(result, 'рубль',
                         "numeral_choose_plural(1) should return first variant 'рубль'")

    def test_numeral_choose_plural_11_returns_rubley(self):
        """Req 4.9 — numeral_choose_plural(11, ...) returns 'рублей'."""
        result = self.contract.numeral_choose_plural(11, ('рубль', 'рубля', 'рублей'))
        self.assertEqual(result, 'рублей',
                         "numeral_choose_plural(11) should return third variant 'рублей'")

    def test_numeral_choose_plural_2_returns_rublya(self):
        """numeral_choose_plural(2) returns second variant 'рубля'."""
        result = self.contract.numeral_choose_plural(2, ('рубль', 'рубля', 'рублей'))
        self.assertEqual(result, 'рубля',
                         "numeral_choose_plural(2) should return second variant 'рубля'")

    def test_check_positive_negative_raises_value_error(self):
        """Req 4.10 — check_positive with negative number raises ValueError."""
        with self.assertRaises(ValueError):
            self.contract.check_positive(-1)

    def test_check_positive_zero_does_not_raise(self):
        """check_positive(0) should not raise (non-strict mode)."""
        try:
            self.contract.check_positive(0)
        except ValueError:
            self.fail("check_positive(0) should not raise ValueError in non-strict mode")

    def test_check_positive_positive_does_not_raise(self):
        """check_positive with positive number should not raise."""
        try:
            self.contract.check_positive(100)
        except ValueError:
            self.fail("check_positive(100) should not raise ValueError")
