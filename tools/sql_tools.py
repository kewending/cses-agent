import os
import re
from sqlalchemy import text, inspect
from db import get_engine

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
