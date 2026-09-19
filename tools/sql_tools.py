import os
import re
import json
from sqlalchemy import text, inspect
from db import get_engine
from tools.registry import registry
from pydantic import BaseModel, Field
from typing import Optional, List

class GetDatabaseSchemaArgs(BaseModel):
    tables: Optional[List[str]] = Field(
        default=None, 
        description="List of table names to retrieve the schema for. Leave empty to get all tables."
    )

@registry.register(args_schema=GetDatabaseSchemaArgs)
def get_database_schema(tables: list[str] = None) -> str:
    """
    Returns the DDL/Schema structure of the requested tables.
    If tables is empty or None, returns the schema for all tables.
    """
    engine = get_engine()
    inspector = inspect(engine)
    
    available_tables = inspector.get_table_names()
    
    if not tables:
        tables = available_tables
    else:
        # Filter out requested tables that don't exist
        tables = [t for t in tables if t in available_tables]
        
    schema_str = ""
    for table_name in tables:
        schema_str += f"Table: {table_name}\n"
        columns = inspector.get_columns(table_name)
        for col in columns:
            col_type = col['type']
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            pk = "PRIMARY KEY" if col.get('primary_key') else ""
            schema_str += f"  - {col['name']} ({col_type}) {nullable} {pk}\n"
            
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            schema_str += f"  - FOREIGN KEY ({', '.join(fk['constrained_columns'])}) REFERENCES {fk['referred_table']} ({', '.join(fk['referred_columns'])})\n"
        schema_str += "\n"
        
    if not schema_str:
        return "No valid tables found."
        
    return schema_str

class ExecuteSqlArgs(BaseModel):
    query: str = Field(description="The SQL query to execute.")

@registry.register(args_schema=ExecuteSqlArgs)
def execute_sql_query(query: str) -> str:
    """
    Executes a SQL query. Only SELECT and INSERT are allowed.
    Returns the result rows (for SELECT) or success message (for INSERT).
    """
    query = query.strip()
    
    # Very basic safety check - block DELETE, UPDATE, DROP, ALTER, TRUNCATE, REPLACE
    forbidden_keywords = r'\b(DELETE|UPDATE|DROP|ALTER|TRUNCATE|REPLACE)\b'
    if re.search(forbidden_keywords, query, re.IGNORECASE):
        return "Error: Only SELECT and INSERT statements are allowed."
        
    is_select = query.upper().startswith("SELECT")
    
    engine = get_engine()
    try:
        with engine.begin() as conn:  # .begin() automatically commits/rolls back
            result = conn.execute(text(query))
            
            if is_select:
                rows = result.fetchall()
                columns = result.keys()
                
                if not rows:
                    return "Query executed successfully, but returned 0 rows."
                    
                output = f"Columns: {', '.join(columns)}\n"
                for row in rows:
                    output += str(dict(zip(columns, row))) + "\n"
                
                # Limit output size to prevent blowing up the context window
                if len(output) > 8000:
                    output = output[:8000] + "\n... (Results truncated due to length constraint)"
                    
                return output
            else:
                return f"Query executed successfully. Rows affected: {result.rowcount}"
                
    except Exception as e:
        return f"Database Error: {str(e)}"

class GetContactProfileArgs(BaseModel):
    name_query: str = Field(description="The name or partial name of the contact to search for (e.g., 'Azadeh').")

@registry.register(args_schema=GetContactProfileArgs)
def get_contact_profile(name_query: str) -> str:
    """
    Returns a comprehensive 360-degree profile of a person, including their background, interactions, and relationships.
    Use this tool whenever the user asks for information about a specific person.
    """
    engine = get_engine()
    
    # Try to find the contact first
    query_contact = text("SELECT * FROM Contact WHERE fullName LIKE :name OR chineseName LIKE :name OR displayName LIKE :name")
    
    try:
        with engine.begin() as conn:
            result = conn.execute(query_contact, {"name": f"%{name_query}%"}).fetchall()
            
            if not result:
                return json.dumps({"error": f"No contact found matching '{name_query}'."})
                
            # If multiple found, just take the first one for the summary
            contact_row = result[0]
            contact_id = contact_row.id
            
            # Helper to fetch rows to dict list
            def fetch_to_dict(query_str, params):
                res = conn.execute(text(query_str), params)
                return [dict(row._mapping) for row in res.fetchall()]
                
            contact_data = dict(contact_row._mapping)
            
            # Fetch related data
            backgrounds = fetch_to_dict("SELECT category, organization, titleOrMajor, startDate, endDate, description FROM BackgroundHistory WHERE contactId = :cid", {"cid": contact_id})
            methods = fetch_to_dict("SELECT type, label, value FROM ContactMethod WHERE contactId = :cid", {"cid": contact_id})
            interactions = fetch_to_dict("SELECT date, type, summary FROM Interaction WHERE contactId = :cid", {"cid": contact_id})
            daily_logs = fetch_to_dict("SELECT d.date, d.content FROM CRMInteractionLink c JOIN DailyLog d ON c.dailyLogId = d.id WHERE c.contactId = :cid", {"cid": contact_id})
            
            # Fetch Relations
            outgoing_rels = fetch_to_dict("SELECT cr.label, c.fullName as relatedPerson FROM ContactRelation cr JOIN Contact c ON cr.toId = c.id WHERE cr.fromId = :cid", {"cid": contact_id})
            incoming_rels = fetch_to_dict("SELECT cr.label, c.fullName as relatedPerson FROM ContactRelation cr JOIN Contact c ON cr.fromId = c.id WHERE cr.toId = :cid", {"cid": contact_id})
            
            profile = {
                "Contact": contact_data,
                "BackgroundHistory": backgrounds,
                "ContactMethods": methods,
                "Interactions": interactions,
                "DailyLogMentions": daily_logs,
                "RelatedPeople": {
                    "Outgoing": outgoing_rels,
                    "Incoming": incoming_rels
                }
            }
            
            return json.dumps(profile, default=str, indent=2)
            
    except Exception as e:
        return json.dumps({"error": f"Database Error: {str(e)}"})
