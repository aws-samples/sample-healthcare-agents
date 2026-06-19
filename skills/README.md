# Skills

Skills define reusable, AI-consumable knowledge for each healthcare agent. Each skill is a self-contained definition with YAML frontmatter (name + description trigger) and a markdown workflow body.

## Structure

```
skills/<skill-name>/
├── SKILL.md          ← Skill definition (YAML frontmatter + workflow instructions)
├── scripts/          ← Executable scripts (Python/bash) for automation
└── references/       ← Domain reference documents loaded on-demand
```

## How Skills Work

- The `description` field in YAML frontmatter is the **trigger** — AI matches user intent to this field
- The markdown body contains the **workflow** — step-by-step instructions with tool references
- `scripts/` holds executable code the agent can run
- `references/` holds domain docs loaded on-demand for deeper context

## Available Skills

| Skill | Description | Agent |
|-------|-------------|-------|
| [appeals](./appeals/) | Appeal letter generation for denied claims | Appeals Agent |
| [claims-assembly](./claims-assembly/) | EDI 837P claim validation and assembly | Claims Assembly Agent |
| [claims-submission](./claims-submission/) | EDI claim submission via B2B Data Interchange | Claims Submission Agent |
| [eligibility-verification](./eligibility-verification/) | Patient insurance eligibility and benefits check | Eligibility Verification Agent |
| [medical-coding](./medical-coding/) | ICD-10-CM, CPT, SNOMED CT code assignment | Medical Coding Agent |
| [prior-authorization](./prior-authorization/) | Prior auth workflow with FHIR PAS Bundle generation | Prior Authorization Agent |

## Consumption

Skills are consumed by:
- **Claude Code** — as plugin skills
- **Strands Agents** — loaded at runtime for workflow guidance
- **AgentCore Registry** — registered as agent capabilities
- **Kiro / Amazon Q** — via steering files or workspace config
