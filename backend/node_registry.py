from typing import Callable, Dict, Any

class NodeRegistry:
    def __init__(self):
        self._generators: Dict[str, Callable] = {}

    def register(self, node_type: str):
        def decorator(func: Callable):
            self._generators[node_type] = func
            return func
        return decorator

    def get_generator(self, node_type: str) -> Callable:
        return self._generators.get(node_type)

    def has_node(self, node_type: str) -> bool:
        return node_type in self._generators

node_registry = NodeRegistry()
