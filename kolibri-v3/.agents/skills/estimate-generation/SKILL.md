# Estimate Generation Skill

This skill guides the AI through generating construction estimates.

## Process

### 1. Intake
When user requests an estimate, gather:
- **Work type**: штукатурка, бетонные работы, электрика, etc.
- **Area/volume**: square meters, cubic meters, etc.
- **Location**: city/region for pricing
- **Details**: thickness, materials, special requirements

### 2. Research
Use tools to gather data:
```
search_prices(query="штукатурка стен", region="Москва")
search_normative(query="ГЭСН штукатурка")
```

### 3. Structure
Create estimate with these sections:

```json
{
  "title": "Смета на штукатурные работы",
  "sections": [
    {
      "name": "Подготовительные работы",
      "positions": [
        {
          "code": "ГЭСН 15-01-001-01",
          "name": "Очистка поверхности стен",
          "unit": "м2",
          "volume": 100,
          "unit_price": 90.00,
          "total": 9000.00,
          "source": "FGIS CS / reference"
        }
      ]
    }
  ],
  "overhead_pct": 15,
  "profit_pct": 8,
  "total_sum": 0
}
```

### 4. Validation
Before presenting:
- Check all prices have sources
- Verify arithmetic (volume × price = total)
- Ensure overhead and profit are applied
- Cross-check with reference prices

### 5. Presentation
Format the estimate clearly:
- Group by work type
- Show unit prices and totals
- Include source references
- Offer to create document pack

## Price Sources (priority order)

1. **FGIS CS** — official federal prices (search_prices tool)
2. **Reference snapshot** — versioned fallback prices
3. **User-provided** — prices from user's documents

## Common Work Types

| Work Type | Typical Units | Key Parameters |
|-----------|---------------|----------------|
| Штукатурка | м2 | толщина слоя, тип смеси |
| Бетонные работы | м3 | марка бетона, армирование |
| Электрика | точка/м | мощность, тип проводки |
| Сантехника | точка/м | тип труб, диаметр |
| Кровля | м2 | тип покрытия, уклон |
| Фундамент | м3/м2 | тип, глубина |

## Document Pack

After estimate is approved, offer to create:
1. **КП (Коммерческое предложение)** — for client presentation
2. **Договор (Contract)** — formal agreement
3. **Акт (Act)** — work completion certificate
4. **Счёт (Invoice)** — payment request

Each document uses the estimate data as source of truth.
