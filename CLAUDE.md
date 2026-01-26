# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlantUML to Draw.io converter - a Python script that converts UML diagrams from PlantUML format (.puml) to Draw.io format (.drawio).

## Commands

```bash
# Convert a single file
python3 plantUML_drawio.py diagram.puml

# Convert with specific output name
python3 plantUML_drawio.py diagram.puml -o output.drawio

# Convert multiple files
python3 plantUML_drawio.py *.puml

# Test with example files
python3 plantUML_drawio.py test/*.puml
```

No dependencies beyond Python standard library are required.

## Architecture

The converter consists of two main classes in `plantUML_drawio.py`:

### PlantUMLParser
- Parses PlantUML content and auto-detects diagram type via `_detect_diagram_type()`
- Specialized parsing methods: `_parse_sequence()`, `_parse_class()`, `_parse_usecase()`, `_parse_activity()`
- Returns structured dict with diagram elements

### DrawIOGenerator
- Creates Draw.io XML structure with `create_base_structure()`
- Shape primitives: `add_rectangle()`, `add_ellipse()`, `add_actor()`, `add_arrow()`
- Diagram generators: `generate_sequence_diagram()`, `generate_class_diagram()`, `generate_usecase_diagram()`, `generate_activity_diagram()`

### Supported Diagram Types (DiagramType enum)
- SEQUENCE: participants, actors, messages (sync/async/return)
- CLASS: classes, interfaces, attributes, methods, relations (inheritance, composition, aggregation)
- USECASE: actors, use cases, include/extend relations
- ACTIVITY: activities, decisions, start/stop points, transitions

## Adding New Diagram Types

1. Add type to `DiagramType` enum
2. Add detection logic in `PlantUMLParser._detect_diagram_type()`
3. Create `_parse_xxx()` method in `PlantUMLParser`
4. Create `generate_xxx_diagram()` method in `DrawIOGenerator`
5. Add case in `convert_plantuml_to_drawio()` function
