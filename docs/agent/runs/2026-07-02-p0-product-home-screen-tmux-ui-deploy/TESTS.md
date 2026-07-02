# Tests

```bash
python3 -m pytest -q tests/test_kolibri_home_screen.py
```

Result:

```text
....                                                                     [100%]
4 passed in 0.09s
```

```bash
python3 -m py_compile ops/kolibri_home_screen.py
```

Result: passed with no output.

```bash
ops/kolibri-home-screen tmux-plan
```

Result: passed; plan includes windows `Фабрика`, `События`, `Владелец`, panes
`overview`, `tasks`, `agents`, `prs`, `logs`, `blockers`, `owner`, and
`sleep 15` refresh loops.

```bash
ops/kolibri-home-screen start
tmux list-windows -t kolibri-factory-screen -F '#{window_index}:#{window_name}:#{window_panes}'
```

Result:

```text
kolibri_home_screen=started session=kolibri-factory-screen attach='tmux attach -t kolibri-factory-screen'
0:Фабрика:4
1:События:2
2:Владелец:1
```
