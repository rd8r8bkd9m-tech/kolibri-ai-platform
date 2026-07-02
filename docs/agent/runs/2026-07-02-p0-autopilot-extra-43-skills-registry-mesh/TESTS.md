# TESTS

Verification performed:

```bash
git status --short --branch
rg -n "master canvas|canvas|skills registry|professional memory|memory task|remote sync|sync plan" docs ops README.md
rg -n "skill|skills|registry|memory|professional|памят|профессион" docs/superfactory/Kolibri_All_Prompts.md docs/agent/dispatcher/OWNER_CANONICAL_INSTRUCTIONS.md docs/agent/dispatcher/FACTORY_STATUS.md docs/agent/intelligence docs/agent/global-intelligence
sed -n '1880,2008p' docs/superfactory/Kolibri_All_Prompts.md
sed -n '2008,2148p' docs/superfactory/Kolibri_All_Prompts.md
sed -n '2238,2298p' docs/superfactory/Kolibri_All_Prompts.md
sed -n '2600,2695p' docs/superfactory/Kolibri_All_Prompts.md
```

Final checks performed:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P1_KOLIBRI_SKILL_REGISTRY_AND_INTERNET_DISCOVERY_REMOTE_IMPL_2026_07_02.json >/dev/null
python3 -m json.tool docs/agent/runs/2026-07-02-p0-autopilot-extra-43-skills-registry-mesh/REMOTE_RESULT.json >/dev/null
git diff --check
git status --short
```

Product test suite:
- Not run. This is a docs/artifact-only extraction and planning task with no
  product code changes.
