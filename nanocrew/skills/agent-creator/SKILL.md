---
name: agent-creator
description: Guide for creating customized agents for specific groups or purposes. Use when the user asks you to create a new agent for a chat group, team, or specific use case. This skill helps you create agents with proper customization and inherited context.
always: true
---

# Agent Creator

Guide for creating customized agents that inherit relevant context from the main agent.

## When to Use This Skill

Use this skill when:
- User asks you to create an agent for a specific chat group (e.g., "为后端团队创建一个 agent")
- User wants a dedicated agent for a specific purpose (e.g., "创建一个专门处理代码审查的 agent")
- You identify that a separate agent would better serve a specific team or workflow

## Creation Workflow

### Step 1: Gather Context

Before creating the agent, read your own memory to understand:

```bash
read_file("~/.nanocrew/workspaces/main/memory/MEMORY.md")
```

Look for:
- **User preferences**: How to address the user (e.g., "王总", "小李")
- **Team context**: Tech stack, domain knowledge, team structure
- **Communication style**: Formal vs casual, language preferences
- **Existing agents**: What agents already exist to avoid duplication

### Step 2: Create the Agent

Execute the CLI command:

```bash
exec("nanocrew agent create <agent_name> [--model <model>] [--temperature <temp>]")
```

Naming conventions:
- Use lowercase letters, digits, and hyphens
- Prefer descriptive names: `backend-dev`, `product-team`, `code-reviewer`
- Keep it under 30 characters

### Step 3: Customize AGENTS.md

After creation, write a customized AGENTS.md for the new agent:

```bash
write_file("~/.nanocrew/workspaces/<agent_name>/AGENTS.md", customized_content)
```

#### Customization Template

**Backend Development Agent:**
```markdown
# Agent Instructions

You are a specialized backend development assistant for {team_name}.

## Team Context

- Primary stack: {tech_stack}
- Focus areas: {focus_areas}

## Guidelines

- Always consider performance and scalability in your advice
- Prefer established patterns over novel solutions
- When reviewing code, check for: security, performance, maintainability
- Reference team conventions when making recommendations

## User

Address the user as "{user_title}".

## Multi-Agent System

This agent serves the backend development team. For general questions outside backend development, suggest consulting the main agent.
```

**Product Team Agent:**
```markdown
# Agent Instructions

You are a product management assistant for {team_name}.

## Team Context

- Product domain: {domain}
- Target users: {target_users}

## Guidelines

- Frame discussions around user value and business goals
- Use user story format when capturing requirements
- Consider competitive landscape when analyzing features
- Balance technical feasibility with user needs

## User

Address the user as "{user_title}".

## Multi-Agent System

This agent serves the product team. For technical implementation details, suggest consulting the backend or frontend agents.
```

### Step 4: Inherit Relevant Memory

Write key context to the new agent's memory:

```bash
write_file("~/.nanocrew/workspaces/<agent_name>/memory/MEMORY.md", inherited_memory)
```

#### What to Inherit

**Always inherit:**
- User name/title (e.g., "称呼用户为'王总'")
- Team identity and domain
- Communication style preferences

**Consider inheriting:**
- Tech stack information
- Project context
- Important team conventions

**Never inherit:**
- Session-specific conversations
- Private information about other users
- Unrelated project details

#### Example Inherited Memory

```markdown
# Long-term Memory

## User Information

- User title: 王总
- Preferred communication: Professional but friendly

## Team Context

- This is the backend development team
- Primary stack: Python, FastAPI, PostgreSQL
- Focus: High-performance API development

## Preferences

- Code reviews should emphasize security and performance
- Prefer async patterns for I/O operations
- Documentation should include API examples
```

### Step 5: Bind to Session (Optional)

If the agent is for a specific chat group, bind it:

```bash
exec("nanocrew agent bind <session_key> <agent_name>")
```

Examples:
- `nanocrew agent bind feishu:oc_abc123 backend-dev`
- `nanocrew agent bind telegram:456789 product-team`

## Memory Inheritance Checklist

Before finishing, verify:

- [ ] Read main agent's MEMORY.md
- [ ] Identified user's preferred name/title
- [ ] Identified relevant team context
- [ ] Created agent with `nanocrew agent create`
- [ ] Customized AGENTS.md for the specific purpose
- [ ] Written inherited memory to new agent's MEMORY.md
- [ ] (Optional) Bound agent to session with `nanocrew agent bind`

## Examples

### Example 1: Backend Dev Team

User: "为飞书后端群创建一个专门的 agent"

Your actions:
1. Read your MEMORY.md → Found: "用户是王总，后端团队使用 Python/FastAPI"
2. Create: `nanocrew agent create backend-dev --temperature 0.3`
3. Customize AGENTS.md → Focus on Python backend, code review
4. Inherit memory → User title "王总", tech stack "Python/FastAPI"
5. Bind: `nanocrew agent bind feishu:oc_backend backend-dev`

### Example 2: Product Discussion Agent

User: "创建一个产品讨论 agent"

Your actions:
1. Read your MEMORY.md → Found: "用户喜欢被称为小李，关注用户体验"
2. Create: `nanocrew agent create product-team`
3. Customize AGENTS.md → Focus on product thinking, user stories
4. Inherit memory → User title "小李", communication style "casual"

## Tips

- **Start simple**: Create basic agent first, then customize
- **Be selective**: Don't inherit everything - only what's relevant
- **Document clearly**: Write clear AGENTS.md so the new agent knows its role
- **Test binding**: Verify the session is correctly bound after creation
