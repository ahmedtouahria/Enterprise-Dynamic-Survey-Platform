"""
Examples and Test Cases for Conditional Logic Engine

Demonstrates various use cases and patterns for the logic engine.
"""

from surveys.logic_engine import LogicEngine, LogicBuilder


# ============================================================================
# EXAMPLE 1: Simple Comparison
# ============================================================================

def example_simple_comparison():
    """Show a field if another field equals a specific value."""
    
    # Rule: Show "reason" field if "satisfied" equals "No"
    rule = {
        "field": "satisfied",
        "comparison": "equals",
        "value": "No"
    }
    
    # Test with different responses
    responses1 = {"satisfied": "No"}
    engine1 = LogicEngine(responses1)
    print(f"Satisfied = 'No': {engine1.evaluate(rule)}")  # True
    
    responses2 = {"satisfied": "Yes"}
    engine2 = LogicEngine(responses2)
    print(f"Satisfied = 'Yes': {engine2.evaluate(rule)}")  # False


# ============================================================================
# EXAMPLE 2: AND Logic
# ============================================================================

def example_and_logic():
    """Show field if multiple conditions are all true."""
    
    # Rule: Show "special_offer" if age >= 18 AND income > 50000
    rule = {
        "operator": "AND",
        "conditions": [
            {
                "field": "age",
                "comparison": "greater_than_or_equal",
                "value": 18
            },
            {
                "field": "income",
                "comparison": "greater_than",
                "value": 50000
            }
        ]
    }
    
    responses = {"age": 25, "income": 60000}
    engine = LogicEngine(responses)
    print(f"Age=25, Income=60000: {engine.evaluate(rule)}")  # True
    
    responses = {"age": 16, "income": 60000}
    engine = LogicEngine(responses)
    print(f"Age=16, Income=60000: {engine.evaluate(rule)}")  # False


# ============================================================================
# EXAMPLE 3: OR Logic
# ============================================================================

def example_or_logic():
    """Show field if at least one condition is true."""
    
    # Rule: Show "contact_method" if email OR phone is provided
    rule = {
        "operator": "OR",
        "conditions": [
            {
                "field": "email",
                "comparison": "is_not_empty",
                "value": None
            },
            {
                "field": "phone",
                "comparison": "is_not_empty",
                "value": None
            }
        ]
    }
    
    responses = {"email": "user@example.com", "phone": ""}
    engine = LogicEngine(responses)
    print(f"Has email: {engine.evaluate(rule)}")  # True
    
    responses = {"email": "", "phone": ""}
    engine = LogicEngine(responses)
    print(f"No contact: {engine.evaluate(rule)}")  # False


# ============================================================================
# EXAMPLE 4: NOT Logic
# ============================================================================

def example_not_logic():
    """Show field if condition is NOT true."""
    
    # Rule: Show "improvement_suggestions" if NOT satisfied
    rule = {
        "operator": "NOT",
        "conditions": [
            {
                "field": "satisfied",
                "comparison": "equals",
                "value": "Yes"
            }
        ]
    }
    
    responses = {"satisfied": "No"}
    engine = LogicEngine(responses)
    print(f"Not satisfied: {engine.evaluate(rule)}")  # True


# ============================================================================
# EXAMPLE 5: Nested Logic (Complex)
# ============================================================================

def example_nested_logic():
    """Complex nested logic with multiple operators."""
    
    # Rule: Show field if:
    # (age >= 18 AND country = "US") OR (age >= 21 AND country = "UK")
    rule = {
        "operator": "OR",
        "conditions": [
            {
                "operator": "AND",
                "conditions": [
                    {
                        "field": "age",
                        "comparison": "greater_than_or_equal",
                        "value": 18
                    },
                    {
                        "field": "country",
                        "comparison": "equals",
                        "value": "US"
                    }
                ]
            },
            {
                "operator": "AND",
                "conditions": [
                    {
                        "field": "age",
                        "comparison": "greater_than_or_equal",
                        "value": 21
                    },
                    {
                        "field": "country",
                        "comparison": "equals",
                        "value": "UK"
                    }
                ]
            }
        ]
    }
    
    # Test case 1: 19 years old in US
    responses = {"age": 19, "country": "US"}
    engine = LogicEngine(responses)
    print(f"Age=19, US: {engine.evaluate(rule)}")  # True
    
    # Test case 2: 19 years old in UK
    responses = {"age": 19, "country": "UK"}
    engine = LogicEngine(responses)
    print(f"Age=19, UK: {engine.evaluate(rule)}")  # False
    
    # Test case 3: 22 years old in UK
    responses = {"age": 22, "country": "UK"}
    engine = LogicEngine(responses)
    print(f"Age=22, UK: {engine.evaluate(rule)}")  # True


# ============================================================================
# EXAMPLE 6: Using LogicBuilder (Fluent API)
# ============================================================================

def example_logic_builder():
    """Build rules using the fluent API."""
    
    # Build rule: age >= 18 AND (country = "US" OR country = "CA")
    rule = LogicBuilder.AND(
        LogicBuilder.field("age").greater_than_or_equal(18),
        LogicBuilder.OR(
            LogicBuilder.field("country").equals("US"),
            LogicBuilder.field("country").equals("CA")
        )
    )
    
    responses = {"age": 20, "country": "US"}
    engine = LogicEngine(responses)
    print(f"Age=20, US: {engine.evaluate(rule)}")  # True
    
    responses = {"age": 20, "country": "UK"}
    engine = LogicEngine(responses)
    print(f"Age=20, UK: {engine.evaluate(rule)}")  # False


# ============================================================================
# EXAMPLE 7: String Comparisons
# ============================================================================

def example_string_comparisons():
    """Various string comparison operators."""
    
    # Contains
    rule1 = {
        "field": "comment",
        "comparison": "contains",
        "value": "excellent"
    }
    
    responses = {"comment": "The service was excellent!"}
    engine = LogicEngine(responses)
    print(f"Contains 'excellent': {engine.evaluate(rule1)}")  # True
    
    # Starts with
    rule2 = {
        "field": "email",
        "comparison": "starts_with",
        "value": "admin"
    }
    
    responses = {"email": "admin@example.com"}
    engine = LogicEngine(responses)
    print(f"Starts with 'admin': {engine.evaluate(rule2)}")  # True
    
    # In list
    rule3 = {
        "field": "role",
        "comparison": "in",
        "value": ["admin", "moderator", "editor"]
    }
    
    responses = {"role": "moderator"}
    engine = LogicEngine(responses)
    print(f"Role in list: {engine.evaluate(rule3)}")  # True


# ============================================================================
# EXAMPLE 8: Numeric Comparisons
# ============================================================================

def example_numeric_comparisons():
    """Numeric range and comparison operators."""
    
    # Between
    rule1 = {
        "field": "age",
        "comparison": "between",
        "value": [18, 65]
    }
    
    responses = {"age": 30}
    engine = LogicEngine(responses)
    print(f"Age between 18-65: {engine.evaluate(rule1)}")  # True
    
    # Greater than
    rule2 = {
        "field": "score",
        "comparison": "greater_than",
        "value": 80
    }
    
    responses = {"score": 95}
    engine = LogicEngine(responses)
    print(f"Score > 80: {engine.evaluate(rule2)}")  # True


# ============================================================================
# EXAMPLE 9: Cross-Section Logic
# ============================================================================

def example_cross_section():
    """Logic that spans multiple survey sections."""
    
    # Rule: Show "shipping_address" section if:
    # - product_type = "Physical" (from section 1)
    # - quantity > 0 (from section 2)
    # - country != "Digital-Only" (from section 3)
    
    rule = {
        "operator": "AND",
        "conditions": [
            {
                "field": "product_type",  # From section 1
                "comparison": "equals",
                "value": "Physical"
            },
            {
                "field": "quantity",  # From section 2
                "comparison": "greater_than",
                "value": 0
            },
            {
                "operator": "NOT",
                "conditions": [
                    {
                        "field": "country",  # From section 3
                        "comparison": "equals",
                        "value": "Digital-Only"
                    }
                ]
            }
        ]
    }
    
    responses = {
        "product_type": "Physical",
        "quantity": 5,
        "country": "US"
    }
    
    engine = LogicEngine(responses)
    print(f"Show shipping: {engine.evaluate(rule)}")  # True


# ============================================================================
# EXAMPLE 10: Real-Time Evaluation During Submission
# ============================================================================

def example_realtime_evaluation():
    """Simulate real-time evaluation as user fills survey."""
    
    rule = {
        "operator": "AND",
        "conditions": [
            {
                "field": "interested",
                "comparison": "equals",
                "value": "Yes"
            },
            {
                "field": "budget",
                "comparison": "greater_than",
                "value": 1000
            }
        ]
    }
    
    # Step 1: User answers first question
    responses = {"interested": "Yes"}
    engine = LogicEngine(responses)
    print(f"After Q1: {engine.evaluate(rule)}")  # False (budget not answered)
    
    # Step 2: User answers second question
    responses = {"interested": "Yes", "budget": 5000}
    engine = LogicEngine(responses)
    print(f"After Q2: {engine.evaluate(rule)}")  # True (both answered)


# ============================================================================
# EXAMPLE 11: Validation
# ============================================================================

def example_validation():
    """Validate logic rules before saving."""
    
    engine = LogicEngine()
    
    # Valid rule
    valid_rule = {
        "operator": "AND",
        "conditions": [
            {
                "field": "age",
                "comparison": "greater_than",
                "value": 18
            }
        ]
    }
    
    errors = engine.validate_logic(valid_rule)
    print(f"Valid rule errors: {errors}")  # []
    
    # Invalid rule (unknown operator)
    invalid_rule = {
        "field": "age",
        "comparison": "unknown_operator",
        "value": 18
    }
    
    errors = engine.validate_logic(invalid_rule)
    print(f"Invalid rule errors: {errors}")  # ['Unknown comparison operator...']


# ============================================================================
# EXAMPLE 12: Explanation (Debugging)
# ============================================================================

def example_explanation():
    """Get detailed explanation of evaluation."""
    
    rule = {
        "operator": "AND",
        "conditions": [
            {
                "field": "age",
                "comparison": "greater_than",
                "value": 18
            },
            {
                "field": "country",
                "comparison": "equals",
                "value": "US"
            }
        ]
    }
    
    responses = {"age": 25, "country": "UK"}
    engine = LogicEngine(responses)
    
    explanation = engine.explain_evaluation(rule)
    print(f"\nResult: {explanation['result']}")
    print(f"Explanation: {explanation['explanation']}")


# ============================================================================
# EXAMPLE 13: Multiple Choice Logic
# ============================================================================

def example_multiple_choice():
    """Logic based on multiple choice selections."""
    
    # Show follow-up if user selected "Other" in interests
    rule = {
        "field": "interests",
        "comparison": "contains",
        "value": "Other"
    }
    
    responses = {"interests": ["Sports", "Music", "Other"]}
    engine = LogicEngine(responses)
    print(f"Contains Other: {engine.evaluate(rule)}")  # True


# ============================================================================
# EXAMPLE 14: Date Comparison
# ============================================================================

def example_date_comparison():
    """Compare dates."""
    
    from datetime import datetime
    
    # Show reminder if event_date is in the future
    rule = {
        "field": "event_date",
        "comparison": "greater_than",
        "value": "2025-12-31"
    }
    
    responses = {"event_date": "2026-01-15"}
    engine = LogicEngine(responses)
    print(f"Future date: {engine.evaluate(rule)}")  # True


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("CONDITIONAL LOGIC ENGINE EXAMPLES")
    print("=" * 80)
    
    print("\n1. Simple Comparison")
    print("-" * 80)
    example_simple_comparison()
    
    print("\n2. AND Logic")
    print("-" * 80)
    example_and_logic()
    
    print("\n3. OR Logic")
    print("-" * 80)
    example_or_logic()
    
    print("\n4. NOT Logic")
    print("-" * 80)
    example_not_logic()
    
    print("\n5. Nested Logic")
    print("-" * 80)
    example_nested_logic()
    
    print("\n6. LogicBuilder (Fluent API)")
    print("-" * 80)
    example_logic_builder()
    
    print("\n7. String Comparisons")
    print("-" * 80)
    example_string_comparisons()
    
    print("\n8. Numeric Comparisons")
    print("-" * 80)
    example_numeric_comparisons()
    
    print("\n9. Cross-Section Logic")
    print("-" * 80)
    example_cross_section()
    
    print("\n10. Real-Time Evaluation")
    print("-" * 80)
    example_realtime_evaluation()
    
    print("\n11. Validation")
    print("-" * 80)
    example_validation()
    
    print("\n12. Explanation")
    print("-" * 80)
    example_explanation()
    
    print("\n13. Multiple Choice Logic")
    print("-" * 80)
    example_multiple_choice()
    
    print("\n14. Date Comparison")
    print("-" * 80)
    example_date_comparison()
