from . import models
from . import wizards


def post_init_load_chart(env):
    """Загрузить типовой план счетов 94н для всех существующих компаний."""
    Wizard = env['rsbu.account.load.wizard']
    for company in env['res.company'].search([]):
        Wizard.create({'company_id': company.id}).action_load()
