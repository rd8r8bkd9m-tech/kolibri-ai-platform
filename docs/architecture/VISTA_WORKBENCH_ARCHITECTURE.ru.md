# Vista Workbench Architecture

Vista OS работает как single-window SPA/workbench. UI не содержит страниц. Все рабочие поверхности являются окнами, sheets или kiosk cards.

```text
chat command → intent → capability policy → allowed components → window manager → workbench render
```

Клиентские роли не получают административные компоненты даже в disabled-виде: они не отрисовываются вообще.
