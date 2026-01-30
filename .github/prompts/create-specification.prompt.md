---
agent: 'agent'
description: 'Create a new specification file for the solution, optimized for Generative AI consumption.'
tools: ['changes', 'search/codebase', 'edit/editFiles', 'extensions', 'web/fetch', 'githubRepo', 'openSimpleBrowser', 'problems', 'runTasks', 'search', 'search/searchResults', 'runCommands/terminalLastCommand', 'runCommands/terminalSelection', 'testFailure', 'usages', 'vscodeAPI']
---

# Create Specification

Your goal is to create a new specification file for the solution, optimized for Generative AI consumption. The specification file must define the requirements, constraints, and interfaces for the solution components in a manner that is clear, unambiguous, and structured for effective use by Generative AIs.

## Best Practices for AI-Ready Specifications

- Use precise, explicit, and unambiguous language.
- Clearly distinguish between requirements, constraints, and recommendations.
- Use structured formatting (headings, lists, tables) for easy parsing.
- Avoid idioms, metaphors, or context-dependent references.
- Define all acronyms and domain-specific terms.
- Include examples and edge cases where applicable.
- Ensure the document is self-contained and does not rely on external context.

The specification should be saved in the `/spec/` directory and named according to the following convention: `spec-[a-z0-9-]+.md`, where the name should be descriptive of the specification's content.

## Specification Template

```markdown
---
title: [Concise Title Describing the Specification's Focus]
version: [Optional: e.g., 1.0, Date]
date_created: [YYYY-MM-DD]
last_updated: [Optional: YYYY-MM-DD]
owner: [Optional: Team/Individual responsible for this spec]
tags: [Optional: List of relevant tags or categories]
---

# Introduction

[A short concise introduction to the specification and the goal it is intended to achieve.]

## 1. Purpose & Scope

[Provide a clear, concise description of the specification's purpose and the scope of its application. State the intended audience and any assumptions.]

## 2. Definitions

[List and define all acronyms, abbreviations, and domain-specific terms used in this specification.]

## 3. Requirements, Constraints & Guidelines

[Explicitly list all requirements, constraints, rules, and guidelines. Use bullet points or tables for clarity.]

- **REQ-001**: Requirement 1
- **SEC-001**: Security Requirement 1
- **CON-001**: Constraint 1
- **GUD-001**: Guideline 1
- **PAT-001**: Pattern to follow 1

## 4. Interfaces & Data Contracts

[Describe the interfaces, APIs, data contracts, or integration points. Use tables or code blocks for schemas and examples.]

## 5. Acceptance Criteria

[Define clear, testable acceptance criteria for each requirement using Given-When-Then format where appropriate.]

- **AC-001**: Given [context], When [action], Then [expected outcome]
- **AC-002**: The system shall [specific behavior] when [condition]

## 6. Test Automation Strategy

[Define the testing approach, frameworks, and automation requirements.]

- **Test Levels**: Unit, Integration, End-to-End
- **Frameworks**: [Testing frameworks used]
- **Test Data Management**: [Approach for test data creation and cleanup]
- **CI/CD Integration**: [Automated testing in GitHub Actions pipelines]
- **Coverage Requirements**: [Minimum code coverage thresholds]
- **Performance Testing**: [Approach for load and performance testing]

## 7. Rationale & Context

[Explain the reasoning behind the requirements, constraints, and guidelines. Provide context for design decisions.]

## 8. Dependencies & External Integrations

[Define the external systems, services, and architectural dependencies required for this specification. Focus on **what** is needed rather than **how** it's implemented.]

### External Systems
- **EXT-001**: [External system name] - [Purpose and integration type]

### Third-Party Services
- **SVC-001**: [Service name] - [Required capabilities and SLA requirements]

### Infrastructure Dependencies
- **INF-001**: [Infrastructure component] - [Requirements and constraints]

### Technology Platform Dependencies
- **PLT-001**: [Platform/runtime requirement] - [Version constraints and rationale]

## 9. Examples & Edge Cases

```code
// Code snippet or data example demonstrating correct application
// Including edge cases
```

## 10. Validation Criteria

[List the criteria or tests that must be satisfied for compliance with this specification.]

## 11. Related Specifications / Further Reading

[Link to related spec 1]
[Link to relevant external documentation]
```

## Instructions for Creating Your Specification

1. **Title**: Use a descriptive, concise title that clearly indicates the specification's subject
2. **Front Matter**: Fill in all required fields (date_created, owner, tags)
3. **Introduction**: Write 2-3 sentences explaining what this specification defines
4. **Purpose & Scope**: Define who uses this spec and what it covers
5. **Definitions**: Include all acronyms and technical terms used
6. **Requirements**: Use standardized prefixes (REQ-, SEC-, CON-, GUD-, PAT-)
7. **Interfaces**: Document APIs and data contracts with examples
8. **Acceptance Criteria**: Write testable criteria for each major requirement
9. **Examples**: Provide concrete examples showing correct usage
10. **Validation**: Define how to verify compliance with this specification

## Quality Checklist

- [ ] All acronyms are defined
- [ ] All requirements are unambiguous
- [ ] All code examples are syntactically correct
- [ ] All sections are populated (no placeholders)
- [ ] Specification is self-contained
- [ ] All file paths use forward slashes
- [ ] All version numbers are specified
- [ ] Contact/owner information is provided
