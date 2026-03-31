"""Compatibility shim for generated skill scripts.

The runtime adds the repository root to ``PYTHONPATH`` when executing skills, and current
skill prompts instruct scripts to use ``from connectors import GraphConnector``.
Re-exporting the package implementation here preserves that contract.
"""

__all__ = ["GraphConnector"]

from knowledge_skills.connectors.graph_connector import GraphConnector
