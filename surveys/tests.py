"""
Unit Tests for Conditional Logic Engine

Tests all operators, edge cases, and security considerations.
"""

import pytest
from surveys.logic_engine import (
    LogicEngine,
    LogicBuilder,
    LogicEvaluationError,
    InvalidLogicError
)


class TestLogicEngine:
    """Test cases for the LogicEngine class."""
    
    # ========================================================================
    # Comparison Operators Tests
    # ========================================================================
    
    def test_equals_operator(self):
        """Test equals comparison."""
        rule = {"field": "name", "comparison": "equals", "value": "John"}
        
        engine = LogicEngine({"name": "John"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"name": "Jane"})
        assert engine.evaluate(rule) is False
    
    def test_not_equals_operator(self):
        """Test not_equals comparison."""
        rule = {"field": "status", "comparison": "not_equals", "value": "completed"}
        
        engine = LogicEngine({"status": "pending"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"status": "completed"})
        assert engine.evaluate(rule) is False
    
    def test_greater_than_operator(self):
        """Test greater_than comparison."""
        rule = {"field": "age", "comparison": "greater_than", "value": 18}
        
        engine = LogicEngine({"age": 25})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"age": 15})
        assert engine.evaluate(rule) is False
        
        engine = LogicEngine({"age": 18})
        assert engine.evaluate(rule) is False  # Not strictly greater
    
    def test_less_than_operator(self):
        """Test less_than comparison."""
        rule = {"field": "score", "comparison": "less_than", "value": 100}
        
        engine = LogicEngine({"score": 50})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"score": 150})
        assert engine.evaluate(rule) is False
    
    def test_contains_operator(self):
        """Test contains comparison for strings."""
        rule = {"field": "comment", "comparison": "contains", "value": "great"}
        
        engine = LogicEngine({"comment": "This is great!"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"comment": "This is okay"})
        assert engine.evaluate(rule) is False
    
    def test_in_operator(self):
        """Test in comparison for lists."""
        rule = {"field": "role", "comparison": "in", "value": ["admin", "moderator"]}
        
        engine = LogicEngine({"role": "admin"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"role": "user"})
        assert engine.evaluate(rule) is False
    
    def test_is_empty_operator(self):
        """Test is_empty comparison."""
        rule = {"field": "optional_field", "comparison": "is_empty"}
        
        engine = LogicEngine({"optional_field": None})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"optional_field": ""})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"optional_field": []})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"optional_field": "value"})
        assert engine.evaluate(rule) is False
    
    def test_is_not_empty_operator(self):
        """Test is_not_empty comparison."""
        rule = {"field": "required_field", "comparison": "is_not_empty"}
        
        engine = LogicEngine({"required_field": "value"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"required_field": None})
        assert engine.evaluate(rule) is False
        
        engine = LogicEngine({"required_field": ""})
        assert engine.evaluate(rule) is False
    
    def test_between_operator(self):
        """Test between comparison."""
        rule = {"field": "age", "comparison": "between", "value": [18, 65]}
        
        engine = LogicEngine({"age": 30})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"age": 18})
        assert engine.evaluate(rule) is True  # Inclusive
        
        engine = LogicEngine({"age": 65})
        assert engine.evaluate(rule) is True  # Inclusive
        
        engine = LogicEngine({"age": 10})
        assert engine.evaluate(rule) is False
    
    # ========================================================================
    # Logical Operators Tests
    # ========================================================================
    
    def test_and_operator(self):
        """Test AND logical operator."""
        rule = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "comparison": "greater_than", "value": 18},
                {"field": "country", "comparison": "equals", "value": "US"}
            ]
        }
        
        engine = LogicEngine({"age": 25, "country": "US"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"age": 15, "country": "US"})
        assert engine.evaluate(rule) is False
        
        engine = LogicEngine({"age": 25, "country": "UK"})
        assert engine.evaluate(rule) is False
    
    def test_or_operator(self):
        """Test OR logical operator."""
        rule = {
            "operator": "OR",
            "conditions": [
                {"field": "email", "comparison": "is_not_empty"},
                {"field": "phone", "comparison": "is_not_empty"}
            ]
        }
        
        engine = LogicEngine({"email": "user@example.com", "phone": ""})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"email": "", "phone": "123-456-7890"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"email": "", "phone": ""})
        assert engine.evaluate(rule) is False
    
    def test_not_operator(self):
        """Test NOT logical operator."""
        rule = {
            "operator": "NOT",
            "conditions": [
                {"field": "status", "comparison": "equals", "value": "completed"}
            ]
        }
        
        engine = LogicEngine({"status": "pending"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"status": "completed"})
        assert engine.evaluate(rule) is False
    
    def test_nested_logic(self):
        """Test complex nested logic."""
        # (age >= 18 AND country = "US") OR (age >= 21 AND country = "UK")
        rule = {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "age", "comparison": "greater_than_or_equal", "value": 18},
                        {"field": "country", "comparison": "equals", "value": "US"}
                    ]
                },
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "age", "comparison": "greater_than_or_equal", "value": 21},
                        {"field": "country", "comparison": "equals", "value": "UK"}
                    ]
                }
            ]
        }
        
        engine = LogicEngine({"age": 19, "country": "US"})
        assert engine.evaluate(rule) is True
        
        engine = LogicEngine({"age": 19, "country": "UK"})
        assert engine.evaluate(rule) is False
        
        engine = LogicEngine({"age": 22, "country": "UK"})
        assert engine.evaluate(rule) is True
    
    # ========================================================================
    # Edge Cases Tests
    # ========================================================================
    
    def test_missing_field(self):
        """Test evaluation with missing field."""
        rule = {"field": "nonexistent", "comparison": "equals", "value": "test"}
        
        engine = LogicEngine({})
        assert engine.evaluate(rule) is False  # Should not raise exception
    
    def test_none_values(self):
        """Test comparison with None values."""
        rule = {"field": "optional", "comparison": "equals", "value": None}
        
        engine = LogicEngine({"optional": None})
        assert engine.evaluate(rule) is True
    
    def test_type_coercion(self):
        """Test automatic type coercion."""
        rule = {"field": "age", "comparison": "greater_than", "value": 18}
        
        # String number should be coerced to int
        engine = LogicEngine({"age": "25"})
        assert engine.evaluate(rule) is True
    
    def test_empty_and_conditions(self):
        """Test AND with no conditions."""
        rule = {"operator": "AND", "conditions": []}
        
        engine = LogicEngine({})
        assert engine.evaluate(rule) is True  # Empty AND is true
    
    def test_empty_or_conditions(self):
        """Test OR with no conditions."""
        rule = {"operator": "OR", "conditions": []}
        
        engine = LogicEngine({})
        assert engine.evaluate(rule) is False  # Empty OR is false
    
    # ========================================================================
    # Validation Tests
    # ========================================================================
    
    def test_validate_valid_rule(self):
        """Test validation of valid rule."""
        rule = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "comparison": "greater_than", "value": 18}
            ]
        }
        
        engine = LogicEngine()
        errors = engine.validate_logic(rule)
        assert len(errors) == 0
    
    def test_validate_invalid_operator(self):
        """Test validation catches invalid operator."""
        rule = {"field": "age", "comparison": "invalid_op", "value": 18}
        
        engine = LogicEngine()
        errors = engine.validate_logic(rule)
        assert len(errors) > 0
        assert "invalid_op" in errors[0]
    
    def test_validate_missing_field(self):
        """Test validation catches missing field."""
        rule = {"comparison": "equals", "value": "test"}
        
        engine = LogicEngine()
        errors = engine.validate_logic(rule)
        assert len(errors) > 0
        assert "field" in errors[0].lower()
    
    def test_validate_not_with_multiple_conditions(self):
        """Test validation catches NOT with multiple conditions."""
        rule = {
            "operator": "NOT",
            "conditions": [
                {"field": "a", "comparison": "equals", "value": 1},
                {"field": "b", "comparison": "equals", "value": 2}
            ]
        }
        
        engine = LogicEngine()
        errors = engine.validate_logic(rule)
        assert len(errors) > 0
        assert "one condition" in errors[0].lower()
    
    # ========================================================================
    # LogicBuilder Tests
    # ========================================================================
    
    def test_logic_builder_and(self):
        """Test LogicBuilder AND construction."""
        rule = LogicBuilder.AND(
            LogicBuilder.field("age").greater_than(18),
            LogicBuilder.field("country").equals("US")
        )
        
        engine = LogicEngine({"age": 25, "country": "US"})
        assert engine.evaluate(rule) is True
    
    def test_logic_builder_or(self):
        """Test LogicBuilder OR construction."""
        rule = LogicBuilder.OR(
            LogicBuilder.field("email").is_not_empty(),
            LogicBuilder.field("phone").is_not_empty()
        )
        
        engine = LogicEngine({"email": "test@example.com", "phone": ""})
        assert engine.evaluate(rule) is True
    
    def test_logic_builder_not(self):
        """Test LogicBuilder NOT construction."""
        rule = LogicBuilder.NOT(
            LogicBuilder.field("status").equals("completed")
        )
        
        engine = LogicEngine({"status": "pending"})
        assert engine.evaluate(rule) is True
    
    def test_logic_builder_complex(self):
        """Test LogicBuilder complex nested logic."""
        rule = LogicBuilder.AND(
            LogicBuilder.field("age").between(18, 65),
            LogicBuilder.OR(
                LogicBuilder.field("country").equals("US"),
                LogicBuilder.field("country").equals("CA")
            )
        )
        
        engine = LogicEngine({"age": 30, "country": "US"})
        assert engine.evaluate(rule) is True
    
    # ========================================================================
    # Explanation Tests
    # ========================================================================
    
    def test_explanation(self):
        """Test explanation generation."""
        rule = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "comparison": "greater_than", "value": 18},
                {"field": "country", "comparison": "equals", "value": "US"}
            ]
        }
        
        engine = LogicEngine({"age": 25, "country": "US"})
        explanation = engine.explain_evaluation(rule)
        
        assert explanation['result'] is True
        assert explanation['explanation']['type'] == 'logical'
        assert explanation['explanation']['operator'] == 'AND'
        assert len(explanation['explanation']['conditions']) == 2
    
    # ========================================================================
    # Security Tests
    # ========================================================================
    
    def test_no_code_injection(self):
        """Test that malicious code cannot be executed."""
        # Try to inject code through comparison value
        rule = {
            "field": "test",
            "comparison": "equals",
            "value": "__import__('os').system('echo hacked')"
        }
        
        engine = LogicEngine({"test": "safe_value"})
        # Should safely compare strings, not execute code
        result = engine.evaluate(rule)
        assert result is False
    
    def test_unknown_operator_rejected(self):
        """Test that unknown operators are rejected."""
        rule = {"field": "test", "comparison": "eval", "value": "malicious_code"}
        
        engine = LogicEngine({"test": "value"})
        
        with pytest.raises(InvalidLogicError):
            engine.evaluate(rule)
    
    # ========================================================================
    # Performance Tests
    # ========================================================================
    
    def test_field_value_caching(self):
        """Test that field values are cached."""
        rule = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "comparison": "greater_than", "value": 18},
                {"field": "age", "comparison": "less_than", "value": 65}
            ]
        }
        
        engine = LogicEngine({"age": 30})
        result = engine.evaluate(rule)
        
        # Field should be accessed only once (cached for second use)
        assert "age" in engine._field_cache
        assert result is True


# ============================================================================
# Run tests with pytest
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
