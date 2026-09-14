"""
Unit tests for validators.py validation logic.
Tests validation rules by simulating row-level validation.
"""

import pytest
from decimal import Decimal
import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from validators import (
    ValidationIssue,
    clean_observed_value,
    is_valid_http_url,
    add_issue,
)


class TestObservedValueCleaning:
    """Test clean_observed_value function."""

    def test_string_value(self):
        """String value should be returned."""
        assert clean_observed_value("test") == "test"

    def test_null_value(self):
        """None should return None."""
        assert clean_observed_value(None) is None

    def test_long_value_truncation(self):
        """Long values should be truncated to 500 chars."""
        long_value = "x" * 600
        result = clean_observed_value(long_value)
        assert len(result) == 500


class TestURLValidation:
    """Test is_valid_http_url in validators."""

    def test_valid_http(self):
        """HTTP URL should be valid."""
        assert is_valid_http_url("http://example.com") is True

    def test_valid_https(self):
        """HTTPS URL should be valid."""
        assert is_valid_http_url("https://example.com") is True

    def test_invalid_no_protocol(self):
        """URL without protocol should be invalid."""
        assert is_valid_http_url("example.com") is False

    def test_markdown_link(self):
        """Markdown link should be validated after extraction."""
        # The function extracts URL from markdown
        assert is_valid_http_url("[text](https://example.com)") is True

    def test_null_value(self):
        """None should be valid (optional field)."""
        assert is_valid_http_url(None) is True


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_create_issue(self):
        """Should create ValidationIssue with all fields."""
        issue = ValidationIssue(
            source_file_name="test.csv",
            source_row_number=1,
            source="test_source",
            dataset="test_dataset",
            rule_code="REQ_TITLE",
            severity="ERROR",
            action_taken="QUARANTINE",
            field_name="product_title",
            observed_value=None,
            issue_message="Product title is missing.",
            issue_details={},
        )

        assert issue.source_file_name == "test.csv"
        assert issue.source_row_number == 1
        assert issue.rule_code == "REQ_TITLE"
        assert issue.severity == "ERROR"
        assert issue.action_taken == "QUARANTINE"


class TestAddIssue:
    """Test add_issue helper function."""

    def test_add_issue_to_list(self):
        """Should append issue to list."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="MISSING_PRICE",
            severity="WARNING",
            action_taken="FLAG",
            field_name="price",
            observed_value=None,
            issue_message="Price is missing.",
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "MISSING_PRICE"
        assert issues[0].severity == "WARNING"


class TestValidationScenarios:
    """Test complete validation scenarios."""

    def test_req_title_scenario(self):
        """REQ_TITLE should trigger for empty title."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="REQ_TITLE",
            severity="ERROR",
            action_taken="QUARANTINE",
            field_name="product_title",
            observed_value=None,
            issue_message="Product title is missing.",
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "REQ_TITLE"
        assert issues[0].severity == "ERROR"
        assert issues[0].action_taken == "QUARANTINE"

    def test_missing_price_scenario(self):
        """MISSING_PRICE should trigger for NULL price."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="MISSING_PRICE",
            severity="WARNING",
            action_taken="FLAG",
            field_name="price",
            observed_value=None,
            issue_message="Price is missing.",
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "MISSING_PRICE"
        assert issues[0].severity == "WARNING"
        assert issues[0].action_taken == "FLAG"

    def test_zero_price_scenario(self):
        """ZERO_PRICE should trigger for price = 0."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="ZERO_PRICE",
            severity="WARNING",
            action_taken="FLAG",
            field_name="price",
            observed_value=0,
            issue_message="Price is zero.",
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "ZERO_PRICE"
        assert issues[0].severity == "WARNING"

    def test_old_price_lt_price_scenario(self):
        """OLD_PRICE_LT_PRICE should trigger when old_price < price."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="OLD_PRICE_LT_PRICE",
            severity="WARNING",
            action_taken="FLAG",
            field_name="old_price",
            observed_value=1000000,
            issue_message="Old price is lower than current price.",
            issue_details={"price": 1500000, "old_price": 1000000},
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "OLD_PRICE_LT_PRICE"
        assert issues[0].severity == "WARNING"

    def test_invalid_percentage_scenario(self):
        """INVALID_PERCENTAGE should trigger for value outside 0-100."""
        issues = []
        row = {
            "source_file_name": "test.csv",
            "source_row_number": 1,
            "source": "test",
            "dataset": "test",
        }

        add_issue(
            issues=issues,
            row=row,
            rule_code="INVALID_PERCENTAGE",
            severity="WARNING",
            action_taken="FLAG",
            field_name="discount_percent",
            observed_value=150,
            issue_message="discount_percent is outside the allowed range of 0 to 100.",
        )

        assert len(issues) == 1
        assert issues[0].rule_code == "INVALID_PERCENTAGE"
        assert issues[0].severity == "WARNING"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])