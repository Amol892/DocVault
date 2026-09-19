"""Authentication and authorization dependencies.

This module is the ONLY place role/membership checks live. Routes must depend on
what is defined here and never re-implement checks. See PRD/06-permission-matrix.md.
"""
