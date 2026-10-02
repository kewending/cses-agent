#!/usr/bin/env python3
"""
CSES Dashboard - Project Markdown Synchronization Engine
Enables bidirectional synchronization between Second Brain Markdown project specifications
and the CSES Dashboard SQLite database.
"""

import os
import re
import sys
import time
import secrets
import sqlite3
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp1252 console encoding issues
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Default active database path for CSES Dashboard
DEFAULT_DB_PATH = Path(r"c:\Users\Kewen\Project\LifeOS\cses-dashboard\prisma\dev.db")

def get_second_brain_projects_dir():
    """Retrieves SECOND_BRAIN_PROJECTS_DIR from environment or cses-agent/.env."""
    env_val = os.getenv("SECOND_BRAIN_PROJECTS_DIR")
    if env_val:
        return Path(env_val)
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SECOND_BRAIN_PROJECTS_DIR="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return Path(val)
    return None

def is_cses_project_file(file_path):
    """
    Checks if a markdown file is a CSES project file by inspecting frontmatter.
    Auxiliary notes (e.g., Field Log.md, Unit Economics.md) will return False.
    """
    p = Path(file_path)
    if not p.is_file() or p.suffix.lower() != ".md":
        return False
    try:
        content = p.read_text(encoding="utf-8", errors="replace")[:1200]
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_part = parts[1]
                has_title = re.search(r"^title\s*:", fm_part, re.MULTILINE) is not None
                has_obj = re.search(r"^(objective|project_id)\s*:", fm_part, re.MULTILINE) is not None
                return has_title and has_obj
    except Exception:
        pass
    return False

def resolve_project_file(target_str):
    """
    Smart resolver for project markdown files.
    Supports:
      1. Exact file path.
      2. Relative path from SECOND_BRAIN_PROJECTS_DIR.
      3. Folder path (finds <Folder>/<Folder>.md or any file with CSES frontmatter).
      4. Partial/fuzzy project name.
    """
    if not target_str:
        return None

    target_path = Path(target_str)
    
    # 1. Exact existing file
    if target_path.is_file():
        return target_path

    sb_dir = get_second_brain_projects_dir()
    if sb_dir and sb_dir.exists():
        cand = sb_dir / target_str
        # 2. Relative file in SECOND_BRAIN_PROJECTS_DIR
        if cand.is_file():
            return cand
        
        # 3. Target is a folder (e.g. 01-Project/Project - Shopify Zero to First Order/)
        folder = cand if cand.is_dir() else (target_path if target_path.is_dir() else None)
        if folder and folder.is_dir():
            # Check Obsidian Folder Note convention: <FolderName>/<FolderName>.md
            folder_note = folder / f"{folder.name}.md"
            if folder_note.is_file() and is_cses_project_file(folder_note):
                return folder_note
            # Scan all .md files in the folder for CSES project frontmatter
            for md_file in folder.glob("*.md"):
                if is_cses_project_file(md_file):
                    return md_file

        # 4. Fuzzy match by folder name
        target_lower = target_str.lower()
        for subfolder in sb_dir.iterdir():
            if subfolder.is_dir() and target_lower in subfolder.name.lower():
                folder_note = subfolder / f"{subfolder.name}.md"
                if folder_note.is_file() and is_cses_project_file(folder_note):
                    return folder_note
                for md_file in subfolder.glob("*.md"):
                    if is_cses_project_file(md_file):
                        return md_file
            elif subfolder.is_file() and subfolder.suffix.lower() == ".md":
                if target_lower in subfolder.stem.lower() and is_cses_project_file(subfolder):
                    return subfolder

    return target_path

def find_all_project_files():
    """Finds all CSES project files recursively in SECOND_BRAIN_PROJECTS_DIR."""
    sb_dir = get_second_brain_projects_dir()
    if not sb_dir or not sb_dir.exists():
        return []
    results = []
    for root, _, files in os.walk(sb_dir):
        for f in files:
            if f.endswith(".md"):
                fp = Path(root) / f
                if is_cses_project_file(fp):
                    results.append(fp)
    return sorted(results)

def generate_cuid():
    """Generates a 25-character cuid-compatible string."""
    ts = hex(int(time.time() * 1000))[2:]
    rand_part = secrets.token_hex(8)
    return f"c{ts}{rand_part}"[:25]

def to_epoch_ms(date_str):
    """Converts YYYY-MM-DD date string to millisecond epoch integer (Prisma SQLite format)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

def from_epoch_ms(epoch_ms):
    """Converts millisecond epoch integer to YYYY-MM-DD date string."""
    if not epoch_ms:
        return None
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000.0, timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None

def now_epoch_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def parse_duration(dur_str):
    """Parses '30m', '45', '1h' into integer minutes."""
    if not dur_str:
        return 30
    s = str(dur_str).strip().lower()
    if s.endswith("h"):
        try:
            return int(float(s[:-1]) * 60)
        except Exception:
            return 60
    if s.endswith("m"):
        s = s[:-1]
    try:
        return int(s)
    except Exception:
        return 30

class ProjectMarkdownParser:
    def __init__(self, content):
        self.raw_content = content
        self.frontmatter = {}
        self.overview = ""
        self.subprojects = []
        self._parse()

    def _parse(self):
        lines = self.raw_content.splitlines()
        
        # 1. Parse Frontmatter
        body_start = 0
        if lines and lines[0].strip() == "---":
            fm_lines = []
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    body_start = i + 1
                    break
                fm_lines.append(lines[i])
            self._parse_frontmatter(fm_lines)
            
        body_lines = lines[body_start:]
        self._parse_body(body_lines)

    def _parse_frontmatter(self, lines):
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                    self.frontmatter[key] = items
                else:
                    self.frontmatter[key] = val

    def _parse_body(self, lines):
        current_sub = None
        current_task = None
        overview_lines = []
        in_overview = True

        subproject_header_re = re.compile(r"^##\s+(?:Subproject:\s*)?(.+)$", re.IGNORECASE)
        task_re = re.compile(r"^(\s*)-\s*\[([ xX])\]\s*(.+)$")

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check Subproject Header
            sub_match = subproject_header_re.match(stripped)
            if sub_match:
                in_overview = False
                sub_title = sub_match.group(1).strip()
                current_sub = {
                    "title": sub_title,
                    "status": "BACKLOG",
                    "startDate": None,
                    "endDate": None,
                    "description": "",
                    "tasks": [],
                    "id": None
                }
                self.subprojects.append(current_sub)
                current_task = None
                i += 1
                continue

            # Subproject metadata fields: - **key**: val
            if current_sub and current_task is None and stripped.startswith("- **"):
                meta_match = re.match(r"^-\s*\*\*([a-zA-Z0-9_]+)\*\*:\s*(.+)$", stripped)
                if meta_match:
                    k, v = meta_match.group(1).strip().lower(), meta_match.group(2).strip()
                    if k == "status":
                        current_sub["status"] = v.upper()
                    elif k in ("startdate", "start"):
                        current_sub["startDate"] = v
                    elif k in ("enddate", "end"):
                        current_sub["endDate"] = v
                    elif k in ("description", "desc"):
                        current_sub["description"] = v
                    i += 1
                    continue

            # Task or Subtask line
            task_match = task_re.match(line)
            if task_match:
                in_overview = False
                indent, mark, task_body = task_match.group(1), task_match.group(2), task_match.group(3)
                is_completed = (mark.lower() == "x")
                is_subtask = len(indent) >= 2

                parsed_task = self._parse_task_line(task_body, is_completed)

                if is_subtask and current_task is not None:
                    current_task["subtasks"].append(parsed_task)
                else:
                    if current_sub is None:
                        # Fallback if tasks exist before any subproject heading (Leaf project mode)
                        current_sub = {
                            "title": self.frontmatter.get("title", "Main"),
                            "status": self.frontmatter.get("status", "BACKLOG"),
                            "startDate": self.frontmatter.get("startDate"),
                            "endDate": self.frontmatter.get("endDate"),
                            "description": "",
                            "tasks": [],
                            "id": None,
                            "is_leaf": True
                        }
                        self.subprojects.append(current_sub)
                    current_sub["tasks"].append(parsed_task)
                    current_task = parsed_task

                i += 1
                continue

            # Blockquote notes following a task
            if current_task and stripped.startswith(">"):
                note_text = stripped[1:].strip()
                if current_task["notes"]:
                    current_task["notes"] += "\n" + note_text
                else:
                    current_task["notes"] = note_text
                i += 1
                continue

            if in_overview:
                if not stripped.startswith("# Project Overview") and not stripped.startswith("#"):
                    overview_lines.append(line)

            i += 1

        self.overview = "\n".join(overview_lines).strip()

    def _parse_task_line(self, task_body, is_completed):
        # Extract HTML comment ID: <!-- id: cuid -->
        task_id = None
        id_match = re.search(r"<!--\s*id:\s*([a-zA-Z0-9_\-]+)\s*-->", task_body)
        if id_match:
            task_id = id_match.group(1).strip()
            task_body = task_body[:id_match.start()] + task_body[id_match.end():]

        # Extract Obsidian block reference: ^task-id
        block_match = re.search(r"\^([a-zA-Z0-9_\-]+)$", task_body.strip())
        if block_match:
            if not task_id:
                task_id = block_match.group(1).strip()
            task_body = task_body[:block_match.start()]

        parts = [p.strip() for p in task_body.split("|")]
        title = parts[0]

        meta = {
            "title": title,
            "isCompleted": is_completed,
            "id": task_id,
            "plannedDurationMinutes": 30,
            "priority": "None",
            "tag": "",
            "startDate": None,
            "dueDate": None,
            "status": "inbox",
            "notes": "",
            "subtasks": []
        }

        for part in parts[1:]:
            if ":" in part:
                k, v = part.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k in ("duration", "planned"):
                    meta["plannedDurationMinutes"] = parse_duration(v)
                elif k == "priority":
                    p = v.capitalize()
                    if p in ("High", "Medium", "Low", "None"):
                        meta["priority"] = p
                elif k == "tag":
                    meta["tag"] = v.replace("#", "").strip()
                elif k in ("start", "startdate"):
                    meta["startDate"] = v
                elif k in ("due", "duedate"):
                    meta["dueDate"] = v
                elif k == "status":
                    meta["status"] = v

        return meta


class ProjectSyncEngine:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at: {self.db_path}")

    def get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_or_create_objective(self, cursor, obj_title):
        if not obj_title:
            return None
        cursor.execute("SELECT id FROM Objective WHERE LOWER(title) = LOWER(?)", (obj_title.strip(),))
        row = cursor.fetchone()
        if row:
            return row["id"]
        
        new_id = generate_cuid()
        cursor.execute("INSERT INTO Objective (id, title, description) VALUES (?, ?, ?)",
                       (new_id, obj_title.strip(), ""))
        return new_id

    def push(self, filepath):
        path = resolve_project_file(filepath)
        if not path or not path.exists():
            print(f"Error: Could not resolve project markdown file from: '{filepath}'")
            sb_dir = get_second_brain_projects_dir()
            if sb_dir:
                print(f"Hint: Checked inside SECOND_BRAIN_PROJECTS_DIR: {sb_dir}")
            sys.exit(1)

        print(f"Resolving project file: {path}")
        content = path.read_text(encoding="utf-8")
        parser = ProjectMarkdownParser(content)
        fm = parser.frontmatter

        title = fm.get("title")
        if not title:
            # Fallback to filename
            raw_stem = path.stem
            if raw_stem.lower().startswith("project - "):
                title = raw_stem[10:].strip()
            else:
                title = raw_stem.strip()
        if not title:
            print(f"Error: Could not determine project title from frontmatter or filename for {path}")
            sys.exit(1)

        objective_name = fm.get("objective")
        parent_status = fm.get("status", "BACKLOG").upper()
        start_date = fm.get("startDate")
        end_date = fm.get("endDate")
        project_id = fm.get("project_id") or None
        overview_desc = parser.overview

        # Determine if this is a leaf project (only 1 subproject flagged as leaf or no subprojects)
        is_flat_leaf = len(parser.subprojects) == 1 and parser.subprojects[0].get("is_leaf", False)

        assigned_project_id = project_id
        assigned_task_ids = {} # (subproject_idx, task_idx) -> id or subtask

        with self.get_connection() as conn:
            cursor = conn.cursor()
            now_ms = now_epoch_ms()
            obj_id = self.get_or_create_objective(cursor, objective_name) if objective_name else None

            # 1. Upsert Parent Project
            if assigned_project_id:
                cursor.execute("SELECT id FROM Project WHERE id = ?", (assigned_project_id,))
                existing = cursor.fetchone()
            else:
                existing = None

            if not existing:
                assigned_project_id = generate_cuid()
                cursor.execute("""
                    INSERT INTO Project (id, title, description, status, startDate, endDate, "order", objectiveId, parentProjectId, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """, (
                    assigned_project_id,
                    title,
                    overview_desc,
                    parent_status,
                    to_epoch_ms(start_date),
                    to_epoch_ms(end_date),
                    0,
                    obj_id,
                    now_ms,
                    now_ms
                ))
                print(f"Created Parent Project: [{title}] (ID: {assigned_project_id})")
            else:
                cursor.execute("""
                    UPDATE Project
                    SET title = ?, description = ?, status = ?, startDate = ?, endDate = ?, objectiveId = ?, updatedAt = ?
                    WHERE id = ?
                """, (
                    title,
                    overview_desc,
                    parent_status,
                    to_epoch_ms(start_date),
                    to_epoch_ms(end_date),
                    obj_id,
                    now_ms,
                    assigned_project_id
                ))
                print(f"Updated Parent Project: [{title}] (ID: {assigned_project_id})")

            # 2. Upsert Subprojects and Tasks
            for s_idx, sub in enumerate(parser.subprojects):
                if is_flat_leaf:
                    # Leaf project holds tasks directly
                    target_project_id = assigned_project_id
                else:
                    sub_title = sub["title"]
                    sub_status = sub["status"]
                    sub_start = sub.get("startDate") or start_date
                    sub_end = sub.get("endDate") or end_date
                    sub_desc = sub.get("description", "")
                    sub_id = sub.get("id")

                    # Match subproject by parentProjectId + title if no ID
                    if not sub_id:
                        cursor.execute("SELECT id FROM Project WHERE parentProjectId = ? AND LOWER(title) = LOWER(?)",
                                       (assigned_project_id, sub_title.strip()))
                        sub_row = cursor.fetchone()
                        if sub_row:
                            sub_id = sub_row["id"]

                    if not sub_id:
                        sub_id = generate_cuid()
                        cursor.execute("""
                            INSERT INTO Project (id, title, description, status, startDate, endDate, "order", objectiveId, parentProjectId, createdAt, updatedAt)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sub_id,
                            sub_title,
                            sub_desc,
                            sub_status,
                            to_epoch_ms(sub_start),
                            to_epoch_ms(sub_end),
                            s_idx,
                            obj_id,
                            assigned_project_id,
                            now_ms,
                            now_ms
                        ))
                        print(f"  └─ Created Subproject: [{sub_title}] (ID: {sub_id})")
                    else:
                        cursor.execute("""
                            UPDATE Project
                            SET title = ?, description = ?, status = ?, startDate = ?, endDate = ?, "order" = ?, updatedAt = ?
                            WHERE id = ?
                        """, (
                            sub_title,
                            sub_desc,
                            sub_status,
                            to_epoch_ms(sub_start),
                            to_epoch_ms(sub_end),
                            s_idx,
                            now_ms,
                            sub_id
                        ))
                        print(f"  └─ Updated Subproject: [{sub_title}] (ID: {sub_id})")

                    target_project_id = sub_id

                # Upsert Tasks
                for t_idx, task in enumerate(sub["tasks"]):
                    task_id = task.get("id")
                    if not task_id:
                        cursor.execute("SELECT id FROM Task WHERE projectId = ? AND parentTaskId IS NULL AND LOWER(title) = LOWER(?)",
                                       (target_project_id, task["title"].strip()))
                        t_row = cursor.fetchone()
                        if t_row:
                            task_id = t_row["id"]

                    if not task_id:
                        task_id = generate_cuid()
                        task["id"] = task_id
                        cursor.execute("""
                            INSERT INTO Task (
                                id, title, status, tag, priority, startDate, dueDate,
                                plannedDurationMinutes, actualDurationSeconds, isCompleted,
                                notes, showInKanban, "order", parentTaskId, projectId, createdAt, updatedAt
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, ?, NULL, ?, ?, ?)
                        """, (
                            task_id,
                            task["title"],
                            task["status"],
                            task["tag"],
                            task["priority"],
                            to_epoch_ms(task["startDate"]),
                            to_epoch_ms(task["dueDate"]),
                            task["plannedDurationMinutes"],
                            1 if task["isCompleted"] else 0,
                            task["notes"],
                            t_idx,
                            target_project_id,
                            now_ms,
                            now_ms
                        ))
                        print(f"     ├── Created Task: {task['title']} (ID: {task_id})")
                    else:
                        cursor.execute("""
                            UPDATE Task
                            SET title = ?, status = ?, tag = ?, priority = ?, startDate = ?, dueDate = ?,
                                plannedDurationMinutes = ?, isCompleted = ?, notes = ?, "order" = ?, projectId = ?, updatedAt = ?
                            WHERE id = ?
                        """, (
                            task["title"],
                            task["status"],
                            task["tag"],
                            task["priority"],
                            to_epoch_ms(task["startDate"]),
                            to_epoch_ms(task["dueDate"]),
                            task["plannedDurationMinutes"],
                            1 if task["isCompleted"] else 0,
                            task["notes"],
                            t_idx,
                            target_project_id,
                            now_ms,
                            task_id
                        ))
                        print(f"     ├── Updated Task: {task['title']} (ID: {task_id})")

                    # Upsert Subtasks
                    for sub_idx, subtask in enumerate(task.get("subtasks", [])):
                        subtask_id = subtask.get("id")
                        if not subtask_id:
                            cursor.execute("SELECT id FROM Task WHERE parentTaskId = ? AND LOWER(title) = LOWER(?)",
                                           (task_id, subtask["title"].strip()))
                            st_row = cursor.fetchone()
                            if st_row:
                                subtask_id = st_row["id"]

                        if not subtask_id:
                            subtask_id = generate_cuid()
                            subtask["id"] = subtask_id
                            cursor.execute("""
                                INSERT INTO Task (
                                    id, title, status, tag, priority, startDate, dueDate,
                                    plannedDurationMinutes, actualDurationSeconds, isCompleted,
                                    notes, showInKanban, "order", parentTaskId, projectId, createdAt, updatedAt
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0, ?, ?, NULL, ?, ?)
                            """, (
                                subtask_id,
                                subtask["title"],
                                task["status"],
                                task["tag"],
                                subtask.get("priority", "None"),
                                to_epoch_ms(task["startDate"]),
                                to_epoch_ms(task["dueDate"]),
                                subtask.get("plannedDurationMinutes", 15),
                                1 if subtask["isCompleted"] else 0,
                                "",
                                sub_idx,
                                task_id,
                                now_ms,
                                now_ms
                            ))
                            print(f"     │    └── Created Subtask: {subtask['title']} (ID: {subtask_id})")
                        else:
                            cursor.execute("""
                                UPDATE Task
                                SET title = ?, plannedDurationMinutes = ?, isCompleted = ?, "order" = ?, updatedAt = ?
                                WHERE id = ?
                            """, (
                                subtask["title"],
                                subtask.get("plannedDurationMinutes", 15),
                                1 if subtask["isCompleted"] else 0,
                                sub_idx,
                                now_ms,
                                subtask_id
                            ))
                            print(f"     │    └── Updated Subtask: {subtask['title']} (ID: {subtask_id})")

            conn.commit()

        # 3. Inject IDs back into Markdown File
        self._writeback_ids(path, assigned_project_id, parser)
        print(f"\nPush Sync Completed! File updated with IDs: {path}")

    def _writeback_ids(self, path, project_id, parser):
        lines = path.read_text(encoding="utf-8").splitlines()
        output_lines = []
        in_fm = False
        fm_done = False
        project_id_written = False

        task_re = re.compile(r"^(\s*-\s*\[[ xX]\]\s*)(.+)$")

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not in_fm and not fm_done:
                    in_fm = True
                    output_lines.append(line)
                    continue
                elif in_fm:
                    if not project_id_written:
                        output_lines.append(f'project_id: "{project_id}"')
                        project_id_written = True
                    in_fm = False
                    fm_done = True
                    output_lines.append(line)
                    continue

            if in_fm:
                if stripped.startswith("project_id:"):
                    output_lines.append(f'project_id: "{project_id}"')
                    project_id_written = True
                    continue
                output_lines.append(line)
                continue

            # Check if this line is a task or subtask and needs <!-- id: ... -->
            task_match = task_re.match(line)
            if task_match:
                prefix, body = task_match.group(1), task_match.group(2)
                # Check if it already has an id
                if "<!-- id:" not in body:
                    # Look up corresponding task in parser data
                    matched_id = self._find_matching_task_id(body, parser)
                    if matched_id:
                        line = f"{line.rstrip()} <!-- id: {matched_id} -->"

            output_lines.append(line)

        path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    def _find_matching_task_id(self, task_body, parser):
        clean_title = task_body.split("|")[0].strip()
        for sub in parser.subprojects:
            for t in sub["tasks"]:
                if t["title"].strip() == clean_title and t.get("id"):
                    return t["id"]
                for st in t.get("subtasks", []):
                    if st["title"].strip() == clean_title and st.get("id"):
                        return st["id"]
        return None

    def pull(self, filepath):
        path = resolve_project_file(filepath)
        if not path or not path.exists():
            print(f"Error: Could not resolve project markdown file from: '{filepath}'")
            sb_dir = get_second_brain_projects_dir()
            if sb_dir:
                print(f"Hint: Checked inside SECOND_BRAIN_PROJECTS_DIR: {sb_dir}")
            sys.exit(1)

        print(f"Resolving project file: {path}")
        content = path.read_text(encoding="utf-8")
        parser = ProjectMarkdownParser(content)
        project_id = parser.frontmatter.get("project_id")

        if not project_id:
            print("Error: No 'project_id' in frontmatter. Please push the project first.")
            sys.exit(1)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Project WHERE id = ?", (project_id,))
            proj = cursor.fetchone()
            if not proj:
                print(f"Error: Project with ID {project_id} not found in database.")
                sys.exit(1)

            # Fetch all subprojects
            cursor.execute("SELECT * FROM Project WHERE parentProjectId = ?", (project_id,))
            subprojects = cursor.fetchall()
            sub_ids = [s["id"] for s in subprojects] + [project_id]

            # Fetch all tasks under these projects
            placeholders = ",".join("?" for _ in sub_ids)
            cursor.execute(f"SELECT * FROM Task WHERE projectId IN ({placeholders})", sub_ids)
            tasks = cursor.fetchall()
            task_map = {t["id"]: t for t in tasks}

            # Fetch all subtasks
            main_task_ids = [t["id"] for t in tasks]
            if main_task_ids:
                t_placeholders = ",".join("?" for _ in main_task_ids)
                cursor.execute(f"SELECT * FROM Task WHERE parentTaskId IN ({t_placeholders})", main_task_ids)
                subtasks = cursor.fetchall()
                for st in subtasks:
                    task_map[st["id"]] = st

        # Update Markdown content
        lines = content.splitlines()
        updated_lines = []
        in_fm = False
        fm_done = False

        task_id_re = re.compile(r"<!--\s*id:\s*([a-zA-Z0-9_\-]+)\s*-->")
        task_box_re = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*.+)$")

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not in_fm and not fm_done:
                    in_fm = True
                elif in_fm:
                    in_fm = False
                    fm_done = True
                updated_lines.append(line)
                continue

            if in_fm:
                if stripped.startswith("status:"):
                    updated_lines.append(f'status: "{proj["status"]}"')
                    continue
                updated_lines.append(line)
                continue

            # Update task checkbox based on database isCompleted
            id_match = task_id_re.search(line)
            if id_match:
                t_id = id_match.group(1).strip()
                if t_id in task_map:
                    db_completed = bool(task_map[t_id]["isCompleted"])
                    box_match = task_box_re.match(line)
                    if box_match:
                        prefix, cur_mark, rest = box_match.group(1), box_match.group(2), box_match.group(3)
                        new_mark = "x" if db_completed else " "
                        line = f"{prefix}{new_mark}{rest}"

            updated_lines.append(line)

        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        print(f"Pull Sync Completed! Updated status & checkmarks from database into {path}")


def main():
    parser = argparse.ArgumentParser(description="Bidirectional Project Markdown Sync Engine for CSES Dashboard")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--push", nargs="?", const="--all", help="Push markdown project file, folder, or project name to SQLite database (or '--push --all' to sync all projects)")
    group.add_argument("--pull", nargs="?", const="--all", help="Pull database execution state into markdown project file (or '--pull --all' to sync all projects)")
    parser.add_argument("--all", action="store_true", help="Sync all projects found in SECOND_BRAIN_PROJECTS_DIR")
    parser.add_argument("--db", help="Path to SQLite database (default: CSES dev.db)")

    args = parser.parse_args()
    engine = ProjectSyncEngine(args.db)

    is_all_push = args.all or args.push in ("--all", "all")
    is_all_pull = args.all or args.pull in ("--all", "all")

    if is_all_push:
        all_files = find_all_project_files()
        if not all_files:
            sb_dir = get_second_brain_projects_dir()
            print(f"No CSES project markdown files found in SECOND_BRAIN_PROJECTS_DIR: {sb_dir}")
            return
        print(f"Found {len(all_files)} project(s) to push:")
        for f in all_files:
            print(f"\n==========================================")
            print(f"Syncing: {f.name}")
            print(f"==========================================")
            try:
                engine.push(str(f))
            except Exception as e:
                print(f"Error syncing {f.name}: {e}")
    elif args.push:
        engine.push(args.push)
    elif is_all_pull:
        all_files = find_all_project_files()
        if not all_files:
            sb_dir = get_second_brain_projects_dir()
            print(f"No CSES project markdown files found in SECOND_BRAIN_PROJECTS_DIR: {sb_dir}")
            return
        print(f"Found {len(all_files)} project(s) to pull:")
        for f in all_files:
            print(f"\n==========================================")
            print(f"Pulling: {f.name}")
            print(f"==========================================")
            try:
                engine.pull(str(f))
            except Exception as e:
                print(f"Error pulling {f.name}: {e}")
    elif args.pull:
        engine.pull(args.pull)

if __name__ == "__main__":
    main()
