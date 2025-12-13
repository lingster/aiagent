"""Skills Manager Module

Manages skill discovery, caching, and execution for the MCP server.
"""
import os
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from loguru import logger
import httpx
import yaml


class Skill(BaseModel):
    """Represents a skill with its metadata and description."""
    name: str = Field(..., description="The name of the skill")
    summary: str = Field(..., description="A brief summary/description of the skill")
    full_description: str = Field(..., description="The complete skill documentation")
    path: str = Field(..., description="Path to the skill directory")


class SkillsManager:
    """Manages skills discovery, caching, and execution."""

    def __init__(self, skills_dir: str):
        """Initialize the skills manager.

        Args:
            skills_dir: The directory containing skills
        """
        self.skills_dir = Path(skills_dir)
        self.skills_cache: Dict[str, Skill] = {}
        self._load_skills()

    def _parse_yaml_frontmatter(self, content: str) -> tuple[Optional[dict], str]:
        """Parse YAML frontmatter from markdown content.

        Args:
            content: The markdown content

        Returns:
            A tuple of (metadata_dict, remaining_content)
        """
        # Check if content starts with ---
        if not content.strip().startswith('---'):
            return None, content

        # Find the closing ---
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            return None, content

        try:
            metadata = yaml.safe_load(match.group(1))
            remaining_content = match.group(2)
            return metadata, remaining_content
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML frontmatter: {e}")
            return None, content

    def _extract_first_heading(self, content: str) -> Optional[str]:
        """Extract the first # heading from markdown content.

        Args:
            content: The markdown content

        Returns:
            The heading text without the # symbol, or None if not found
        """
        pattern = r'^#\s+(.+?)$'
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_first_paragraph(self, content: str) -> str:
        """Extract the first non-empty paragraph from content.

        Args:
            content: The text content

        Returns:
            The first paragraph or empty string if not found
        """
        # Split by double newlines to get paragraphs
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        return paragraphs[0] if paragraphs else ""

    def _parse_skill_file(self, skill_path: Path) -> Optional[Skill]:
        """Parse a skill.md file and extract skill information.

        Args:
            skill_path: Path to the skill.md file

        Returns:
            A Skill object or None if parsing fails
        """
        try:
            content = skill_path.read_text(encoding='utf-8')

            # Try to parse YAML frontmatter
            metadata, remaining_content = self._parse_yaml_frontmatter(content)

            if metadata:
                # Use metadata if available
                name = metadata.get('name')
                summary = metadata.get('description', '')
                full_description = remaining_content.strip()

                # If name is not in metadata, use parent folder
                if not name:
                    name = skill_path.parent.name
            else:
                # No metadata, use fallback approach
                name = skill_path.parent.name

                # Try to get summary from first # heading
                heading = self._extract_first_heading(content)
                if heading:
                    summary = heading
                else:
                    # Fallback to first paragraph
                    summary = self._extract_first_paragraph(content)

                full_description = content.strip()

            # Get the skill directory path
            skill_dir = str(skill_path.parent.absolute())

            return Skill(
                name=name,
                summary=summary,
                full_description=full_description,
                path=skill_dir
            )

        except Exception as e:
            logger.error(f"Failed to parse skill file {skill_path}: {e}")
            return None

    def _get_folder_timestamp(self, folder_path: Path) -> str:
        """Get the creation timestamp of a folder in YYYYMMDD_HHMMSS format.

        Args:
            folder_path: Path to the folder

        Returns:
            Timestamp string
        """
        try:
            stat_info = folder_path.stat()
            timestamp = datetime.fromtimestamp(stat_info.st_ctime)
            return timestamp.strftime('%Y%m%d_%H%M%S')
        except Exception as e:
            logger.error(f"Failed to get timestamp for {folder_path}: {e}")
            return datetime.now().strftime('%Y%m%d_%H%M%S')

    def _load_skills(self):
        """Recursively load all skills from the skills directory."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_dir}")
            return

        # Find all skill.md or SKILL.md files
        skill_files = []
        for pattern in ['**/skill.md', '**/SKILL.md']:
            skill_files.extend(self.skills_dir.glob(pattern))

        logger.info(f"Found {len(skill_files)} skill files")

        # Parse each skill file
        temp_skills: Dict[str, Skill] = {}

        for skill_file in skill_files:
            skill = self._parse_skill_file(skill_file)

            if skill:
                # Check for duplicate names
                if skill.name in temp_skills:
                    logger.warning(f"Duplicate skill name found: {skill.name}")
                    # Add timestamp suffix to both skills
                    timestamp = self._get_folder_timestamp(skill_file.parent)
                    skill.name = f"{skill.name}_{timestamp}"

                temp_skills[skill.name] = skill
                logger.info(f"Loaded skill: {skill.name}")

        self.skills_cache = temp_skills
        logger.info(f"Successfully loaded {len(self.skills_cache)} skills")

    def list_skills(self) -> List[Dict[str, str]]:
        """List all available skills with name and summary.

        Returns:
            A list of dicts containing name and summary for each skill
        """
        return [
            {"name": skill.name, "summary": skill.summary}
            for skill in self.skills_cache.values()
        ]

    def get_skill(self, name: str) -> Optional[Dict[str, str]]:
        """Get the full description of a skill by name.

        Args:
            name: The name of the skill

        Returns:
            A dict with skill details or None if not found
        """
        skill = self.skills_cache.get(name)
        if skill:
            return {
                "name": skill.name,
                "summary": skill.summary,
                "full_description": skill.full_description,
                "path": skill.path
            }
        return None

    async def use_skill(
        self,
        skill_name: str,
        command: str,
        execute_url: str
    ) -> dict:
        """Execute a command in the context of a skill.

        This copies the skill files to a temp directory and runs the command there.

        Args:
            skill_name: The name of the skill to use
            command: The command to execute
            execute_url: The URL for command execution

        Returns:
            The execution result as a dict
        """
        # Get the skill
        skill = self.skills_cache.get(skill_name)
        if not skill:
            return {
                "error": f"Skill '{skill_name}' not found",
                "available_skills": list(self.skills_cache.keys())
            }

        # Create a temporary directory
        try:
            temp_dir = tempfile.mkdtemp(prefix=f"skill_{skill_name}_")
            logger.info(f"Created temp directory: {temp_dir}")

            # Copy skill files to temp directory
            skill_path = Path(skill.path)
            shutil.copytree(skill_path, temp_dir, dirs_exist_ok=True)
            logger.info(f"Copied skill files from {skill_path} to {temp_dir}")

            # Modify command to run in temp directory
            full_command = f"cd {temp_dir} && {command}"

            # Execute the command
            from remote_server_lib.core import CommandRequest

            req = CommandRequest(command=full_command)
            httpx_timeout = httpx.Timeout(300)  # 5 minute timeout for skill execution

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    execute_url,
                    data=req.model_dump_json(),
                    timeout=httpx_timeout
                )

            response.raise_for_status()

            if response.status_code == 200:
                result = response.json()
                result['temp_directory'] = temp_dir
                result['skill_name'] = skill_name
                return result
            else:
                return {
                    "error": f"Failed to execute command: {response.json().get('error')}",
                    "skill_name": skill_name,
                    "temp_directory": temp_dir
                }

        except Exception as ex:
            logger.error(f"Failed to use skill {skill_name}: {str(ex)}")
            return {
                "error": f"Failed to execute skill: {str(ex)}",
                "skill_name": skill_name
            }

    def refresh_skills(self) -> dict:
        """Refresh the skills cache by reloading from disk.

        Returns:
            A dict with refresh status
        """
        try:
            old_count = len(self.skills_cache)
            self._load_skills()
            new_count = len(self.skills_cache)

            return {
                "success": True,
                "message": f"Skills cache refreshed. Previous: {old_count}, Current: {new_count}",
                "skills_loaded": new_count
            }
        except Exception as ex:
            logger.error(f"Failed to refresh skills: {str(ex)}")
            return {
                "success": False,
                "error": str(ex)
            }
