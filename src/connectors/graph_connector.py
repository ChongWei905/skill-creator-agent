"""Compatibility shim for generated skill scripts.

The runtime adds ``src/`` to ``PYTHONPATH`` when executing skills, and current
skill prompts instruct scripts to use ``from connectors import GraphConnector``.
Re-exporting the package implementation here preserves that contract.
"""

from skill_creator_agent.connectors.graph_connector import GraphConnector

__all__ = ["GraphConnector"]
