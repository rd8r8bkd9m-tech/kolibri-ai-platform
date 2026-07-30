"""Document templates — predefined structures for contracts, acts, proposals, etc."""
import re
from datetime import datetime, timezone
from typing import Dict, Optional


def render_template(content: str, variables: Dict[str, str]) -> str:
    """Replace {{variable}} placeholders with values."""
    def replacer(match):
        var_name = match.group(1).strip()
        return variables.get(var_name, match.group(0))
    
    result = re.sub(r'\{\{(\w+)\}\}', replacer, content)
    
    # Auto-fill common variables
    auto_vars = {
        'date': datetime.now(timezone.utc).strftime('%d.%m.%Y'),
        'year': str(datetime.now(timezone.utc).year),
    }
    for key, val in auto_vars.items():
        if key not in variables:
            result = result.replace('{{' + key + '}}', val)
    
    return result

TEMPLATES = {
    "contract": {
        "title": "Договор подряда",
        "type": "contract",
        "content": """<h2>ДОГОВОР ПОДРЯДА № {{contract_number}}/2026</h2>
<p><strong>г. {{city}}</strong> &nbsp; <strong>«{{date}}»</strong></p>
<p>&nbsp;</p>
<p>{{contractor_name}}, именуемое в дальнейшем «Заказчик», в лице ____________________, действующего на основании Устава, с одной стороны, и {{client_name}}, именуемое в дальнейшем «Исполнитель», с другой стороны, заключили настоящий договор о нижеследующем:</p>
<h3>1. ПРЕДМЕТ ДОГОВОРА</h3>
<p>1.1. Исполнитель обязуется выполнить работы по {{subject}}, а Заказчик обязуется принять и оплатить выполненные работы.</p>
<p>1.2. Перечень работ и материалов указан в Приложении №1 (Смета).</p>
<h3>2. СТОИМОСТЬ РАБОТ</h3>
<p>2.1. Общая стоимость работ составляет {{price}} рублей, включая НДС.</p>
<p>2.2. Аванс в размере {{advance_percent}}% уплачивается в течение {{payment_days}} банковских дней.</p>
<h3>3. СРОКИ</h3>
<p>3.1. Работы выполняются с {{start_date}} по {{end_date}}.</p>
<h3>4. ПРАВА И ОБЯЗАННОСТИ</h3>
<p>4.1. Заказчик обязуется обеспечить доступ на объект и произвести оплату.</p>
<p>4.2. Исполнитель обязуется выполнить работы в соответствии с техническим заданием.</p>
<h3>5. ГАРАНТИЙНЫЕ ОБЯЗАТЕЛЬСТВА</h3>
<p>5.1. Гарантийный срок — {{guarantee_months}} месяцев с даты подписания акта.</p>
<h3>6. РЕКВИЗИТЫ СТОРОН</h3>
<p><strong>Заказчик:</strong> {{contractor_name}}</p>
<p><strong>Исполнитель:</strong> {{client_name}}</p>""",
        "variables": ["client_name", "contractor_name", "subject", "price", "start_date", "end_date", "advance_percent", "guarantee_months", "city", "contract_number", "payment_days"],
    },
    "act": {
        "title": "Акт выполненных работ",
        "type": "act",
        "content": """<h2>АКТ ВЫПОЛНЕННЫХ РАБОТ № ____</h2>
<p><strong>г. __________</strong> &nbsp; <strong>«___» __________ 2026 г.</strong></p>
<p>&nbsp;</p>
<p>Мы, нижеподписавшиеся, представитель Заказчика ____________________, с одной стороны, и представитель Исполнителя ____________________, с другой стороны, составили настоящий акт о том, что Исполнителем выполнены следующие работы:</p>
<h3>1. ПЕРЕЧЕНЬ ВЫПОЛНЕННЫХ РАБОТ</h3>
<table>
<tr><th>№</th><th>Наименование работ</th><th>Ед. изм.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
<tr><td>1</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>2</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>3</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
<p>&nbsp;</p>
<p><strong>Итого выполнено работ на сумму: ______________ (______________) рублей.</strong></p>
<h3>2. ЗАМЕЧАНИЯ</h3>
<p>Замечания по качеству и срокам выполнения работ: ________________________________</p>
<h3>3. ЗАКЛЮЧЕНИЕ</h3>
<p>Работы выполнены в соответствии с договором № ____/2026 от «___» __________ 2026 г.</p>
<p>Настоящий акт составлен в двух экземплярах, по одному для каждой из сторон.</p>
<p>&nbsp;</p>
<p><strong>Заказчик:</strong> _______________ / _______________ /</p>
<p><strong>Исполнитель:</strong> _______________ / _______________ /</p>""",
        "variables": ["client_name", "contractor_name", "contract_number", "total"],
    },
    "proposal": {
        "title": "Коммерческое предложение",
        "type": "proposal",
        "content": """<h2>КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ</h2>
<p><strong>от «___» __________ 2026 г.</strong></p>
<p>&nbsp;</p>
<p>Уважаемый(ая) ____________________!</p>
<p>Компания ____________________ предлагает Вам следующие услуги:</p>
<h3>1. ОПИСАНИЕ УСЛУГ</h3>
<p>&nbsp;</p>
<h3>2. СТОИМОСТЬ</h3>
<table>
<tr><th>№</th><th>Услуга</th><th>Ед. изм.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
<tr><td>1</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>2</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
<p>&nbsp;</p>
<p><strong>Итого: ______________ (______________) рублей.</strong></p>
<h3>3. УСЛОВИЯ</h3>
<p>- Сроки выполнения: ______________</p>
<p>- Гарантия: ______________</p>
<p>- Оплата: ______________</p>
<h3>4. КОНТАКТЫ</h3>
<p>Телефон: ______________</p>
<p>Email: ______________</p>
<p>Адрес: ______________</p>""",
        "variables": ["client_name", "company_name"],
    },
    "report": {
        "title": "Технический отчёт",
        "type": "report",
        "content": """<h2>ТЕХНИЧЕСКИЙ ОТЧЁТ</h2>
<p><strong>г. __________</strong> &nbsp; <strong>«___» __________ 2026 г.</strong></p>
<p>&nbsp;</p>
<h3>1. ВВЕДЕНИЕ</h3>
<p>Настоящий отчёт подготовлен по результатам ________________________________.</p>
<h3>2. ОБЪЕКТ ИССЛЕДОВАНИЯ</h3>
<p>Объект: ________________________________</p>
<p>Адрес: ________________________________</p>
<h3>3. МЕТОДОЛОГИЯ</h3>
<p>&nbsp;</p>
<h3>4. РЕЗУЛЬТАТЫ</h3>
<p>&nbsp;</p>
<h3>5. ВЫВОДЫ И РЕКОМЕНДАЦИИ</h3>
<p>&nbsp;</p>
<h3>6. ПРИЛОЖЕНИЯ</h3>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p><strong>Исполнитель:</strong> _______________ / _______________ /</p>""",
        "variables": ["object_name", "address"],
    },
    "memo": {
        "title": "Служебная записка",
        "type": "memo",
        "content": """<h2>СЛУЖЕБНАЯ ЗАПИСКА</h2>
<p><strong>от «___» __________ 2026 г.</strong></p>
<p>&nbsp;</p>
<p><strong>Кому:</strong> ____________________</p>
<p><strong>От кого:</strong> ____________________</p>
<p><strong>Тема:</strong> ____________________</p>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p><strong>Подпись:</strong> _______________ / _______________ /</p>""",
        "variables": ["to", "from", "subject"],
    },
    "letter": {
        "title": "Деловое письмо",
        "type": "letter",
        "content": """<h2>ДЕЛОВОЕ ПИСЬМО</h2>
<p><strong>г. __________</strong> &nbsp; <strong>«___» __________ 2026 г.</strong></p>
<p>&nbsp;</p>
<p>Уважаемый(ая) ____________________!</p>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p>&nbsp;</p>
<p>С уважением,</p>
<p>___________________</p>
<p>___________________</p>
<p>Тел: _______________</p>""",
        "variables": ["recipient_name", "sender_name", "phone"],
    },
}


def list_templates():
    return [
        {"id": tid, "title": t["title"], "type": t["type"], "variables": t["variables"]}
        for tid, t in TEMPLATES.items()
    ]


def get_template(template_id: str):
    return TEMPLATES.get(template_id)
