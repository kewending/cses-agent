import os
from pydantic import BaseModel, Field
from tools.registry import registry
from scripts.sync_project import ProjectSyncEngine

class SyncProjectFromMarkdownArgs(BaseModel):
    filepath: str = Field(
        description="Path to the project markdown (.md) file to parse and sync into the CSES Dashboard database."
    )

@registry.register(args_schema=SyncProjectFromMarkdownArgs)
def sync_project_from_markdown(filepath: str) -> str:
    """
    Parses a Second Brain project markdown (.md) file and creates/updates the corresponding
    Project, Subprojects, and Tasks in the CSES Dashboard database. Automatically injects
    generated IDs back into the markdown file.
    """
    try:
        engine = ProjectSyncEngine()
        engine.push(filepath)
        return f"Successfully synchronized project from {filepath} into the CSES Dashboard."
    except Exception as e:
        return f"Error during markdown push sync: {str(e)}"

class SyncProjectToMarkdownArgs(BaseModel):
    filepath: str = Field(
        description="Path to the project markdown (.md) file to refresh with latest completion and status from CSES Dashboard."
    )

@registry.register(args_schema=SyncProjectToMarkdownArgs)
def sync_project_to_markdown(filepath: str) -> str:
    """
    Pulls latest task completion checkmarks and project status from the CSES Dashboard
    database and updates the Second Brain markdown file.
    """
    try:
        engine = ProjectSyncEngine()
        engine.pull(filepath)
        return f"Successfully pulled latest dashboard state into {filepath}."
    except Exception as e:
        return f"Error during markdown pull sync: {str(e)}"
