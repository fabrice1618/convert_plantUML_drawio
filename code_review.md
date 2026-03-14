# Revue de code - `plantUML_drawio.py`

## Bugs / problèmes de fiabilité

### 1. Détection fragile par mots-clés dans le contenu brut (L36-67)

La détection cherche des sous-chaînes dans `content_lower` **commentaires et chaînes inclus**. Un commentaire `' extends the usecase` suffit à déclencher un faux positif CLASS + USECASE. De même `'class '` matche `subclass ` ou `classique `.

**Correction** : ne scanner que les lignes hors commentaires, et utiliser des regex avec limites de mot (`\bclass\b`).

### 2. `_parse_component` ne gère pas les éléments sans guillemets (L602-606)

Les regex exigent `"..."` autour du nom, mais PlantUML autorise `node MonNoeud {` ou `component MonComposant as C`. Les alias sans guillemets ne sont pas parsés.

### 3. `_parse_component` : `}` sur la même ligne que du contenu est ignoré (L618)

Si un fichier contient `component "X" as X }` ou des accolades mixtes, la pile `parent_stack` sera désynchronisée. Il faudrait compter les `{` et `}` par ligne.

### 4. Connexions non résolues silencieusement ignorées (L1011-1014)

Si un alias est mal orthographié dans une connexion, il est silencieusement sauté. Un `print(f"Warning: connexion ignorée {conn['source']} -> {conn['target']}")` aiderait au debug.

### 5. `element_map` retourné mais jamais utilisé (L675)

`_parse_component()` retourne `element_map` dans le dict mais `generate_component_diagram()` ne l'utilise pas. Donnée morte.

---

## Duplication de code / architecture

### 6. 4 méthodes quasi-identiques pour créer des cellules

`add_rectangle()`, `add_ellipse()`, `add_cell()` font exactement la même chose avec des signatures quasi-identiques. `add_rectangle` et `add_ellipse` hardcodent `parent="1"` alors que `add_cell` le paramétrise. On pourrait unifier :

```python
def add_cell(self, root, label, x, y, width, height, style, parent_id="1"):
    ...
```

Et les anciennes méthodes deviennent des alias/raccourcis. Ça évite aussi le bug potentiel si on veut imbriquer dans un autre type de diagramme.

### 7. Chaîne if/elif répétée dans `parse()` et `convert_plantuml_to_drawio()`

Le dispatch par type de diagramme est dupliqué à deux endroits (L69-82 et L1519-1531). Un dictionnaire de dispatch serait plus maintenable :

```python
PARSERS = {DiagramType.SEQUENCE: '_parse_sequence', ...}
GENERATORS = {DiagramType.SEQUENCE: 'generate_sequence_diagram', ...}
```

### 8. Données de layout mélangées avec les données du modèle

`_compute_component_size()` écrit `rel_x`, `rel_y`, `width`, `height` directement dans les dicts du parser. Ça couple parsing et rendu. Si on voulait générer un autre format de sortie, il faudrait re-parser. Mieux : stocker les positions dans un dict séparé `layout[elem_id] = {x, y, w, h}`.

---

## Robustesse

### 9. `self.lines` strip l'indentation une seule fois (L33)

Le strip est fait dans `__init__`, ce qui convient pour la plupart des parsers. Mais `_parse_activity` fait `line.startswith(':')` qui dépend de ce strip. Si quelqu'un change le strip, tout casse. Ce couplage implicite est fragile.

### 10. Pas de validation de l'input

Aucun parser ne vérifie que `@startuml`/`@enduml` encadrent bien le contenu. Un fichier tronqué ou mal formé peut produire un résultat partiel sans aucune erreur.

### 11. Regex de connexion component trop restrictive (L608-609)

`conn_re` exige `(\w+)` pour source/target, mais les alias auto-générés `_auto_1` matchent grâce au `_`. Par contre un alias avec tiret (`mon-alias`) ne matcherait pas. PlantUML autorise certains alias avec tirets.

---

## Performance / maintenabilité

### 12. `import traceback` au runtime (L1551)

L'import est dans le bloc `except`. Mieux vaut l'importer en tête de fichier avec les autres imports.

### 13. Docstring du module obsolète (L2-5)

Mentionne "séquence, classes, cas d'utilisation, activité" mais ne mentionne pas COMPONENT (ni STATE détecté mais non supporté).

### 14. `self.elements` dans DrawIOGenerator (L684)

Cet attribut `self.elements` est écrit par `generate_sequence_diagram` et `generate_class_diagram` mais jamais lu. C'est du code mort.

---

## Améliorations possibles (évolutions)

### 15. Support de `@startcomponent` / `@startdeployment`

PlantUML supporte ces directives spécialisées en plus de `@startuml`. Les détecter simplifierait la détection de type.

### 16. Tests automatisés

Aucun test unitaire. Au minimum des tests de détection de type et de parsing pour chaque type de diagramme éviteraient les régressions (ex: le bug de détection SEQUENCE au lieu de COMPONENT aurait été attrapé).

### 17. Le placeholder `__NEWLINE__` est fragile

Si un label contient littéralement `__NEWLINE__`, il sera corrompu. Un caractère Unicode improbable (ex: `\x00`) ou un passage par un dictionnaire de substitution serait plus sûr.

---

## Résumé par priorité

| Priorité | # | Problème |
|----------|---|----------|
| Haute | 1 | Détection faux positifs (commentaires, sous-chaînes) |
| Haute | 4 | Connexions non résolues silencieuses |
| Haute | 16 | Absence de tests |
| Moyenne | 2,3 | Parsing component incomplet (sans guillemets, accolades mixtes) |
| Moyenne | 6,7 | Duplication code (cellules, dispatch) |
| Moyenne | 8 | Couplage layout/modèle |
| Faible | 5,14 | Code mort (`element_map`, `self.elements`) |
| Faible | 10,12,13,17 | Robustesse et hygiène |
