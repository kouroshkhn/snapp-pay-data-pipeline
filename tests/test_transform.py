"""
Unit tests for transform.py functions.
Tests text cleaning, price parsing, URL normalization, and availability mapping.
"""

import pytest
from decimal import Decimal
import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from transform import (
    clean_text,
    normalize_text,
    parse_decimal,
    parse_price_to_irr,
    parse_percent,
    normalize_url,
    is_valid_http_url,
)


class TestTextCleaning:
    """Test clean_text function."""

    def test_persian_digits_to_ascii(self):
        """Persian digits should convert to ASCII."""
        assert clean_text("۱۵۰۰۰۰۰") == "1500000"
        assert clean_text("۲۵٪") == "25٪"

    def test_arabic_yeh_to_persian(self):
        """Arabic ي should convert to Persian ی."""
        assert clean_text("موبايل") == "موبایل"

    def test_arabic_kaf_to_persian(self):
        """Arabic ك should convert to Persian ک."""
        assert clean_text("كابل") == "کابل"

    def test_whitespace_normalization(self):
        """Multiple spaces should become single space."""
        assert clean_text("گوشی   موبایل") == "گوشی موبایل"
        assert clean_text("  محصول  نمونه  ") == "محصول نمونه"

    def test_null_value(self):
        """None should return None."""
        assert clean_text(None) is None

    def test_empty_string(self):
        """Empty string should return None."""
        assert clean_text("") is None
        assert clean_text("   ") is None


class TestTextNormalization:
    """Test normalize_text function (casefold for matching)."""

    def test_casefold(self):
        """Text should be casefolded."""
        assert normalize_text("SAMSUNG") == "samsung"
        assert normalize_text("Apple") == "apple"

    def test_null_value(self):
        """None should return None."""
        assert normalize_text(None) is None


class TestDecimalParsing:
    """Test parse_decimal function."""

    def test_plain_numeric_string(self):
        """Plain numeric string should parse."""
        assert parse_decimal("1500000") == Decimal("1500000")

    def test_with_comma_separator(self):
        """Comma should be removed."""
        assert parse_decimal("1,500,000") == Decimal("1500000")

    def test_with_persian_digits(self):
        """Persian digits should convert."""
        assert parse_decimal("۱۵۰۰۰۰۰") == Decimal("1500000")

    def test_with_currency_words(self):
        """Currency words should be stripped."""
        assert parse_decimal("1500000ریال") == Decimal("1500000")
        assert parse_decimal("150000تومان") == Decimal("150000")

    def test_null_value(self):
        """None should return None."""
        assert parse_decimal(None) is None

    def test_invalid_string(self):
        """Non-numeric string should return None."""
        assert parse_decimal("ناموجود") is None
        assert parse_decimal("free") is None


class TestPriceParsing:
    """Test parse_price_to_irr function."""

    def test_plain_price(self):
        """Plain price should parse."""
        assert parse_price_to_irr("1500000", 1) == Decimal("1500000")

    def test_with_multiplier(self):
        """Price with multiplier should multiply."""
        assert parse_price_to_irr("150000", 10) == Decimal("1500000")

    def test_null_value(self):
        """None should return None."""
        assert parse_price_to_irr(None, 1) is None

    def test_null_multiplier(self):
        """None multiplier should return None."""
        assert parse_price_to_irr("1500000", None) is None


class TestPercentageParsing:
    """Test parse_percent function."""

    def test_plain_percentage(self):
        """Plain percentage should parse."""
        assert parse_percent("25") == Decimal("25")

    def test_with_percent_sign(self):
        """Percent sign should be stripped."""
        assert parse_percent("25%") == Decimal("25")
        assert parse_percent("٪20") == Decimal("20")

    def test_null_value(self):
        """None should return None."""
        assert parse_percent(None) is None


class TestURLNormalization:
    """Test normalize_url function."""

    def test_valid_url(self):
        """Valid URL should remain unchanged."""
        url = "https://example.com/product/123"
        assert normalize_url(url) == url

    def test_url_with_whitespace(self):
        """URL with whitespace should be trimmed."""
        assert normalize_url("  https://example.com  ") == "https://example.com"

    def test_markdown_link(self):
        """Markdown link should extract URL."""
        result = normalize_url("[مشاهده محصول](https://example.com/p/1)")
        assert result == "https://example.com/p/1"

    def test_null_value(self):
        """None should return None."""
        assert normalize_url(None) is None


class TestURLValidation:
    """Test is_valid_http_url function."""

    def test_valid_http(self):
        """HTTP URL should be valid."""
        assert is_valid_http_url("http://example.com") is True

    def test_valid_https(self):
        """HTTPS URL should be valid."""
        assert is_valid_http_url("https://example.com") is True

    def test_invalid_no_protocol(self):
        """URL without protocol should be invalid."""
        assert is_valid_http_url("example.com") is False

    def test_null_value(self):
        """None should be considered invalid."""
        assert is_valid_http_url(None) is False

    def test_empty_string(self):
        """Empty string should be considered invalid."""
        assert is_valid_http_url("") is False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])