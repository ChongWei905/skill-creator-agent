"""Compatibility exports for generated skill scripts.

Generated skills currently import ``GraphConnector`` via
``from connectors import GraphConnector``. This top-level package keeps that
import path stable while the real implementation lives under
``knowledge_skills.connectors``.
"""

from .graph_connector import GraphConnector

__all__ = ["GraphConnector"]
