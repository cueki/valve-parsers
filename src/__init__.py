"""
Valve Parsers - A Python library for parsing Valve game engine files

This library provides parsers for:
- VPK (Valve Packaged) files - Valve's archive format
- PCF (Particle File) files - Valve's particle system files
- MDL (Source model) files - read materials/materialDirectories and rewrite the latter

Author: Extracted from casual-pre-loader project
License: MIT
"""

from .vpk import VPKFile, VPKDirectoryEntry
from .pcf import PCFFile, PCFElement
from .mdl import MDLFile
from .constants import PCFVersion, AttributeType

__all__ = [
    "VPKFile",
    "VPKDirectoryEntry",
    "PCFFile",
    "PCFElement",
    "MDLFile",
    "PCFVersion",
    "AttributeType",
]
