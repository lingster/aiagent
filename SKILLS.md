# Skills System Documentation

## Overview

The Skills system provides a way to organize and execute reusable AI agent workflows. Each skill is a self-contained directory with documentation and optional scripts that can be invoked via MCP tools.

## Features

- **Auto-discovery**: Skills are automatically discovered from the `SKILLS_DIR` directory
- **Metadata support**: Skills can include YAML frontmatter for structured metadata
- **Safe execution**: Commands run in isolated temporary directories
- **Hot reload**: Refresh skills cache without restarting the server
- **MCP integration**: Four MCP tools for listing, retrieving, and executing skills

## Directory Structure

```
skills/
├── pdfs/
│   └── skill.md
├── docs/
│   └── skill.md
└── spreadsheets/
    ├── skill.md
    ├── examples/
    │   └── *.py
    └── *.md
```

## Skill File Format

### Without Metadata (Simple Format)

```markdown
# Skill Title

This becomes the summary/description.

The rest of the file is the full description...
```

The skill name defaults to the parent directory name (e.g., `pdfs` for `pdfs/skill.md`).

### With YAML Frontmatter (Advanced Format)

```markdown
---
name: custom-skill-name
description: Brief description that becomes the summary
---

# Full Documentation

Detailed skill documentation goes here...
```

## Environment Configuration

Set the skills directory location in your `.env` file:

```bash
SKILLS_DIR=./skills
```

Default is `./skills` if not specified.

## MCP Tools

### 1. list_skills()

Lists all available skills with their names and summaries.

**Returns:**
```json
{
  "success": true,
  "skills": [
    {
      "name": "pdfs",
      "summary": "PDF reading, creation, and review guidance"
    },
    {
      "name": "docs",
      "summary": "DOCX reading, creation, and review guidance"
    }
  ],
  "count": 2
}
```

### 2. get_skill(name: str)

Retrieves the full details of a specific skill.

**Parameters:**
- `name`: The skill name

**Returns:**
```json
{
  "success": true,
  "skill": {
    "name": "pdfs",
    "summary": "PDF reading, creation, and review guidance",
    "full_description": "# PDF reading...\n\nComplete markdown content...",
    "path": "/path/to/skills/pdfs"
  }
}
```

### 3. use_skill(skill_name: str, command: str)

Executes a command in the context of a skill. The skill's files are copied to a temporary directory before execution to prevent modifications.

**Parameters:**
- `skill_name`: Name of the skill to use
- `command`: Shell command to execute (e.g., `"python script.py arg1 arg2"`)

**Returns:**
```json
{
  "command": "python script.py arg1",
  "output": "Script output...",
  "error": "",
  "return_code": 0,
  "temp_directory": "/tmp/skill_pdfs_xyz123",
  "skill_name": "pdfs"
}
```

**Example:**
```python
# Execute a Python script in the spreadsheets skill directory
result = use_skill("spreadsheets", "python examples/create_basic_spreadsheet.py")
```

### 4. refresh_skills_cache()

Refreshes the skills cache by reloading from disk. Useful when skills are added or modified without restarting the server.

**Returns:**
```json
{
  "success": true,
  "message": "Skills cache refreshed. Previous: 3, Current: 4",
  "skills_loaded": 4
}
```

## Error Handling

### Duplicate Skill Names

If two skills have the same name, a timestamp suffix is automatically added:
- `skill_name_20251213_103045`
- `skill_name_20251213_104127`

### Malformed Skills

Skills that fail to parse are logged as errors and skipped. The server continues loading other skills.

### Missing Heading

If a skill.md file has no `# Heading`, the first paragraph is used as the summary.

## Best Practices

1. **Keep skills focused**: Each skill should address a specific domain or task type
2. **Document thoroughly**: Include usage examples, prerequisites, and expected outputs
3. **Include examples**: Add example scripts in an `examples/` subdirectory
4. **Use metadata**: For skills with custom names or complex structure, use YAML frontmatter
5. **Test scripts**: Ensure example scripts work standalone within the skill directory

## Implementation Details

### Skill Model (Pydantic)

```python
class Skill(BaseModel):
    name: str
    summary: str
    full_description: str
    path: str
```

### Caching

- Skills are loaded once at startup
- Cache is stored in memory for fast access
- Use `refresh_skills_cache()` to reload without restart

### Execution Isolation

When using `use_skill()`:
1. A temporary directory is created
2. All skill files are copied to the temp directory
3. The command runs with the temp directory as the working directory
4. Original skill files remain unchanged
5. Temp directory path is returned for access to outputs

## Module Structure

- `skills_manager.py`: Core skills management logic
  - `SkillsManager` class
  - `Skill` pydantic model
  - Parsing and caching logic
- `mcp_server.py`: MCP tool integrations
  - `list_skills()`
  - `get_skill(name)`
  - `use_skill(skill_name, command)`
  - `refresh_skills_cache()`

## Testing

Run the test suite:

```bash
uv run python test_skills_simple.py
```

Expected output:
```
✓ Initialized SkillsManager with 3 skills
✓ Found 3 skills
✓ Retrieved skill 'pdfs'
✓ Correctly returned None for non-existent skill
✓ Refresh successful
✓ All tests passed!
```
