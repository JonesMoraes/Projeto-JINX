"""
JINX action - Update JINX from Git repository (for development).

This action allows developers to update JINX directly from the GitHub repository
using git pull. It's the simplest way to keep JINX up-to-date during development.

Usage:
    - Voice command: "JINX, atualizar" or "JINX, update"
    - Text command: update_jinx
    - Alternative: "JINX, verificar atualizações" or "JINX, check for updates"
"""

import subprocess
import sys
from pathlib import Path
from core import outcome


def is_git_repo(path: Path) -> bool:
    """Check if the given path is a Git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


def get_current_branch(path: Path) -> str:
    """Get the current Git branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_latest_commit(path: Path) -> str:
    """Get the latest commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def check_for_updates(path: Path) -> tuple[bool, str, str]:
    """
    Check if there are updates available.
    Returns: (has_updates, current_commit, latest_remote_commit)
    """
    try:
        # Fetch latest changes from remote
        result = subprocess.run(
            ["git", "fetch", "origin", "--prune"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=10
        )
        
        if result.returncode != 0:
            return False, "", ""
        
        # Get current commit
        current = get_latest_commit(path)
        
        # Get remote commit
        result = subprocess.run(
            ["git", "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5
        )
        
        if result.returncode != 0:
            return False, current, ""
        
        remote = result.stdout.strip()
        has_updates = current != remote
        
        return has_updates, current, remote
        
    except Exception as e:
        return False, "", str(e)


def pull_updates(path: Path) -> tuple[bool, str]:
    """
    Pull updates from Git repository.
    Returns: (success, message)
    """
    try:
        # Get current branch
        branch = get_current_branch(path)
        
        # Pull updates
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=30
        )
        
        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                return True, "JINX já está atualizado!"
            else:
                # Count changes
                changes_result = subprocess.run(
                    ["git", "log", "--oneline", f"@{1}...HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=str(path),
                    timeout=5
                )
                changes = changes_result.stdout.strip()
                commit_count = len(changes.split('\n')) if changes else 0
                return True, f"Atualização realizada com sucesso! {commit_count} novo(s) commit(s)."
        else:
            return False, f"Erro ao atualizar: {result.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        return False, "Timeout ao executar git pull. Tente novamente."
    except Exception as e:
        return False, f"Erro ao atualizar: {str(e)}"


def get_git_status(path: Path) -> str:
    """Get Git status information."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


async def action_update_jinx(session):
    """Update JINX from Git repository."""
    project_path = Path(__file__).parent.parent
    
    # Check if this is a Git repository
    if not is_git_repo(project_path):
        return outcome.answered(
            "update_jinx",
            "Este método de atualização requer um repositório Git. "
            "Para atualizar manualmente: git pull origin main"
        )
    
    # Check for updates
    has_updates, current, remote = check_for_updates(project_path)
    
    if not has_updates:
        branch = get_current_branch(project_path)
        return outcome.answered(
            "update_jinx",
            f"JINX já está atualizado! (Branch: {branch})"
        )
    
    # Pull updates
    success, message = pull_updates(project_path)
    
    if success:
        return outcome.answered(
            "update_jinx",
            f"{message}\n\nReiniciando JINX para aplicar as atualizações..."
        )
    else:
        return outcome.failed("update_jinx", message)


async def action_check_updates(session):
    """Check if updates are available without pulling."""
    project_path = Path(__file__).parent.parent
    
    if not is_git_repo(project_path):
        return outcome.answered(
            "check_updates",
            "Este método requer um repositório Git."
        )
    
    has_updates, current, remote = check_for_updates(project_path)
    
    if has_updates:
        branch = get_current_branch(project_path)
        status = get_git_status(project_path)
        
        message = f"Atualização disponível!\n"
        message += f"Branch: {branch}\n"
        message += f"Local: {current[:8]}\n"
        message += f"Remote: {remote[:8]}\n"
        
        if status:
            message += f"\nStatus:\n{status}"
        
        message += "\nUse 'update_jinx' para atualizar."
        
        return outcome.answered("check_updates", message)
    else:
        branch = get_current_branch(project_path)
        return outcome.answered(
            "check_updates",
            f"JINX está atualizado! (Branch: {branch})"
        )


# Tool declarations for auto-discovery
TOOL_UPDATE = {
    "name": "update_jinx",
    "description": "Update JINX from Git repository. Pulls the latest changes from the current branch.",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": action_update_jinx,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}

TOOL_CHECK = {
    "name": "check_updates",
    "description": "Check if there are updates available for JINX from Git repository without pulling.",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": action_check_updates,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
