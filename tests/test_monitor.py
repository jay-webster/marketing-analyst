import pytest
from monitor import _detect_website_changes

# Test 1: No changes detected
def test_detect_website_changes_no_change():
    # The code expects a NESTED dictionary structure
    prev_data = {
        "content": {
            "value_proposition": "Same old content"
        }
    }
    current_val_prop = "Same old content"
    
    # Should return False (no change)
    assert _detect_website_changes(prev_data, current_val_prop) is False

# Test 2: Significant change detected
def test_detect_website_changes_found_diff():
    prev_data = {
        "content": {
            "value_proposition": "We sell shoes"
        }
    }
    current_val_prop = "We sell hats now"
    
    # Should return True (change detected)
    assert _detect_website_changes(prev_data, current_val_prop) is True

# Test 3: One input is missing/None (The Bug We Just Fixed)
def test_detect_website_changes_none_input():
    # If previous data is None, it should return True (New Data) without crashing
    assert _detect_website_changes(None, "New stuff") is True
    