# test_data_reader.py
# Purpose: Unit tests for src/data_reader.py
# Run with: python -m pytest tests/
# TODO: Expand tests as data_reader.py is implemented in Step 2

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_reader import find_merchant


def test_find_existing_merchant():
    """Should return campaign data when merchant exists."""
    result = find_merchant("KFC")
    assert result is not None
    assert result["Merchant"].upper() == "KFC"


def test_find_merchant_case_insensitive():
    """Search should work regardless of letter case."""
    result = find_merchant("kfc")
    assert result is not None


def test_find_nonexistent_merchant():
    """Should return None when merchant is not in the spreadsheet."""
    result = find_merchant("NonExistentBrand")
    assert result is None


def test_result_has_required_fields():
    """Campaign dict must contain all fields the email generator needs."""
    result = find_merchant("KFC")
    required_fields = [
        "Merchant", "Campaign Name", "Timeline",
        "Scheme", "Channel", "Budget", "CTA"
    ]
    for field in required_fields:
        assert field in result, f"Missing field: {field}"
