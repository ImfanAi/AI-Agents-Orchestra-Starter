"""
Enhanced validation utilities for Wand Orchestrator.

Provides comprehensive validation for requests, responses, and data
with detailed error messages and type checking.
"""

import re
from typing import Any, Dict, List, Optional, Union, Callable, Type
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

from app.core.exceptions import ValidationError, ErrorDetail


class ValidationRule:
    """Base class for custom validation rules."""
    
    def __init__(self, message: str):
        self.message = message
    
    def validate(self, value: Any, field_name: str) -> bool:
        """Validate the value. Return True if valid, False otherwise."""
        raise NotImplementedError
    
    def get_error_detail(self, field_name: str, value: Any) -> ErrorDetail:
        """Get error detail for validation failure."""
        return ErrorDetail(
            type="validation_rule_failed",
            message=self.message.format(field=field_name, value=value),
            field=field_name,
            context={"value": value, "rule": self.__class__.__name__}
        )


class LengthRule(ValidationRule):
    """Validate string/list length."""
    
    def __init__(self, min_length: Optional[int] = None, max_length: Optional[int] = None):
        self.min_length = min_length
        self.max_length = max_length
        
        parts = []
        if min_length is not None:
            parts.append(f"at least {min_length}")
        if max_length is not None:
            parts.append(f"at most {max_length}")
        
        message = f"{{field}} must be {' and '.join(parts)} characters/items long"
        super().__init__(message)
    
    def validate(self, value: Any, field_name: str) -> bool:
        if value is None:
            return True
            
        length = len(value) if hasattr(value, '__len__') else 0
        
        if self.min_length is not None and length < self.min_length:
            return False
        if self.max_length is not None and length > self.max_length:
            return False
            
        return True


class RegexRule(ValidationRule):
    """Validate string against regex pattern."""
    
    def __init__(self, pattern: str, message: str = "{field} format is invalid"):
        self.pattern = re.compile(pattern)
        super().__init__(message)
    
    def validate(self, value: Any, field_name: str) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        return bool(self.pattern.match(value))


class RangeRule(ValidationRule):
    """Validate numeric range."""
    
    def __init__(self, min_value: Optional[Union[int, float]] = None, max_value: Optional[Union[int, float]] = None):
        self.min_value = min_value
        self.max_value = max_value
        
        parts = []
        if min_value is not None:
            parts.append(f"at least {min_value}")
        if max_value is not None:
            parts.append(f"at most {max_value}")
        
        message = f"{{field}} must be {' and '.join(parts)}"
        super().__init__(message)
    
    def validate(self, value: Any, field_name: str) -> bool:
        if value is None:
            return True
        if not isinstance(value, (int, float)):
            return False
            
        if self.min_value is not None and value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False
            
        return True


class ChoicesRule(ValidationRule):
    """Validate value is in allowed choices."""
    
    def __init__(self, choices: List[Any]):
        self.choices = choices
        super().__init__(f"{{field}} must be one of: {', '.join(map(str, choices))}")
    
    def validate(self, value: Any, field_name: str) -> bool:
        return value in self.choices


class CustomRule(ValidationRule):
    """Custom validation rule with function."""
    
    def __init__(self, validator_func: Callable[[Any], bool], message: str):
        self.validator_func = validator_func
        super().__init__(message)
    
    def validate(self, value: Any, field_name: str) -> bool:
        try:
            return self.validator_func(value)
        except Exception:
            return False


class EnhancedValidator:
    """Enhanced validator with multiple validation rules."""
    
    def __init__(self):
        self.rules: Dict[str, List[ValidationRule]] = {}
    
    def add_rule(self, field_name: str, rule: ValidationRule) -> 'EnhancedValidator':
        """Add validation rule for a field."""
        if field_name not in self.rules:
            self.rules[field_name] = []
        self.rules[field_name].append(rule)
        return self
    
    def add_length_rule(self, field_name: str, min_length: Optional[int] = None, max_length: Optional[int] = None) -> 'EnhancedValidator':
        """Add length validation rule."""
        return self.add_rule(field_name, LengthRule(min_length, max_length))
    
    def add_regex_rule(self, field_name: str, pattern: str, message: str = None) -> 'EnhancedValidator':
        """Add regex validation rule."""
        rule_message = message or f"{field_name} format is invalid"
        return self.add_rule(field_name, RegexRule(pattern, rule_message))
    
    def add_range_rule(self, field_name: str, min_value: Optional[Union[int, float]] = None, max_value: Optional[Union[int, float]] = None) -> 'EnhancedValidator':
        """Add range validation rule."""
        return self.add_rule(field_name, RangeRule(min_value, max_value))
    
    def add_choices_rule(self, field_name: str, choices: List[Any]) -> 'EnhancedValidator':
        """Add choices validation rule."""
        return self.add_rule(field_name, ChoicesRule(choices))
    
    def add_custom_rule(self, field_name: str, validator_func: Callable[[Any], bool], message: str) -> 'EnhancedValidator':
        """Add custom validation rule."""
        return self.add_rule(field_name, CustomRule(validator_func, message))
    
    def validate(self, data: Dict[str, Any], raise_on_error: bool = True) -> List[ErrorDetail]:
        """Validate data against all rules."""
        errors = []
        
        for field_name, rules in self.rules.items():
            value = data.get(field_name)
            
            for rule in rules:
                if not rule.validate(value, field_name):
                    errors.append(rule.get_error_detail(field_name, value))
        
        if raise_on_error and errors:
            raise ValidationError(
                message=f"Validation failed for {len(errors)} field(s)",
                details=errors
            )
        
        return errors


# Predefined validators for common use cases
class NodeIdValidator(EnhancedValidator):
    """Validator for node IDs."""
    
    def __init__(self):
        super().__init__()
        self.add_length_rule("id", min_length=1, max_length=100)
        self.add_regex_rule("id", r"^[a-zA-Z][a-zA-Z0-9_-]*$", "Node ID must start with letter and contain only letters, numbers, underscores, and hyphens")


class GraphNameValidator(EnhancedValidator):
    """Validator for graph names."""
    
    def __init__(self):
        super().__init__()
        self.add_length_rule("name", min_length=1, max_length=200)
        self.add_regex_rule("name", r"^[^\x00-\x1f\x7f-\x9f]*$", "Graph name contains invalid characters")


class UrlValidator(EnhancedValidator):
    """Validator for URLs."""
    
    def __init__(self):
        super().__init__()
        self.add_regex_rule("url", 
            r"^https?://(?:[-\w.])+(?::[0-9]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?$",
            "Invalid URL format"
        )


class TimeoutValidator(EnhancedValidator):
    """Validator for timeout values."""
    
    def __init__(self):
        super().__init__()
        self.add_range_rule("timeout_sec", min_value=1, max_value=3600)


class ConcurrencyValidator(EnhancedValidator):
    """Validator for concurrency values."""
    
    def __init__(self):
        super().__init__()
        self.add_range_rule("concurrency", min_value=1, max_value=100)


# Validation utilities
def validate_node_spec(node_data: Dict[str, Any]) -> None:
    """Validate node specification."""
    validator = NodeIdValidator()
    validator.add_choices_rule("type", ["agent.fetch", "agent.analyze", "agent.chart"])
    validator.validate(node_data)


def validate_edge_spec(edge_data: Dict[str, Any]) -> None:
    """Validate edge specification."""
    validator = EnhancedValidator()
    validator.add_length_rule("from", min_length=1, max_length=100)
    validator.add_length_rule("to", min_length=1, max_length=100)
    validator.validate(edge_data)


def validate_graph_options(options: Dict[str, Any]) -> None:
    """Validate graph execution options."""
    validator = EnhancedValidator()
    
    if "default_timeout_sec" in options:
        validator.add_range_rule("default_timeout_sec", min_value=1, max_value=3600)
    
    if "max_retries" in options:
        validator.add_range_rule("max_retries", min_value=0, max_value=10)
    
    if "concurrency" in options:
        validator.add_range_rule("concurrency", min_value=1, max_value=100)
    
    validator.validate(options)


def validate_api_key(api_key: str) -> None:
    """Validate API key format."""
    validator = EnhancedValidator()
    validator.add_length_rule("api_key", min_length=16, max_length=512)
    validator.add_regex_rule("api_key", r"^[a-zA-Z0-9\-_=+/]+$", "API key contains invalid characters")
    validator.validate({"api_key": api_key})


def validate_run_input(input_data: Optional[Dict[str, Any]]) -> None:
    """Validate run input data."""
    if input_data is None:
        return
    
    validator = EnhancedValidator()
    
    # Add custom validation for input data structure
    def validate_serializable(value):
        """Check if value is JSON serializable."""
        try:
            import json
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False
    
    for key in input_data.keys():
        validator.add_custom_rule(key, validate_serializable, f"{key} must be JSON serializable")
    
    validator.validate(input_data)


# Enhanced request validation models
class ValidatedGraphRequest(BaseModel):
    """Enhanced graph creation request with validation."""
    
    name: str = Field(..., min_length=1, max_length=200, description="Graph name")
    nodes: List[Dict[str, Any]] = Field(..., min_items=1, max_items=100, description="Graph nodes")
    edges: List[Dict[str, Any]] = Field(default_factory=list, max_items=1000, description="Graph edges")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Execution options")
    sinks: List[str] = Field(default_factory=list, max_items=50, description="Output sink nodes")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate graph name."""
        if re.search(r'[\x00-\x1f\x7f-\x9f]', v):
            raise ValueError("Graph name contains invalid characters")
        return v
    
    @field_validator('nodes')
    @classmethod
    def validate_nodes(cls, v):
        """Validate node specifications."""
        node_ids = set()
        for i, node in enumerate(v):
            try:
                validate_node_spec(node)
            except ValidationError as e:
                raise ValueError(f"Node {i}: {e.message}")
            
            node_id = node.get('id')
            if node_id in node_ids:
                raise ValueError(f"Duplicate node ID: {node_id}")
            node_ids.add(node_id)
        
        return v
    
    @field_validator('edges')
    @classmethod
    def validate_edges(cls, v):
        """Validate edge specifications."""
        for i, edge in enumerate(v):
            try:
                validate_edge_spec(edge)
            except ValidationError as e:
                raise ValueError(f"Edge {i}: {e.message}")
        return v
    
    @field_validator('options')
    @classmethod
    def validate_options(cls, v):
        """Validate execution options."""
        if v:
            try:
                validate_graph_options(v)
            except ValidationError as e:
                raise ValueError(f"Options validation: {e.message}")
        return v
    
    @model_validator(mode='after')
    def validate_graph_structure(self):
        """Validate overall graph structure."""
        nodes = self.nodes or []
        edges = self.edges or []
        sinks = self.sinks or []
        
        if not nodes:
            raise ValueError("Graph must have at least one node")
        
        node_ids = {node.id for node in nodes}
        
        # Validate edge references
        for edge in edges:
            if edge.from_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.from_id}")
            if edge.to_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.to_id}")
        
        # Validate sink references
        for sink in sinks:
            if sink not in node_ids:
                raise ValueError(f"Sink references unknown node: {sink}")
        
        return self


class ValidatedRunRequest(BaseModel):
    """Enhanced run creation request with validation."""
    
    graph_id: str = Field(..., min_length=1, max_length=100, description="Graph ID")
    input: Optional[Dict[str, Any]] = Field(default=None, description="Input data")
    
    @field_validator('graph_id')
    @classmethod
    def validate_graph_id(cls, v):
        """Validate graph ID format."""
        if not re.match(r"^g_[a-f0-9]{8}$", v):
            raise ValueError("Invalid graph ID format")
        return v
    
    @field_validator('input')
    @classmethod
    def validate_input(cls, v):
        """Validate input data."""
        if v is not None:
            try:
                validate_run_input(v)
            except ValidationError as e:
                raise ValueError(f"Input validation: {e.message}")
        return v


# Export main components
__all__ = [
    # Validation rules
    "ValidationRule",
    "LengthRule",
    "RegexRule", 
    "RangeRule",
    "ChoicesRule",
    "CustomRule",
    
    # Validators
    "EnhancedValidator",
    "NodeIdValidator",
    "GraphNameValidator",
    "UrlValidator",
    "TimeoutValidator",
    "ConcurrencyValidator",
    
    # Validation utilities
    "validate_node_spec",
    "validate_edge_spec", 
    "validate_graph_options",
    "validate_api_key",
    "validate_run_input",
    
    # Enhanced models
    "ValidatedGraphRequest",
    "ValidatedRunRequest"
]