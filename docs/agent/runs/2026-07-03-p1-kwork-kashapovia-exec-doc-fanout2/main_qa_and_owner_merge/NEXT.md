# NEXT

## Immediate Next Step

1. Poll these factory tasks read-only:
   - `P1_KFM_MIMO_RUNTIME_REPAIR_FOR_KWORK_FANOUT_20260703T151640Z`
   - `P1_KWORK_KASHAPOVIA_EXEC_DOC_FANOUT_SOURCE_INVENTORY_20260703T151018Z`
   - `P1_KWORK_KASHAPOVIA_EXEC_DOC_FANOUT_CABLE_SPEC_MAPPING_20260703T151018Z`
   - `P1_KWORK_KASHAPOVIA_EXEC_DOC_FANOUT_NOTE_QA_OWNER_DRAFT_20260703T151018Z`
2. Treat these lanes as failed, not pending:
   - `P1_KWORK_KASHAPOVIA_EXEC_DOC_FANOUT_DWG_SHEET_REGISTER_20260703T151018Z`
   - `P1_KWORK_KASHAPOVIA_EXEC_DOC_FANOUT2_KFRM_DWG_AND_SPEC_CODEX_FALLBACK_20260703T151545Z`
3. If runtime repair completes green but queued Mimo lanes still do not produce files, do not wait on Mimo for owner decision-making.

## Recommended Recovery

Prepare a corrected Codex fallback wave with a strict artifact contract:

- source inventory and missing-data register;
- DWG sheet register and DWG structure plan;
- cable journal/spec mapping skeleton;
- specification draft;
- explanatory note draft;
- QA checklist;
- owner next-message draft.

## Client Communication Gate

Do not send a client or Kwork message until all of the following are true:

- source inventory exists, or there is an explicit no-source artifact;
- DWG/spec has a successful artifact path, or the fallback clearly states the missing-input limitation;
- QA checklist exists and passes scope/secret checks;
- the client-facing draft asks for missing inputs and does not promise full executive documentation for 12,000 RUB without scope confirmation.

## If No Worker Output Arrives

Use Codex as the primary recovery path. Keep Mimo fan-out as optional evidence after runtime repair, but do not block the owner summary on lanes that are queued without artifacts or already dead-lettered.
