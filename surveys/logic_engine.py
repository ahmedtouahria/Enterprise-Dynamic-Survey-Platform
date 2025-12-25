"""
Conditional Logic Engine for Dynamic Surveys

A safe, extensible rule evaluation system that supports:
- AND / OR / NOT logic operators
- Multiple comparison operators (=, !=, >, <, in, contains, etc.)
- Cross-section field evaluation
- Real-time evaluation during survey submission
- No arbitrary code execution (secure by design)
"""

from typing import Any, Dict, List, Optional, Union
from decimal import Decimal
from datetime import datetime, date, time
import operator
import re


class LogicEvaluationError(Exception):
    """Raised when logic evaluation fails"""
    pass


class InvalidLogicError(Exception):
    """Raised when logic structure is invalid"""
    pass


class LogicEngine:
    """
    Evaluates conditional logic rules for survey fields.
    
    Supports complex nested logic with AND/OR/NOT operators and various
    comparison operators. Designed to be extended without schema changes.
    """
    
    # Whitelisted comparison operators (security: prevent arbitrary execution)
    COMPARISON_OPERATORS = {
        'equals': lambda a, b: a == b,
        'not_equals': lambda a, b: a != b,
        'greater_than': lambda a, b: a > b if a is not None and b is not None else False,
        'less_than': lambda a, b: a < b if a is not None and b is not None else False,
        'greater_than_or_equal': lambda a, b: a >= b if a is not None and b is not None else False,
        'less_than_or_equal': lambda a, b: a <= b if a is not None and b is not None else False,
        'contains': lambda a, b: b in str(a) if a is not None else False,
        'not_contains': lambda a, b: b not in str(a) if a is not None else False,
        'starts_with': lambda a, b: str(a).startswith(str(b)) if a is not None else False,
        'ends_with': lambda a, b: str(a).endswith(str(b)) if a is not None else False,
        'in': lambda a, b: a in b if isinstance(b, (list, tuple, set)) else False,
        'not_in': lambda a, b: a not in b if isinstance(b, (list, tuple, set)) else False,
        'is_empty': lambda a, b: a is None or a == '' or (isinstance(a, (list, dict)) and len(a) == 0),
        'is_not_empty': lambda a, b: a is not None and a != '' and (not isinstance(a, (list, dict)) or len(a) > 0),
        'matches_regex': lambda a, b: bool(re.match(str(b), str(a))) if a is not None else False,
        'between': lambda a, b: b[0] <= a <= b[1] if isinstance(b, (list, tuple)) and len(b) == 2 else False,
    }
    
    # Logical operators
    LOGICAL_OPERATORS = {'AND', 'OR', 'NOT'}
    
    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        """
        Initialize the logic engine with response data.
        
        Args:
            responses: Dictionary mapping field_id to field_value
                      Example: {'field_123': 'Yes', 'field_456': 25}
        """
        self.responses = responses or {}
        self._field_cache = {}
    
    def evaluate(self, logic_rule: Dict[str, Any]) -> bool:
        """
        Evaluate a logic rule against the current responses.
        
        Args:
            logic_rule: Logic rule in JSON format
            
        Returns:
            Boolean result of the evaluation
            
        Raises:
            InvalidLogicError: If rule structure is invalid
            LogicEvaluationError: If evaluation fails
            
        Example:
            rule = {
                "operator": "AND",
                "conditions": [
                    {
                        "field": "field_123",
                        "comparison": "equals",
                        "value": "Yes"
                    },
                    {
                        "field": "field_456",
                        "comparison": "greater_than",
                        "value": 18
                    }
                ]
            }
            result = engine.evaluate(rule)
        """
        try:
            return self._evaluate_node(logic_rule)
        except Exception as e:
            raise LogicEvaluationError(f"Failed to evaluate logic: {str(e)}") from e
    
    def _evaluate_node(self, node: Dict[str, Any]) -> bool:
        """
        Recursively evaluate a logic node.
        
        A node can be:
        1. A logical operator node (AND/OR/NOT) with nested conditions
        2. A comparison node with field, comparison, and value
        """
        if not isinstance(node, dict):
            raise InvalidLogicError(f"Logic node must be a dictionary, got {type(node)}")
        
        # Check if this is a logical operator node
        operator_key = node.get('operator', '').upper()
        
        if operator_key in self.LOGICAL_OPERATORS:
            return self._evaluate_logical_operator(operator_key, node)
        
        # Otherwise, it's a comparison node
        return self._evaluate_comparison(node)
    
    def _evaluate_logical_operator(self, operator: str, node: Dict[str, Any]) -> bool:
        """Evaluate AND/OR/NOT logical operators."""
        conditions = node.get('conditions', [])
        
        if not isinstance(conditions, list):
            raise InvalidLogicError(f"'conditions' must be a list for {operator} operator")
        
        if operator == 'AND':
            # All conditions must be true
            if not conditions:
                return True  # Empty AND is true
            return all(self._evaluate_node(cond) for cond in conditions)
        
        elif operator == 'OR':
            # At least one condition must be true
            if not conditions:
                return False  # Empty OR is false
            return any(self._evaluate_node(cond) for cond in conditions)
        
        elif operator == 'NOT':
            # Negate the result
            if len(conditions) != 1:
                raise InvalidLogicError(f"NOT operator requires exactly one condition, got {len(conditions)}")
            return not self._evaluate_node(conditions[0])
        
        raise InvalidLogicError(f"Unknown logical operator: {operator}")
    
    def _evaluate_comparison(self, node: Dict[str, Any]) -> bool:
        """Evaluate a comparison node."""
        # Extract comparison components
        field_ref = node.get('field')
        comparison = node.get('comparison', 'equals')
        expected_value = node.get('value')
        
        if field_ref is None:
            raise InvalidLogicError("Comparison node must have 'field' property")
        
        if comparison not in self.COMPARISON_OPERATORS:
            raise InvalidLogicError(
                f"Unknown comparison operator: {comparison}. "
                f"Valid operators: {', '.join(self.COMPARISON_OPERATORS.keys())}"
            )
        
        # Get actual value from responses
        actual_value = self._get_field_value(field_ref)
        
        # Normalize values for comparison
        actual_value = self._normalize_value(actual_value)
        expected_value = self._normalize_value(expected_value)
        
        # Execute comparison
        comparison_func = self.COMPARISON_OPERATORS[comparison]
        
        try:
            return comparison_func(actual_value, expected_value)
        except Exception as e:
            # Log but don't fail - return False for failed comparisons
            return False
    
    def _get_field_value(self, field_ref: Union[str, int]) -> Any:
        """
        Get field value from responses.
        
        Supports both field IDs and field keys.
        """
        # Convert field_ref to string for consistent lookup
        field_key = str(field_ref)
        
        # Check cache first
        if field_key in self._field_cache:
            return self._field_cache[field_key]
        
        # Get value from responses
        value = self.responses.get(field_key)
        
        # Cache the value
        self._field_cache[field_key] = value
        
        return value
    
    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize values for consistent comparison.
        
        Handles type coercion and edge cases.
        """
        # Handle None
        if value is None:
            return None
        
        # Handle strings
        if isinstance(value, str):
            # Try to convert to number if it looks like one
            if value.isdigit():
                return int(value)
            try:
                return float(value)
            except ValueError:
                pass
            
            # Convert string booleans
            if value.lower() in ('true', 'yes', 'on'):
                return True
            if value.lower() in ('false', 'no', 'off'):
                return False
            
            return value
        
        # Handle Decimal
        if isinstance(value, Decimal):
            return float(value)
        
        # Handle datetime objects
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        
        # Return as-is for other types
        return value
    
    def validate_logic(self, logic_rule: Dict[str, Any]) -> List[str]:
        """
        Validate logic rule structure without evaluating it.
        
        Args:
            logic_rule: Logic rule to validate
            
        Returns:
            List of validation error messages (empty if valid)
            
        Example:
            errors = engine.validate_logic(rule)
            if errors:
                print(f"Invalid rule: {errors}")
        """
        errors = []
        
        try:
            self._validate_node(logic_rule, errors)
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return errors
    
    def _validate_node(self, node: Dict[str, Any], errors: List[str], path: str = 'root') -> None:
        """Recursively validate a logic node."""
        if not isinstance(node, dict):
            errors.append(f"{path}: Node must be a dictionary")
            return
        
        operator_key = node.get('operator', '').upper()
        
        if operator_key in self.LOGICAL_OPERATORS:
            # Validate logical operator node
            if 'conditions' not in node:
                errors.append(f"{path}: Logical operator node must have 'conditions'")
                return
            
            conditions = node.get('conditions', [])
            if not isinstance(conditions, list):
                errors.append(f"{path}: 'conditions' must be a list")
                return
            
            if operator_key == 'NOT' and len(conditions) != 1:
                errors.append(f"{path}: NOT operator requires exactly one condition")
            
            # Recursively validate child conditions
            for i, cond in enumerate(conditions):
                self._validate_node(cond, errors, f"{path}.conditions[{i}]")
        
        else:
            # Validate comparison node
            if 'field' not in node:
                errors.append(f"{path}: Comparison node must have 'field'")
            
            comparison = node.get('comparison', 'equals')
            if comparison not in self.COMPARISON_OPERATORS:
                errors.append(
                    f"{path}: Unknown comparison operator '{comparison}'. "
                    f"Valid: {', '.join(self.COMPARISON_OPERATORS.keys())}"
                )
            
            # 'value' is optional for some operators like is_empty
            if comparison not in ('is_empty', 'is_not_empty') and 'value' not in node:
                errors.append(f"{path}: Comparison node should have 'value' for operator '{comparison}'")
    
    def explain_evaluation(self, logic_rule: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate logic and return detailed explanation of each step.
        
        Useful for debugging and showing users why a field is shown/hidden.
        
        Args:
            logic_rule: Logic rule to evaluate
            
        Returns:
            Dictionary with result and explanation tree
            
        Example:
            explanation = engine.explain_evaluation(rule)
            print(f"Result: {explanation['result']}")
            print(f"Explanation: {explanation['explanation']}")
        """
        result = self.evaluate(logic_rule)
        explanation = self._explain_node(logic_rule)
        
        return {
            'result': result,
            'explanation': explanation
        }
    
    def _explain_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Generate explanation for a node."""
        operator_key = node.get('operator', '').upper()
        
        if operator_key in self.LOGICAL_OPERATORS:
            conditions = node.get('conditions', [])
            condition_results = [self._explain_node(cond) for cond in conditions]
            
            if operator_key == 'AND':
                result = all(c['result'] for c in condition_results)
            elif operator_key == 'OR':
                result = any(c['result'] for c in condition_results)
            else:  # NOT
                result = not condition_results[0]['result'] if condition_results else True
            
            return {
                'type': 'logical',
                'operator': operator_key,
                'result': result,
                'conditions': condition_results
            }
        
        else:
            # Comparison node
            field_ref = node.get('field')
            comparison = node.get('comparison', 'equals')
            expected_value = node.get('value')
            actual_value = self._get_field_value(field_ref)
            
            result = self._evaluate_comparison(node)
            
            return {
                'type': 'comparison',
                'field': field_ref,
                'comparison': comparison,
                'actual_value': actual_value,
                'expected_value': expected_value,
                'result': result
            }


class LogicBuilder:
    """
    Helper class to build logic rules programmatically.
    
    Provides a fluent API for creating complex logic rules.
    """
    
    @staticmethod
    def field(field_id: Union[str, int]) -> 'FieldConditionBuilder':
        """Start building a field condition."""
        return FieldConditionBuilder(field_id)
    
    @staticmethod
    def AND(*conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Create an AND condition."""
        return {
            'operator': 'AND',
            'conditions': list(conditions)
        }
    
    @staticmethod
    def OR(*conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Create an OR condition."""
        return {
            'operator': 'OR',
            'conditions': list(conditions)
        }
    
    @staticmethod
    def NOT(condition: Dict[str, Any]) -> Dict[str, Any]:
        """Create a NOT condition."""
        return {
            'operator': 'NOT',
            'conditions': [condition]
        }


class FieldConditionBuilder:
    """Builder for field conditions."""
    
    def __init__(self, field_id: Union[str, int]):
        self.field_id = field_id
    
    def equals(self, value: Any) -> Dict[str, Any]:
        """Field equals value."""
        return {
            'field': self.field_id,
            'comparison': 'equals',
            'value': value
        }
    
    def not_equals(self, value: Any) -> Dict[str, Any]:
        """Field does not equal value."""
        return {
            'field': self.field_id,
            'comparison': 'not_equals',
            'value': value
        }
    
    def greater_than(self, value: Any) -> Dict[str, Any]:
        """Field is greater than value."""
        return {
            'field': self.field_id,
            'comparison': 'greater_than',
            'value': value
        }
    
    def less_than(self, value: Any) -> Dict[str, Any]:
        """Field is less than value."""
        return {
            'field': self.field_id,
            'comparison': 'less_than',
            'value': value
        }
    
    def contains(self, value: Any) -> Dict[str, Any]:
        """Field contains value."""
        return {
            'field': self.field_id,
            'comparison': 'contains',
            'value': value
        }
    
    def is_empty(self) -> Dict[str, Any]:
        """Field is empty."""
        return {
            'field': self.field_id,
            'comparison': 'is_empty',
            'value': None
        }
    
    def is_not_empty(self) -> Dict[str, Any]:
        """Field is not empty."""
        return {
            'field': self.field_id,
            'comparison': 'is_not_empty',
            'value': None
        }
    
    def in_list(self, values: List[Any]) -> Dict[str, Any]:
        """Field value is in list."""
        return {
            'field': self.field_id,
            'comparison': 'in',
            'value': values
        }
    
    def between(self, min_value: Any, max_value: Any) -> Dict[str, Any]:
        """Field value is between min and max."""
        return {
            'field': self.field_id,
            'comparison': 'between',
            'value': [min_value, max_value]
        }
