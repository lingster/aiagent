#!/usr/bin/env python
"""Simple test script for skills_manager."""
import sys
from skills_manager import SkillsManager


def main():
    print("Testing SkillsManager...")
    print("=" * 60)

    # Initialize manager
    manager = SkillsManager("./skills")
    print(f"\n✓ Initialized SkillsManager with {len(manager.skills_cache)} skills")

    # Test list_skills
    print("\n" + "=" * 60)
    print("Testing list_skills()...")
    skills_list = manager.list_skills()
    print(f"✓ Found {len(skills_list)} skills:")
    for skill in skills_list:
        print(f"   - {skill['name']}: {skill['summary'][:60]}...")

    # Test get_skill
    print("\n" + "=" * 60)
    print("Testing get_skill()...")
    if skills_list:
        first_skill_name = skills_list[0]["name"]
        skill_details = manager.get_skill(first_skill_name)
        if skill_details:
            print(f"✓ Retrieved skill '{first_skill_name}':")
            print(f"   Summary: {skill_details['summary'][:80]}...")
            print(f"   Description length: {len(skill_details['full_description'])} chars")
            print(f"   Path: {skill_details['path']}")
        else:
            print(f"✗ Failed to retrieve skill '{first_skill_name}'")
            sys.exit(1)

    # Test get_skill with non-existent name
    print("\n" + "=" * 60)
    print("Testing get_skill() with non-existent skill...")
    nonexistent = manager.get_skill("nonexistent_skill_xyz")
    if nonexistent is None:
        print("✓ Correctly returned None for non-existent skill")
    else:
        print("✗ Should have returned None for non-existent skill")
        sys.exit(1)

    # Test refresh_skills
    print("\n" + "=" * 60)
    print("Testing refresh_skills()...")
    result = manager.refresh_skills()
    if result["success"]:
        print(f"✓ Refresh successful: {result['message']}")
    else:
        print(f"✗ Refresh failed: {result.get('error')}")
        sys.exit(1)

    # Verify specific skills
    print("\n" + "=" * 60)
    print("Verifying expected skills...")
    expected = ["pdfs", "docs", "spreadsheets"]
    for skill_name in expected:
        skill = manager.get_skill(skill_name)
        if skill:
            print(f"✓ Found '{skill_name}' skill")
            print(f"   Summary: {skill['summary'][:70]}...")
        else:
            print(f"⚠ Warning: Expected skill '{skill_name}' not found")

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
