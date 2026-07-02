# Skill: Kolibri Model Factory

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-model-factory` |
| version | `0.1.0` |
| scope | `server` |
| owner | Model Factory Engineer |
| status | `registered` |

## Purpose

Orchestrate local LLM pipeline tasks: model selection, inference testing,
embedding generation, and model quality monitoring.

## Trigger

- Local LLM ring requires model deployment
- Embedding pipeline needs new model
- Model quality regression detected
- New model evaluation requested

## Inputs

- Model requirements (size, capability, license)
- Available compute on model nodes
- Current model inventory
- Quality benchmarks

## Outputs

- Model deployment recommendation
- Resource allocation plan
- Quality evaluation report
- Rollback plan for model changes

## Safety Constraints

- No model deployment without owner approval
- No GPU resource allocation without capacity check
- Model quality regression triggers automatic rollback
- License compatibility verified before deployment

## Dependencies

- Model node status (uiap, mesh-agent-01..03)
- Local LLM ring infrastructure
- Model quality benchmarks
