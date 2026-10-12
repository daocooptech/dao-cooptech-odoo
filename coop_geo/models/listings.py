from odoo import models

# Объявления с собственным городом. Сделки, учебные заведения и разделы
# организаций — не объявления; у фермы и внешнеторгового договора город
# берётся из связанной записи, и адрес у них — её адрес.
LISTING_MODELS = [
    'coop.auction', 'coop.barter.offer', 'coop.community', 'coop.crypto.offer',
    'coop.event', 'coop.groupbuy', 'coop.miner', 'coop.mining.offer',
    'coop.program', 'coop.project', 'coop.resource', 'coop.skill.offer',
    'coop.vacancy', 'coop.warehouse', 'coop.warehouse.offer',
]


class CoopAuction(models.Model):
    _inherit = ['coop.auction', 'coop.geo.mixin']


class CoopBarterOffer(models.Model):
    _inherit = ['coop.barter.offer', 'coop.geo.mixin']


class CoopCommunity(models.Model):
    _inherit = ['coop.community', 'coop.geo.mixin']


class CoopCryptoOffer(models.Model):
    _inherit = ['coop.crypto.offer', 'coop.geo.mixin']


class CoopEvent(models.Model):
    _inherit = ['coop.event', 'coop.geo.mixin']


class CoopGroupbuy(models.Model):
    _inherit = ['coop.groupbuy', 'coop.geo.mixin']


class CoopMiner(models.Model):
    _inherit = ['coop.miner', 'coop.geo.mixin']


class CoopMiningOffer(models.Model):
    _inherit = ['coop.mining.offer', 'coop.geo.mixin']


class CoopProgram(models.Model):
    _inherit = ['coop.program', 'coop.geo.mixin']


class CoopProject(models.Model):
    _inherit = ['coop.project', 'coop.geo.mixin']


class CoopResource(models.Model):
    _inherit = ['coop.resource', 'coop.geo.mixin']


class CoopSkillOffer(models.Model):
    _inherit = ['coop.skill.offer', 'coop.geo.mixin']


class CoopVacancy(models.Model):
    _inherit = ['coop.vacancy', 'coop.geo.mixin']


class CoopWarehouse(models.Model):
    _inherit = ['coop.warehouse', 'coop.geo.mixin']


class CoopWarehouseOffer(models.Model):
    _inherit = ['coop.warehouse.offer', 'coop.geo.mixin']
