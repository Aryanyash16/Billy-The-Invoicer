import importlib.util
from pathlib import Path


def test_normalization():
    spec = importlib.util.spec_from_file_location("evaluate_jsonl", Path("scripts/evaluate_jsonl.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.norm("total", "$1,200.00") == "1200.00"
    assert module.norm("invoice_number", "INV- 001") == "inv001"
