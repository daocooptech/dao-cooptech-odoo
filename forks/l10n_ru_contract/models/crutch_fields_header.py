ENTITY_CONTRACT_HEADER = """
<b>{{object.company_id.partner_id.name}}</b>,
именуемое в дальнейшем  <b>«Поставщик»</b>, в лице 
{{(object.company_id.chief_id.partner_id.function or '').lower()}} 
{{(object.name_dirprint1 or '').title()}},
 действующего на основании ОГРНИП № {{object.company_id.company_registry or ''}}, с одной стороны, и <b>{{object.partner_id.name or ''}}</b>, 
именуемое в дальнейшем  <b>«Покупатель»</b>, в лице 
{{(object.get_function_partner1(object.partner_id.id) or '').lower()}}
{{(object.name_print1 or '').title()}}, действующего на основании устава общества, с другой стороны, вместе именуемые в дальнейшем <b>«Стороны»</b> заключили
настоящий Договор о нижеследующем:
        """
IP_CONTACT_HEADER = """
<b>{{object.company_id.partner_id.name}}</b>,
именуемое в дальнейшем  <b>«Поставщик»</b>, в лице 
{{(object.company_id.chief_id.partner_id.function or '').lower()}} 
{{(object.name_dirprint1 or '').title()}},
 действующего на основании ОГРНИП № {{object.company_id.company_registry or ''}}, с одной стороны, и <b>{{object.partner_id.name or ''}}</b>, 
именуемое в дальнейшем  <b>«Покупатель»</b>, в лице 
{{(object.get_function_partner1(object.partner_id.id) or '').lower()}}
{{(object.name_print1 or '').title()}}, действующего на основании ОГРНИП №{{object.partner_id.ogrn or ''}},
 с другой стороны, вместе именуемые в дальнейшем <b>«Стороны»</b> заключили
настоящий Договор о нижеследующем:
"""

INDIVIDUAL_CONTRACT_HEADER = """
<b>{{object.company_id.partner_id.name}}</b>,
именуемое в дальнейшем  <b>«Поставщик»</b>, в лице 
{{(object.company_id.chief_id.partner_id.function or '').lower()}} 
{{(object.name_dirprint1 or '').title()}},
 действующего на основании ОГРНИП № {{object.company_id.company_registry or ''}}, с одной стороны, и <b>{{object.partner_id.name or ''}}</b>, 
именуемое в дальнейшем  <b>«Покупатель»</b>, вместе именуемые в дальнейшем <b>«Стороны»</b> заключили
настоящий Договор о нижеследующем:
        """
