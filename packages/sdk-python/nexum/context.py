from typing import Any


class ContextView:
    def __init__(self, input_data: dict, outputs: dict[str, Any]):
        self.input = input_data
        self._outputs = outputs

    def get(self, node_id: str) -> Any:
        if node_id not in self._outputs:
            raise KeyError(f"Node '{node_id}' not completed yet. Available: {list(self._outputs.keys())}")
        return self._outputs[node_id]

    def get_map_results(self, map_node_id: str) -> list:
        result = self._outputs.get(map_node_id)
        if not isinstance(result, list):
            raise TypeError(f"'{map_node_id}' is not a MAP node or not completed")
        return result
