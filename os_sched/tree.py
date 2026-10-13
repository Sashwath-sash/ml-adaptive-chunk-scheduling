"""Tiny deterministic CART classifier, so the Linux demo needs no ML package."""
from collections import Counter


class DecisionTree:
    def __init__(self, max_depth=3, min_leaf=3):
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.root = None

    def fit(self, rows, labels):
        if not rows or len(rows) != len(labels):
            raise ValueError("nonempty equal-length rows and labels required")
        self.root = self._build(list(zip(rows, labels)), 0)
        return self

    @staticmethod
    def _gini(items):
        n = len(items)
        return 1 - sum((v / n) ** 2 for v in Counter(y for _, y in items).values())

    def _build(self, items, depth):
        majority = Counter(y for _, y in items).most_common(1)[0][0]
        if depth >= self.max_depth or len(items) < 2 * self.min_leaf or self._gini(items) == 0:
            return {"value": majority, "n": len(items)}
        best = None
        for feature in range(len(items[0][0])):
            values = sorted(set(float(x[feature]) for x, _ in items))
            for a, b in zip(values, values[1:]):
                threshold = (a + b) / 2
                left = [(x, y) for x, y in items if x[feature] <= threshold]
                right = [(x, y) for x, y in items if x[feature] > threshold]
                if min(len(left), len(right)) < self.min_leaf:
                    continue
                score = (len(left) * self._gini(left) + len(right) * self._gini(right)) / len(items)
                if best is None or score < best[0]:
                    best = (score, feature, threshold, left, right)
        if best is None or best[0] >= self._gini(items):
            return {"value": majority, "n": len(items)}
        _, feature, threshold, left, right = best
        return {"feature": feature, "threshold": threshold,
                "left": self._build(left, depth + 1), "right": self._build(right, depth + 1),
                "value": majority, "n": len(items)}

    def predict_one(self, row):
        node = self.root
        if node is None:
            raise RuntimeError("model not fitted")
        while "feature" in node:
            node = node["left"] if row[node["feature"]] <= node["threshold"] else node["right"]
        return node["value"]

    def to_dict(self):
        return {"max_depth": self.max_depth, "min_leaf": self.min_leaf, "root": self.root}

    @classmethod
    def from_dict(cls, data):
        model = cls(data["max_depth"], data["min_leaf"])
        model.root = data["root"]
        return model
