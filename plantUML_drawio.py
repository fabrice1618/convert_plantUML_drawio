#!/usr/bin/env python3
"""
Convertisseur PlantUML vers Draw.io
Support: diagrammes de séquence, classes, cas d'utilisation, activité
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from enum import Enum


class DiagramType(Enum):
    """Types de diagrammes UML supportés"""
    SEQUENCE = "sequence"
    CLASS = "class"
    USECASE = "usecase"
    ACTIVITY = "activity"
    COMPONENT = "component"
    STATE = "state"
    UNKNOWN = "unknown"


class PlantUMLParser:
    """Parse les fichiers PlantUML et extrait les éléments"""

    def __init__(self, content: str):
        self.content = content
        self.lines = [line.strip() for line in content.split('\n')]
        self.diagram_type = self._detect_diagram_type()

    def _detect_diagram_type(self) -> DiagramType:
        """Détecte le type de diagramme"""
        content_lower = self.content.lower()

        if '@startuml' not in content_lower:
            return DiagramType.UNKNOWN

        # Détection basée sur les mots-clés (ordre important: du plus spécifique au plus général)
        # Cas d'utilisation (avant séquence car partage "-->")
        if 'usecase' in content_lower:
            return DiagramType.USECASE
        # Diagramme de classes
        elif any(keyword in content_lower for keyword in ['class ', 'interface ', 'abstract class', 'extends', 'implements']):
            return DiagramType.CLASS
        # Diagramme de séquence (avant activité car partage certains mots-clés)
        elif 'participant' in content_lower or ('actor' in content_lower and '->' in content_lower):
            return DiagramType.SEQUENCE
        # Diagramme d'activité (vérifier les lignes commençant par start/stop)
        elif any(line.strip() in ['start', 'stop'] or line.strip().startswith('start ') or line.strip().startswith('stop ')
                 for line in content_lower.split('\n')):
            return DiagramType.ACTIVITY
        # Diagramme d'état
        elif any(keyword in content_lower for keyword in ['state ', '[*]']):
            return DiagramType.STATE
        # Diagramme de composants
        elif any(keyword in content_lower for keyword in ['component', 'package', 'node']):
            return DiagramType.COMPONENT
        # Messages de séquence simples
        elif any(keyword in content_lower for keyword in ['->', '<-', 'activate', 'deactivate']):
            return DiagramType.SEQUENCE

        return DiagramType.UNKNOWN

    def parse(self) -> Dict:
        """Parse le contenu selon le type de diagramme"""
        if self.diagram_type == DiagramType.SEQUENCE:
            return self._parse_sequence()
        elif self.diagram_type == DiagramType.CLASS:
            return self._parse_class()
        elif self.diagram_type == DiagramType.USECASE:
            return self._parse_usecase()
        elif self.diagram_type == DiagramType.ACTIVITY:
            return self._parse_activity()
        else:
            raise ValueError(f"Type de diagramme non supporté: {self.diagram_type}")

    def _parse_sequence(self) -> Dict:
        """Parse un diagramme de séquence"""
        participants = []
        messages = []

        for line in self.lines:
            # Participants
            if line.startswith('participant') or line.startswith('actor'):
                match = re.match(r'(participant|actor)\s+(?:"([^"]+)"|(\S+))(?:\s+as\s+(\S+))?', line)
                if match:
                    name = match.group(2) or match.group(3)
                    alias = match.group(4) or name
                    ptype = match.group(1)
                    participants.append({"name": name, "alias": alias, "type": ptype})

            # Messages
            elif '->' in line or '-->' in line or '<-' in line or '<--' in line:
                # Support plusieurs formats: A -> B: message, A -> B : message, etc.
                match = re.match(r'(\S+)\s*(<?-+>?)\s*(\S+)\s*:?\s*(.*)', line)
                if match:
                    source = match.group(1)
                    arrow = match.group(2)
                    target = match.group(3)
                    label = match.group(4).strip()

                    # Déterminer le type de message
                    is_return = arrow.startswith('<') or '-->' in arrow
                    is_async = '-->' in arrow or '<--' in arrow

                    messages.append({
                        "source": source,
                        "target": target,
                        "label": label,
                        "is_return": is_return,
                        "is_async": is_async
                    })

        return {
            "type": DiagramType.SEQUENCE,
            "participants": participants,
            "messages": messages
        }

    def _parse_class(self) -> Dict:
        """Parse un diagramme de classes"""
        classes = []
        relations = []
        current_class = None
        in_methods_section = False  # Pour gérer le séparateur --

        for line in self.lines:
            # Déclaration de classe ou enum
            if line.startswith('class ') or line.startswith('interface ') or line.startswith('abstract ') or line.startswith('enum '):
                match = re.match(r'(class|interface|abstract\s+class|enum)\s+(\S+)(?:\s+{)?', line)
                if match:
                    class_type = match.group(1)
                    class_name = match.group(2)
                    current_class = {
                        "name": class_name,
                        "type": class_type,
                        "attributes": [],
                        "methods": []
                    }
                    classes.append(current_class)
                    in_methods_section = False

            # Dans un bloc de classe/enum
            elif current_class and line and not line.startswith('}'):
                # Séparateur entre attributs et méthodes
                if line == '--':
                    in_methods_section = True
                # Méthode (contient des parenthèses) ou après le séparateur --
                elif '(' in line and ')' in line:
                    current_class["methods"].append(line)
                # Attribut (commence par +, -, # ou contient un type)
                elif line.startswith('+') or line.startswith('-') or line.startswith('#'):
                    if in_methods_section or ('(' in line and ')' in line):
                        current_class["methods"].append(line)
                    else:
                        current_class["attributes"].append(line)
                # Valeurs d'enum (lignes simples comme ETUDIANT, ADULTE, etc.)
                elif current_class["type"] == "enum" and re.match(r'^[A-Z_]+$', line):
                    current_class["attributes"].append(line)

            # Fin de bloc de classe
            elif line == '}':
                current_class = None
                in_methods_section = False

            # Relations (exclure les notes et autres)
            elif current_class is None and any(rel in line for rel in ['<|--', '--|>', '..|>', '<|..', '--', 'o--', '*--', '--o', '--*']):
                # Patterns pour les différentes relations
                # Héritage: A <|-- B ou A --|> B
                # Composition: A *-- B ou A --* B
                # Agrégation: A o-- B ou A --o B
                # Association: A -- B avec multiplicités optionnelles
                match = re.match(r'(\S+)\s*(?:"[^"]*")?\s*(<?\|?(?:--|\.\.)(?:o|\*)?>?\|?)\s*(?:"[^"]*")?\s*(\S+)(?:\s*:\s*(.*))?', line)
                if match:
                    source = match.group(1)
                    rel_type = match.group(2)
                    target = match.group(3)
                    label = match.group(4) or ""

                    # Déterminer le type de relation
                    if '<|--' in rel_type or '--|>' in rel_type:
                        rtype = "inheritance"
                    elif '<|..' in rel_type or '..|>' in rel_type:
                        rtype = "implementation"
                    elif 'o--' in rel_type or '--o' in rel_type:
                        rtype = "aggregation"
                    elif '*--' in rel_type or '--*' in rel_type:
                        rtype = "composition"
                    else:
                        rtype = "association"

                    relations.append({
                        "source": source,
                        "target": target,
                        "type": rtype,
                        "label": label
                    })

        return {
            "type": DiagramType.CLASS,
            "classes": classes,
            "relations": relations
        }

    def _parse_usecase(self) -> Dict:
        """Parse un diagramme de cas d'utilisation"""
        actors = []
        usecases = []
        relations = []
        system_name = None

        for line in self.lines:
            # Cadre du système (rectangle)
            if line.startswith('rectangle '):
                match = re.match(r'rectangle\s+"([^"]+)"', line)
                if match:
                    system_name = match.group(1)
            # Acteurs
            if line.startswith('actor '):
                match = re.match(r'actor\s+(?:"([^"]+)"|(\S+))(?:\s+as\s+(\S+))?(?:\s+<<(\w+)>>)?', line)
                if match:
                    name = match.group(1) or match.group(2)
                    alias = match.group(3) or name
                    stereotype = match.group(4)  # "secondary" ou None
                    is_secondary = stereotype == "secondary"
                    actors.append({"name": name, "alias": alias, "is_secondary": is_secondary})

            # Cas d'utilisation
            elif line.startswith('usecase ') or (line.startswith('(') and line.endswith(')')):
                if line.startswith('usecase '):
                    match = re.match(r'usecase\s+(?:"([^"]+)"|(\S+))(?:\s+as\s+(\S+))?', line)
                    if match:
                        name = match.group(1) or match.group(2)
                        # Convertir les \n littéraux en placeholder (sera remplacé par &#10; à la sauvegarde)
                        name = name.replace('\\n', '__NEWLINE__')
                        alias = match.group(3) or name
                        usecases.append({"name": name, "alias": alias})
                else:
                    # Format (Cas d'utilisation)
                    name = line.strip('()')
                    name = name.replace('\\n', '__NEWLINE__')
                    usecases.append({"name": name, "alias": name})

            # Relations
            elif '-->' in line or '..|>' in line or '--' in line:
                match = re.match(r'(\S+)\s*(-->|\.\.>|--)\s*(\S+)(?:\s*:\s*(.*))?', line)
                if match:
                    source = match.group(1)
                    rel_type = match.group(2)
                    target = match.group(3)
                    label = match.group(4) or ""

                    rtype = "association"
                    if '..|>' in rel_type or '..>' in rel_type:
                        rtype = "extends" if "extend" in label.lower() else "include"

                    relations.append({
                        "source": source,
                        "target": target,
                        "type": rtype,
                        "label": label
                    })

        return {
            "type": DiagramType.USECASE,
            "actors": actors,
            "usecases": usecases,
            "relations": relations,
            "system_name": system_name
        }

    def _parse_activity(self) -> Dict:
        """Parse un diagramme d'activité"""
        activities = []
        transitions = []
        prev_activity = "start"

        for line in self.lines:
            if line.startswith(':') and line.endswith(';'):
                # Activité
                activity_name = line.strip(':;').strip()
                activities.append({
                    "name": activity_name,
                    "type": "activity"
                })

                # Transition depuis l'activité précédente
                if prev_activity:
                    transitions.append({
                        "source": prev_activity,
                        "target": activity_name,
                        "label": ""
                    })
                prev_activity = activity_name

            elif line.startswith('if ') and line.endswith('then'):
                # Condition
                condition = line[3:-4].strip('()')
                activities.append({
                    "name": condition,
                    "type": "decision"
                })

                if prev_activity:
                    transitions.append({
                        "source": prev_activity,
                        "target": condition,
                        "label": ""
                    })
                prev_activity = condition

            elif line == 'stop':
                # Fin
                activities.append({
                    "name": "stop",
                    "type": "end"
                })

                if prev_activity:
                    transitions.append({
                        "source": prev_activity,
                        "target": "stop",
                        "label": ""
                    })

        return {
            "type": DiagramType.ACTIVITY,
            "activities": activities,
            "transitions": transitions
        }


class DrawIOGenerator:
    """Génère des fichiers Draw.io à partir de données parsées"""

    def __init__(self):
        self.cell_id = 2
        self.elements = {}

    def create_base_structure(self, diagram_name: str = "Diagram") -> Tuple[ET.Element, ET.Element]:
        """Crée la structure XML de base"""
        mxfile = ET.Element('mxfile', host="app.diagrams.net",
                           modified="2024-01-01T12:00:00.000Z",
                           agent="PlantUML to DrawIO Converter",
                           version="22.0.0", type="device")

        diagram = ET.SubElement(mxfile, 'diagram', name=diagram_name, id="diagram1")
        mxGraphModel = ET.SubElement(diagram, 'mxGraphModel',
                                     dx="1422", dy="794",
                                     grid="1", gridSize="10", guides="1",
                                     tooltips="1", connect="1", arrows="1",
                                     fold="1", page="1", pageScale="1",
                                     pageWidth="827", pageHeight="1169",
                                     math="0", shadow="0")

        root = ET.SubElement(mxGraphModel, 'root')
        ET.SubElement(root, 'mxCell', id="0")
        ET.SubElement(root, 'mxCell', id="1", parent="0")

        return mxfile, root

    def add_rectangle(self, root: ET.Element, label: str, x: int, y: int,
                     width: int = 120, height: int = 60,
                     style: str = "rounded=0;whiteSpace=wrap;html=1;") -> str:
        """Ajoute un rectangle"""
        elem_id = f"elem_{self.cell_id}"
        self.cell_id += 1

        cell = ET.SubElement(root, 'mxCell', id=elem_id, value=label,
                           style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                     width=str(width), height=str(height), **{'as': 'geometry'})

        return elem_id

    def add_ellipse(self, root: ET.Element, label: str, x: int, y: int,
                   width: int = 120, height: int = 60,
                   style: str = "ellipse;whiteSpace=wrap;html=1;") -> str:
        """Ajoute une ellipse"""
        elem_id = f"elem_{self.cell_id}"
        self.cell_id += 1

        cell = ET.SubElement(root, 'mxCell', id=elem_id, value=label,
                           style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                     width=str(width), height=str(height), **{'as': 'geometry'})

        return elem_id

    def add_actor(self, root: ET.Element, label: str, x: int, y: int) -> str:
        """Ajoute un acteur"""
        style = "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
        return self.add_rectangle(root, label, x, y, 30, 60, style)

    def add_secondary_actor(self, root: ET.Element, label: str, x: int, y: int) -> str:
        """Ajoute un acteur secondaire (système externe) avec icône bonhomme entourée d'un cadre"""
        # Créer le cadre rectangle autour de l'acteur
        frame_style = "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;strokeWidth=1;"
        frame_width, frame_height = 50, 80
        frame_x = x - 10  # Centrer le cadre autour de l'acteur
        self.add_rectangle(root, "", frame_x, y, frame_width, frame_height, frame_style)

        # Créer l'acteur (bonhomme) à l'intérieur du cadre
        actor_style = "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
        return self.add_rectangle(root, label, x, y + 10, 30, 60, actor_style)

    def add_arrow(self, root: ET.Element, source_id: str, target_id: str,
                 label: str = "", style: str = "endArrow=block;endFill=1;") -> str:
        """Ajoute une flèche entre deux éléments"""
        arrow_id = f"arrow_{self.cell_id}"
        self.cell_id += 1

        full_style = f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;{style}"

        cell = ET.SubElement(root, 'mxCell', id=arrow_id, value=label,
                           style=full_style, edge="1", parent="1",
                           source=source_id, target=target_id)
        ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})

        return arrow_id

    def add_arrow_with_points(self, root: ET.Element, label: str,
                            source_x: int, source_y: int,
                            target_x: int, target_y: int,
                            style: str = "endArrow=block;endFill=1;") -> str:
        """Ajoute une flèche avec des coordonnées directes"""
        arrow_id = f"arrow_{self.cell_id}"
        self.cell_id += 1

        full_style = f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;{style}"

        cell = ET.SubElement(root, 'mxCell', id=arrow_id, value=label,
                           style=full_style, edge="1", parent="1")

        geom = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
        ET.SubElement(geom, 'mxPoint', x=str(source_x), y=str(source_y), **{'as': 'sourcePoint'})
        ET.SubElement(geom, 'mxPoint', x=str(target_x), y=str(target_y), **{'as': 'targetPoint'})

        return arrow_id

    def generate_sequence_diagram(self, data: Dict) -> ET.Element:
        """Génère un diagramme de séquence"""
        mxfile, root = self.create_base_structure("Sequence Diagram")

        participants = data.get("participants", [])
        messages = data.get("messages", [])

        # Si pas de participants explicites, les extraire des messages
        if not participants:
            participant_names = set()
            for msg in messages:
                participant_names.add(msg["source"])
                participant_names.add(msg["target"])
            participants = [{"name": name, "alias": name, "type": "participant"}
                          for name in participant_names]

        # Placer les participants
        x_start = 50
        x_spacing = 180
        y_start = 100

        participant_positions = {}
        for i, participant in enumerate(participants):
            x = x_start + i * x_spacing
            name = participant["name"]

            if participant["type"] == "actor":
                elem_id = self.add_actor(root, name, x, y_start)
            else:
                style = "rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
                elem_id = self.add_rectangle(root, name, x, y_start, 120, 40, style)

            # Ligne de vie
            lifeline_id = f"lifeline_{self.cell_id}"
            self.cell_id += 1
            cell = ET.SubElement(root, 'mxCell', id=lifeline_id, value="",
                               style="dashed=1;html=1;strokeColor=#666666;",
                               edge="1", parent="1", source=elem_id)
            geom = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
            points = ET.SubElement(geom, 'Array', **{'as': 'points'})
            ET.SubElement(points, 'mxPoint', x=str(x + 60), y="700")

            participant_positions[participant["alias"]] = (x + 60, y_start + 40)
            self.elements[participant["alias"]] = elem_id

        # Ajouter les messages
        y_pos = y_start + 100
        y_spacing = 50

        for msg in messages:
            source_pos = participant_positions.get(msg["source"])
            target_pos = participant_positions.get(msg["target"])

            if source_pos and target_pos:
                # Style selon le type de message
                if msg.get("is_return"):
                    style = "dashed=1;endArrow=open;endFill=0;"
                elif msg.get("is_async"):
                    style = "endArrow=open;endFill=0;"
                else:
                    style = "endArrow=block;endFill=1;"

                self.add_arrow_with_points(root, msg["label"],
                                          source_pos[0], y_pos,
                                          target_pos[0], y_pos,
                                          style)
                y_pos += y_spacing

        return mxfile

    def add_class_box(self, root: ET.Element, cls: Dict, x: int, y: int) -> str:
        """Ajoute une classe UML avec format HTML (3 compartiments)"""
        name = cls["name"]
        class_type = cls.get("type", "class")
        attributes = cls.get("attributes", [])
        methods = cls.get("methods", [])

        # Calculer la largeur basée sur le contenu
        max_text_len = len(name)
        for attr in attributes:
            max_text_len = max(max_text_len, len(attr))
        for method in methods:
            max_text_len = max(max_text_len, len(method))
        width = max(160, min(320, max_text_len * 7 + 20))

        # Calculer la hauteur
        line_height = 18
        title_lines = 2 if class_type in ["interface", "enum"] else 1
        title_height = title_lines * 20 + 10
        attr_height = max(20, len(attributes) * line_height + 10)
        method_height = max(20, len(methods) * line_height + 10)
        total_height = title_height + attr_height + method_height

        # ID de la classe
        class_id = f"class_{self.cell_id}"
        self.cell_id += 1

        # Construire le contenu HTML
        html_parts = []

        # Titre (avec stéréotype pour interface/enum)
        if class_type == "interface":
            html_parts.append(f'<p style="margin:0px;text-align:center;"><i>&lt;&lt;interface&gt;&gt;</i></p>')
            html_parts.append(f'<p style="margin:0px;text-align:center;"><b>{name}</b></p>')
            fill_color = "#fff2cc"
            stroke_color = "#d6b656"
        elif class_type == "enum":
            html_parts.append(f'<p style="margin:0px;text-align:center;">&lt;&lt;enumeration&gt;&gt;</p>')
            html_parts.append(f'<p style="margin:0px;text-align:center;"><b>{name}</b></p>')
            fill_color = "#e1d5e7"
            stroke_color = "#9673a6"
        else:
            html_parts.append(f'<p style="margin:0px;text-align:center;"><b>{name}</b></p>')
            fill_color = "#dae8fc"
            stroke_color = "#6c8ebf"

        # Séparateur
        html_parts.append('<hr size="1"/>')

        # Attributs
        if attributes:
            for attr in attributes:
                html_parts.append(f'<p style="margin:0px;margin-left:4px;">{attr}</p>')
        else:
            html_parts.append('<p style="margin:0px;">&nbsp;</p>')

        # Séparateur
        html_parts.append('<hr size="1"/>')

        # Méthodes
        if methods:
            for method in methods:
                html_parts.append(f'<p style="margin:0px;margin-left:4px;">{method}</p>')
        else:
            html_parts.append('<p style="margin:0px;">&nbsp;</p>')

        html_content = "".join(html_parts)

        # Style du rectangle
        style = f"verticalAlign=top;align=left;overflow=fill;html=1;rounded=0;shadow=0;comic=0;labelBackgroundColor=none;strokeColor={stroke_color};strokeWidth=1;fillColor={fill_color};"

        # Créer la cellule
        cell = ET.SubElement(root, 'mxCell', id=class_id, value=html_content,
                            style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                     width=str(width), height=str(total_height), **{'as': 'geometry'})

        return class_id

    def generate_class_diagram(self, data: Dict) -> ET.Element:
        """Génère un diagramme de classes"""
        mxfile, root = self.create_base_structure("Class Diagram")

        classes = data.get("classes", [])
        relations = data.get("relations", [])

        # Disposition en grille - espacement augmenté pour les swimlanes
        x_start = 50
        y_start = 50
        x_spacing = 320
        y_spacing = 250
        cols = 3

        class_positions = {}

        for i, cls in enumerate(classes):
            col = i % cols
            row = i // cols
            x = x_start + col * x_spacing
            y = y_start + row * y_spacing

            elem_id = self.add_class_box(root, cls, x, y)
            class_positions[cls["name"]] = elem_id
            self.elements[cls["name"]] = elem_id

        # Ajouter les relations
        for rel in relations:
            source_id = class_positions.get(rel["source"])
            target_id = class_positions.get(rel["target"])

            if source_id and target_id:
                # Style selon le type de relation
                if rel["type"] == "inheritance":
                    style = "endArrow=block;endFill=0;endSize=12;"
                elif rel["type"] == "implementation":
                    style = "dashed=1;endArrow=block;endFill=0;endSize=12;"
                elif rel["type"] == "composition":
                    style = "endArrow=diamondThin;endFill=1;endSize=12;"
                elif rel["type"] == "aggregation":
                    style = "endArrow=diamondThin;endFill=0;endSize=12;"
                else:
                    style = "endArrow=none;endFill=0;"

                self.add_arrow(root, source_id, target_id, rel.get("label", ""), style)

        return mxfile

    def generate_usecase_diagram(self, data: Dict) -> ET.Element:
        """Génère un diagramme de cas d'utilisation"""
        mxfile, root = self.create_base_structure("Use Case Diagram")

        actors = data.get("actors", [])
        usecases = data.get("usecases", [])
        relations = data.get("relations", [])
        system_name = data.get("system_name")

        # Séparer les acteurs primaires et secondaires
        primary_actors = [a for a in actors if not a.get("is_secondary")]
        secondary_actors = [a for a in actors if a.get("is_secondary")]

        # Disposition: acteurs primaires à gauche, cas d'utilisation au centre, acteurs secondaires à droite
        actor_x = 50
        usecase_x_start = 250
        secondary_x = usecase_x_start + 200  # À droite des use cases
        y_start = 100
        y_spacing = 90

        element_ids = {}

        # Ajouter le cadre du système (rectangle englobant les use cases)
        if system_name and usecases:
            system_x = usecase_x_start - 30
            system_y = y_start - 50
            system_width = 200
            system_height = len(usecases) * y_spacing + 50
            system_style = "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;verticalAlign=top;fontStyle=1;"
            self.add_rectangle(root, system_name, system_x, system_y, system_width, system_height, system_style)

        # Ajouter les acteurs primaires à gauche
        for i, actor in enumerate(primary_actors):
            y = y_start + i * y_spacing
            elem_id = self.add_actor(root, actor["name"], actor_x, y)
            element_ids[actor["alias"]] = elem_id

        # Ajouter les acteurs secondaires à droite
        for i, actor in enumerate(secondary_actors):
            y = y_start + i * y_spacing
            elem_id = self.add_secondary_actor(root, actor["name"], secondary_x, y)
            element_ids[actor["alias"]] = elem_id

        # Ajouter les cas d'utilisation
        for i, usecase in enumerate(usecases):
            y = y_start + i * y_spacing
            style = "ellipse;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;"
            elem_id = self.add_ellipse(root, usecase["name"],
                                      usecase_x_start, y, 140, 70, style)
            element_ids[usecase["alias"]] = elem_id

        # Ajouter les relations
        for rel in relations:
            source_id = element_ids.get(rel["source"])
            target_id = element_ids.get(rel["target"])

            if source_id and target_id:
                if rel["type"] in ["extends", "include"]:
                    style = "dashed=1;endArrow=open;endFill=0;"
                    label = f"<<{rel['type']}>>"
                else:
                    style = "endArrow=none;endFill=0;"
                    label = rel.get("label", "")

                self.add_arrow(root, source_id, target_id, label, style)

        return mxfile

    def generate_activity_diagram(self, data: Dict) -> ET.Element:
        """Génère un diagramme d'activité"""
        mxfile, root = self.create_base_structure("Activity Diagram")

        activities = data.get("activities", [])
        transitions = data.get("transitions", [])

        # Disposition verticale
        x_center = 300
        y_start = 100
        y_spacing = 100

        element_ids = {}

        # Ajouter le point de départ
        start_style = "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=#000000;"
        start_id = self.add_ellipse(root, "", x_center - 15, y_start - 50, 30, 30, start_style)
        element_ids["start"] = start_id

        # Ajouter les activités
        for i, activity in enumerate(activities):
            y = y_start + i * y_spacing
            name = activity["name"]

            if activity["type"] == "decision":
                # Losange pour les décisions
                style = "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
                elem_id = self.add_rectangle(root, name, x_center - 60, y, 120, 80, style)
            elif activity["type"] == "end":
                # Point final
                style = "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=#000000;"
                elem_id = self.add_ellipse(root, "", x_center - 15, y, 30, 30, style)
            else:
                # Activité normale
                style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
                elem_id = self.add_rectangle(root, name, x_center - 80, y, 160, 60, style)

            element_ids[name] = elem_id

        # Ajouter les transitions
        for trans in transitions:
            source_id = element_ids.get(trans["source"])
            target_id = element_ids.get(trans["target"])

            if source_id and target_id:
                style = "endArrow=block;endFill=1;"
                self.add_arrow(root, source_id, target_id, trans.get("label", ""), style)

        return mxfile

    def save_to_file(self, mxfile: ET.Element, output_path: str):
        """Sauvegarde le XML dans un fichier"""
        xml_str = ET.tostring(mxfile, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")
        # Remplacer les placeholders par les entités/caractères XML appropriés (après pretty printing)
        pretty_xml = pretty_xml.replace('__NEWLINE__', '&#10;')
        pretty_xml = pretty_xml.replace('__LT__', '&lt;')
        pretty_xml = pretty_xml.replace('__GT__', '&gt;')

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)


def convert_plantuml_to_drawio(input_file: str, output_file: Optional[str] = None) -> bool:
    """Convertit un fichier PlantUML en Draw.io"""

    try:
        # Lire le fichier PlantUML
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parser le contenu
        parser = PlantUMLParser(content)

        if parser.diagram_type == DiagramType.UNKNOWN:
            print(f"Erreur: Type de diagramme non reconnu dans {input_file}")
            return False

        print(f"Type de diagramme détecté: {parser.diagram_type.value}")

        # Parser les données
        data = parser.parse()

        # Générer le diagramme Draw.io
        generator = DrawIOGenerator()

        if parser.diagram_type == DiagramType.SEQUENCE:
            mxfile = generator.generate_sequence_diagram(data)
        elif parser.diagram_type == DiagramType.CLASS:
            mxfile = generator.generate_class_diagram(data)
        elif parser.diagram_type == DiagramType.USECASE:
            mxfile = generator.generate_usecase_diagram(data)
        elif parser.diagram_type == DiagramType.ACTIVITY:
            mxfile = generator.generate_activity_diagram(data)
        else:
            print(f"Erreur: Conversion non implémentée pour {parser.diagram_type.value}")
            return False

        # Déterminer le nom du fichier de sortie
        if output_file is None:
            input_path = Path(input_file)
            output_file = input_path.with_suffix('.drawio').name

        # Sauvegarder
        generator.save_to_file(mxfile, output_file)

        print(f"Conversion réussie: {output_file}")
        print(f"Ouvrez avec Draw.io: https://app.diagrams.net/")

        return True

    except FileNotFoundError:
        print(f"Erreur: Fichier non trouvé: {input_file}")
        return False
    except Exception as e:
        print(f"Erreur lors de la conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(
        description="Convertit des diagrammes PlantUML en format Draw.io",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s diagram.puml
  %(prog)s diagram.puml -o output.drawio
  %(prog)s *.puml

Types de diagrammes supportés:
  - Diagrammes de séquence
  - Diagrammes de classes
  - Diagrammes de cas d'utilisation
  - Diagrammes d'activité
        """
    )

    parser.add_argument('input_files', nargs='+',
                       help='Fichier(s) PlantUML à convertir')
    parser.add_argument('-o', '--output',
                       help='Nom du fichier de sortie (pour un seul fichier)')

    args = parser.parse_args()

    # Si plusieurs fichiers et un output spécifié, erreur
    if len(args.input_files) > 1 and args.output:
        print("Erreur: -o/--output ne peut être utilisé qu'avec un seul fichier d'entrée")
        return 1

    # Convertir chaque fichier
    success_count = 0
    for input_file in args.input_files:
        output_file = args.output if len(args.input_files) == 1 else None

        print(f"\nConversion de {input_file}...")
        if convert_plantuml_to_drawio(input_file, output_file):
            success_count += 1

    print(f"\n{success_count}/{len(args.input_files)} fichier(s) converti(s) avec succès")

    return 0 if success_count == len(args.input_files) else 1


if __name__ == "__main__":
    sys.exit(main())
