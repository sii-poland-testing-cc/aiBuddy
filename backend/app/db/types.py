"""
Custom SQLAlchemy column types.

JsonType
--------
Stores any JSON-serialisable Python value (dict, list, str, int, …) as a
TEXT column in the database.  Serialisation / deserialisation is handled
transparently at the ORM boundary — callers never call json.dumps / json.loads
on model attributes.

  • NULL in DB  →  None in Python
  • Write:  value → json.dumps(value)
  • Read:   text  → json.loads(text)

Usage in a model::

    from app.db.types import JsonType

    class Project(Base):
        mind_map: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
        context_files: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
"""

import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class JsonType(TypeDecorator):
    """TEXT column that transparently serialises/deserialises JSON values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Python → DB: serialise to JSON string."""
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        """DB → Python: deserialise from JSON string."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
