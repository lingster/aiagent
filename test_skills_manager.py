"""Unit tests for skills_manager module."""
import pytest
from pathlib import Path
from skills_manager import SkillsManager


def test_skills_manager_initialization():
    """Test that SkillsManager initializes and loads skills correctly."""
    # Use the actual skills directory
    skills_dir = "./skills"
    manager = SkillsManager(skills_dir)

    # Check that skills were loaded
    assert len(manager.skills_cache) > 0, "No skills were loaded"

    # Print loaded skills for verification
    print(f"\nLoaded {len(manager.skills_cache)} skills:")
    for name, skill in manager.skills_cache.items():
        print(f"  - {name}: {skill.summary[:50]}...")


def test_list_skills():
    """Test list_skills returns correct format."""
    manager = SkillsManager("./skills")
    skills_list = manager.list_skills()

    assert isinstance(skills_list, list), "list_skills should return a list"
    assert len(skills_list) > 0, "list_skills should return at least one skill"

    # Check format of first skill
    first_skill = skills_list[0]
    assert "name" in first_skill, "Skill should have 'name' field"
    assert "summary" in first_skill, "Skill should have 'summary' field"

    print(f"\nlist_skills returned {len(skills_list)} skills:")
    for skill in skills_list:
        print(f"  - {skill['name']}: {skill['summary'][:60]}...")


def test_get_skill():
    """Test get_skill returns correct skill details."""
    manager = SkillsManager("./skills")

    # Get the first skill
    skills_list = manager.list_skills()
    if len(skills_list) == 0:
        pytest.skip("No skills available to test")

    first_skill_name = skills_list[0]["name"]
    skill_details = manager.get_skill(first_skill_name)

    assert skill_details is not None, f"get_skill should return details for '{first_skill_name}'"
    assert "name" in skill_details
    assert "summary" in skill_details
    assert "full_description" in skill_details
    assert "path" in skill_details

    print(f"\nget_skill('{first_skill_name}'):")
    print(f"  Name: {skill_details['name']}")
    print(f"  Summary: {skill_details['summary'][:80]}...")
    print(f"  Description length: {len(skill_details['full_description'])} chars")
    print(f"  Path: {skill_details['path']}")


def test_get_nonexistent_skill():
    """Test get_skill with non-existent skill name."""
    manager = SkillsManager("./skills")
    result = manager.get_skill("nonexistent_skill_xyz")

    assert result is None, "get_skill should return None for non-existent skill"


def test_refresh_skills():
    """Test refresh_skills reloads the cache."""
    manager = SkillsManager("./skills")
    initial_count = len(manager.skills_cache)

    result = manager.refresh_skills()

    assert result["success"] is True, "refresh_skills should succeed"
    assert "skills_loaded" in result
    assert result["skills_loaded"] == initial_count, "Refresh should load same number of skills"

    print(f"\nrefresh_skills result: {result}")


def test_skill_parsing_without_metadata():
    """Test that skills without YAML frontmatter are parsed correctly."""
    manager = SkillsManager("./skills")

    # Check if we have the expected skills (pdfs, docs, spreadsheets)
    expected_skills = ["pdfs", "docs", "spreadsheets"]

    for skill_name in expected_skills:
        skill = manager.get_skill(skill_name)
        if skill:
            print(f"\nSkill '{skill_name}':")
            print(f"  Summary: {skill['summary'][:80]}...")
            print(f"  Has full description: {len(skill['full_description']) > 0}")

            # Verify the skill has required fields
            assert skill["name"] == skill_name
            assert len(skill["summary"]) > 0
            assert len(skill["full_description"]) > 0


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
