def post_init_hook(env):
    """Move OGRN values stored by the l10n_ru chain into `coop_ogrn`.

    Before this module the chain kept OGRN in its own columns of res_partner
    (`ogrn`, `company_registry`). They stay in the table as dead columns; the
    values are copied once, where the platform field is still empty.
    """
    cr = env.cr
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'res_partner' AND column_name IN ('ogrn', 'company_registry')")
    legacy = [row[0] for row in cr.fetchall()]
    for column in legacy:
        cr.execute(
            'UPDATE res_partner SET coop_ogrn = LEFT("%s", 15) '
            'WHERE COALESCE(coop_ogrn, \'\') = \'\' AND COALESCE("%s", \'\') != \'\'' % (column, column))
