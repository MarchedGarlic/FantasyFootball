#!/usr/bin/env python3
"""Small helpers shared by multiple analysis modules."""


def get_manager_name(user_lookup, manager_id, prefix="Manager"):
    """Display name for a manager_id, falling back to '{prefix} {manager_id}' instead of
    raising when the manager is missing from user_lookup (e.g. a departed/unlinked manager)."""
    return (user_lookup or {}).get(manager_id, {}).get('display_name', f'{prefix} {manager_id}')
