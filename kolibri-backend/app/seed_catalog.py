"""Seed price catalog — loads all collected data into database with regional variants."""
import json
import os
import uuid
from decimal import Decimal

REGIONS = [
    # Федеральные города
    ("Москва", "msk", 1.15), ("Санкт-Петербург", "spb", 1.10),
    ("Севастополь", "sev", 0.95),
    # Центральный ФО — города
    ("Воронеж", "vrn", 0.95), ("Ярославль", "yar", 0.95), ("Рязань", "rya", 0.93),
    ("Тула", "tul", 0.93), ("Белгород", "bel", 0.93), ("Калуга", "kal", 0.91),
    ("Курск", "krs", 0.89), ("Липецк", "lip", 0.90), ("Орёл", "orl", 0.88),
    ("Тамбов", "tam", 0.87), ("Тверь", "tve", 0.91), ("Смоленск", "smo", 0.89),
    ("Брянск", "bry", 0.90), ("Владимир", "vla", 0.92), ("Иваново", "iva", 0.88),
    ("Кострома", "kos", 0.87),
    # Северо-Западный ФО — города
    ("Мурманск", "mur", 1.25), ("Архангельск", "ark", 1.08), ("Вологда", "vog", 0.95),
    ("Калининград", "kln", 1.02), ("Псков", "psk", 0.88), ("Великий Новгород", "nov", 0.90),
    ("Петрозаводск", "pet", 1.15), ("Сыктывкар", "syr", 1.12),
    # Южный ФО — города
    ("Краснодар", "krd", 1.00), ("Ростов-на-Дону", "rnd", 0.97),
    ("Волгоград", "vlg", 0.93), ("Астрахань", "ast", 0.91),
    ("Сочи", "soc", 1.05), ("Крымск", "krm", 0.95),
    # Северо-Кавказский ФО — города
    ("Махачкала", "mcr", 0.88), ("Ставрополь", "sta", 0.90),
    ("Владикавказ", "vlk", 0.86), ("Грозный", "grz", 0.85),
    ("Нальчик", "nal", 0.87), ("Черкесск", "chr", 0.86),
    ("Магас", "mag", 0.85),
    # Приволжский ФО — города
    ("Казань", "kzn", 0.98), ("Нижний Новгород", "nnv", 0.95),
    ("Самара", "sam", 0.96), ("Саратов", "sar", 0.92),
    ("Уфа", "ufa", 0.95), ("Оренбург", "ore", 0.93),
    ("Пермь", "per", 0.96), ("Тольятти", "tlt", 0.93),
    ("Ижевск", "ijk", 0.91), ("Ульяновск", "ulv", 0.90),
    ("Пенза", "pnz", 0.89), ("Киров", "kir", 0.88),
    ("Йошкар-Ола", "yol", 0.87), ("Саранск", "sak", 0.87),
    ("Чебоксары", "che", 0.89),
    # Уральский ФО — города
    ("Екатеринбург", "ekb", 1.02), ("Челябинск", "chl", 0.97),
    ("Тюмень", "tum", 1.05), ("Курган", "krg", 0.90),
    ("Сургут", "sur", 1.10), ("Нижневартовск", "nvs", 1.12),
    ("Ноябрьск", "noy", 1.15),
    # Сибирский ФО — города
    ("Новосибирск", "nsk", 1.08), ("Омск", "omsk", 0.93),
    ("Красноярск", "krs", 1.12), ("Иркутск", "irk", 1.10),
    ("Томск", "tom", 1.05), ("Кемерово", "kem", 1.00),
    ("Барнаул", "bar", 0.97), ("Новокузнецк", "nvk", 1.02),
    ("Кызыл", "kyz", 0.95), ("Абакан", "aba", 1.05),
    ("Улан-Удэ", "ulu", 1.08), ("Чита", "chi", 1.10),
    # Дальневосточный ФО — города
    ("Хабаровск", "kha", 1.18), ("Владивосток", "vvo", 1.20),
    ("Якутск", "yak", 1.35), ("Петропавловск-Камчатский", "pkc", 1.40),
    ("Южно-Сахалинск", "uss", 1.30), ("Магадан", "mgd", 1.35),
    ("Благовещенск", "blg", 1.12), ("Комсомольск-на-Амуре", "kna", 1.15),
    ("Анадырь", "ana", 1.50),
]

MATERIAL_CATS = {
    "Электромонтаж", "HVAC", "Краски", "Водоснабжение", "Промышленные",
    "Интерьер", "Доп. материалы", "Сантехника", "Кровля", "Утепление",
    "Фасад", "Окна", "Бетон", "Металл", "Кирпич", "Сыпучие", "Цемент",
    "Блоки", "Штукатурка", "Краска", "Плитка", "Полы", "Потолки",
    "ГКЛ", "Двери", "Аренда", "Электрика", "Слаботочка",
}


def load_json_files(base_dir):
    items = []
    for fname in os.listdir(base_dir):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(base_dir, fname)) as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        items.append({
                            "code": item.get("code", ""),
                            "name": item.get("name", item.get("name_ru", "")),
                            "unit": item.get("unit", ""),
                            "price": str(item.get("price", item.get("price_rub", 0))),
                            "category": item.get("category", fname.split("_")[0]),
                            "source": item.get("source", fname),
                        })
        except Exception:
            continue
    return items


def seed_catalog(db_session, base_dir):
    from app.models import CatalogItemDB
    if db_session.query(CatalogItemDB).count() > 0:
        return

    base_items = load_json_files(base_dir)
    count = 0

    for item in base_items:
        db_session.add(CatalogItemDB(
            id=str(uuid.uuid4()), code=item["code"], name=item["name"],
            unit=item["unit"], price=item["price"], category=item["category"],
            source=item["source"], region="Базовая", currency="RUB", is_active=True,
        ))
        count += 1

    for item in base_items:
        try:
            bp = Decimal(item["price"])
        except Exception:
            continue
        if bp <= 0:
            continue
        for city, code, coeff in REGIONS:
            rp = (bp * Decimal(str(coeff))).quantize(Decimal("0.01"))
            db_session.add(CatalogItemDB(
                id=str(uuid.uuid4()),
                code=f"{item['code']}-{code}",
                name=f"{item['name']} ({city})",
                unit=item["unit"], price=str(rp), category=item["category"],
                source=f"{item['source']} × {coeff}", region=city,
                currency="RUB", is_active=True,
            ))
            count += 1

    db_session.commit()
    print(f"Seeded {count} catalog items")
