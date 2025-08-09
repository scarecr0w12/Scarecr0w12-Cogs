"""
Model capabilities detection and parameter filtering system.

This module provides automatic detection of AI model types and their supported
parameters to prevent API errors and optimize model usage.
"""
from __future__ import annotations
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import logging

log = logging.getLogger("red.skynetv2.model_capabilities")


class ModelType(Enum):
    """Types of AI models with different capabilities."""
    REASONING = "reasoning"         # o1-series models with internal reasoning (supports temperature=1.0)
    GPT5_REASONING = "gpt5_reasoning"  # GPT-5 reasoning models (no temperature support)
    CHAT = "chat"                   # Standard chat completion models
    INSTRUCT = "instruct"           # Instruction-following models
    CODE = "code"                   # Code-specialized models
    VISION = "vision"               # Vision-capable models
    UNKNOWN = "unknown"             # Unknown or unsupported model type


@dataclass
class ModelCapabilities:
    """Defines what parameters and features a model type supports."""
    model_type: ModelType
    supports_temperature: bool = True
    temperature_range: tuple[float, float] = (0.0, 2.0)
    supports_top_p: bool = True
    top_p_range: tuple[float, float] = (0.0, 1.0)
    supports_frequency_penalty: bool = True
    frequency_penalty_range: tuple[float, float] = (-2.0, 2.0)
    supports_presence_penalty: bool = True
    presence_penalty_range: tuple[float, float] = (-2.0, 2.0)
    supports_max_tokens: bool = True
    supports_streaming: bool = True
    supports_system_messages: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    has_reasoning: bool = False
    
    # Special parameter constraints
    forced_temperature: Optional[float] = None  # Force specific temperature
    unsupported_params: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Apply model-specific constraints after initialization."""
        if self.model_type == ModelType.REASONING:
            # o1-series models have strict constraints but support temperature=1.0
            self.forced_temperature = 1.0
            self.supports_top_p = False
            self.supports_frequency_penalty = False
            self.supports_presence_penalty = False
            self.has_reasoning = True
            self.unsupported_params.update({
                'top_p', 'frequency_penalty', 'presence_penalty'
            })
            # Don't add temperature to unsupported - it's supported but forced
        elif self.model_type == ModelType.GPT5_REASONING:
            # GPT-5 reasoning models don't support temperature AT ALL
            self.supports_temperature = False
            self.supports_top_p = False
            self.supports_frequency_penalty = False
            self.supports_presence_penalty = False
            self.has_reasoning = True
            self.unsupported_params.update({
                'temperature', 'top_p', 'frequency_penalty', 'presence_penalty'
            })


# Model capability definitions
MODEL_CAPABILITIES = {
    ModelType.REASONING: ModelCapabilities(
        model_type=ModelType.REASONING,
        supports_temperature=True,  # Supports temperature but only at 1.0
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        forced_temperature=1.0,
        has_reasoning=True,
    ),
    
    ModelType.GPT5_REASONING: ModelCapabilities(
        model_type=ModelType.GPT5_REASONING,
        supports_temperature=False,  # GPT-5 reasoning models don't support temperature
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        has_reasoning=True,
    ),
    
    ModelType.CHAT: ModelCapabilities(
        model_type=ModelType.CHAT,
        supports_function_calling=True,
    ),
    
    ModelType.INSTRUCT: ModelCapabilities(
        model_type=ModelType.INSTRUCT,
        supports_function_calling=False,
    ),
    
    ModelType.CODE: ModelCapabilities(
        model_type=ModelType.CODE,
        supports_function_calling=True,
        temperature_range=(0.0, 1.0),  # Code models work better with lower temps
    ),
    
    ModelType.VISION: ModelCapabilities(
        model_type=ModelType.VISION,
        supports_vision=True,
        supports_function_calling=True,
    ),
    
    ModelType.UNKNOWN: ModelCapabilities(
        model_type=ModelType.UNKNOWN,
        # Conservative defaults - assume basic chat capabilities only
        supports_function_calling=False,
        supports_vision=False,
    ),
}


def detect_model_type(model_name: str, provider: str = "") -> ModelType:
    """
    Detect the type of model based on its name and provider.
    
    Args:
        model_name: Name of the model (e.g., "gpt-4o", "o1-mini", "gpt-5")
        provider: Provider name (e.g., "openai", "anthropic")
        
    Returns:
        ModelType enum value
    """
    model_lower = model_name.lower()
    provider_lower = provider.lower()
    
    # GPT-5 series models (new reasoning models from OpenAI)
    if model_lower.startswith('gpt-5'):
        if 'chat' in model_lower:
            return ModelType.CHAT  # gpt-5-chat-latest supports temperature
        else:
            return ModelType.GPT5_REASONING  # gpt-5, gpt-5-mini, gpt-5-nano, gpt-5-pro
    
    # O-series reasoning models (OpenAI o1, o3, etc. - support temperature=1.0)
    if re.match(r'^o[1-9](-\w+)?$', model_lower) or re.match(r'^o[1-9][0-9]*(-\w+)?$', model_lower):
        return ModelType.REASONING
    
    # Vision models
    if any(vision_indicator in model_lower for vision_indicator in [
        'vision', 'gpt-4v', 'gpt-4-vision', 'claude-3', 'gemini-pro-vision'
    ]):
        return ModelType.VISION
    
    # Code models
    if any(code_indicator in model_lower for code_indicator in [
        'code', 'codestral', 'codegemma', 'starcoder', 'deepseek-coder'
    ]):
        return ModelType.CODE
    
    # Instruct models
    if any(instruct_indicator in model_lower for instruct_indicator in [
        'instruct', 'chat-bison', 'text-bison'
    ]):
        return ModelType.INSTRUCT
    
    # Provider-specific detection
    if provider_lower == "openai":
        if model_lower.startswith('gpt-'):
            return ModelType.CHAT
        elif model_lower.startswith('o1') or model_lower.startswith('o3') or model_lower.startswith('o4'):
            return ModelType.REASONING
    
    elif provider_lower == "anthropic":
        if 'claude' in model_lower:
            if 'claude-3' in model_lower:
                return ModelType.VISION  # Claude 3 has vision capabilities
            return ModelType.CHAT
    
    elif provider_lower == "google":
        if 'gemini' in model_lower:
            if 'vision' in model_lower:
                return ModelType.VISION
            return ModelType.CHAT
    
    # Self-hosted providers - assume chat capabilities
    elif provider_lower in ['ollama', 'lm_studio', 'localai', 'vllm', 'text_generation_webui']:
        return ModelType.CHAT
    
    # Default to chat for unknown models
    log.debug(f"Unknown model type for {model_name} ({provider}), defaulting to CHAT")
    return ModelType.CHAT


def get_model_capabilities(model_name: str, provider: str = "") -> ModelCapabilities:
    """
    Get the capabilities for a specific model.
    
    Args:
        model_name: Name of the model
        provider: Provider name
        
    Returns:
        ModelCapabilities instance
    """
    model_type = detect_model_type(model_name, provider)
    return MODEL_CAPABILITIES[model_type]


def filter_parameters(
    params: Dict[str, Any], 
    model_name: str, 
    provider: str = "",
    log_adjustments: bool = True
) -> tuple[Dict[str, Any], List[str]]:
    """
    Filter parameters based on model capabilities.
    
    Args:
        params: Dictionary of parameters to filter
        model_name: Name of the model
        provider: Provider name
        log_adjustments: Whether to log parameter adjustments
        
    Returns:
        Tuple of (filtered_params, list_of_adjustments_made)
    """
    capabilities = get_model_capabilities(model_name, provider)
    filtered_params = params.copy()
    adjustments = []
    
    # Handle forced temperature
    if capabilities.forced_temperature is not None:
        if 'temperature' in filtered_params:
            old_temp = filtered_params['temperature']
            if old_temp != capabilities.forced_temperature:
                filtered_params['temperature'] = capabilities.forced_temperature
                adjustments.append(f"Temperature adjusted from {old_temp} to {capabilities.forced_temperature} (model requirement)")
        else:
            filtered_params['temperature'] = capabilities.forced_temperature
    
    # Remove unsupported parameters (but skip temperature if it was forced)
    for param in list(filtered_params.keys()):
        if param in capabilities.unsupported_params:
            # Don't remove temperature if it was forced
            if param == 'temperature' and capabilities.forced_temperature is not None:
                continue
            removed_value = filtered_params.pop(param)
            adjustments.append(f"Removed unsupported parameter '{param}' (was {removed_value})")
    
    # Validate parameter ranges
    param_validations = [
        ('temperature', capabilities.supports_temperature, capabilities.temperature_range),
        ('top_p', capabilities.supports_top_p, capabilities.top_p_range),
        ('frequency_penalty', capabilities.supports_frequency_penalty, capabilities.frequency_penalty_range),
        ('presence_penalty', capabilities.supports_presence_penalty, capabilities.presence_penalty_range),
    ]
    
    for param_name, is_supported, (min_val, max_val) in param_validations:
        if param_name in filtered_params:
            if not is_supported:
                removed_value = filtered_params.pop(param_name)
                adjustments.append(f"Removed unsupported parameter '{param_name}' (was {removed_value})")
            else:
                value = filtered_params[param_name]
                if value < min_val:
                    filtered_params[param_name] = min_val
                    adjustments.append(f"{param_name} clamped from {value} to {min_val}")
                elif value > max_val:
                    filtered_params[param_name] = max_val
                    adjustments.append(f"{param_name} clamped from {value} to {max_val}")
    
    # Log adjustments if requested
    if log_adjustments and adjustments:
        log.info(f"Model {model_name} parameter adjustments: {'; '.join(adjustments)}")
    
    return filtered_params, adjustments


def get_model_info(model_name: str, provider: str = "") -> Dict[str, Any]:
    """
    Get comprehensive information about a model's capabilities.
    
    Args:
        model_name: Name of the model
        provider: Provider name
        
    Returns:
        Dictionary with model information
    """
    capabilities = get_model_capabilities(model_name, provider)
    
    return {
        "model_name": model_name,
        "provider": provider,
        "model_type": capabilities.model_type.value,
        "has_reasoning": capabilities.has_reasoning,
        "supports_vision": capabilities.supports_vision,
        "supports_function_calling": capabilities.supports_function_calling,
        "supports_streaming": capabilities.supports_streaming,
        "parameter_support": {
            "temperature": {
                "supported": capabilities.supports_temperature,
                "range": capabilities.temperature_range if capabilities.supports_temperature else None,
                "forced_value": capabilities.forced_temperature,
            },
            "top_p": {
                "supported": capabilities.supports_top_p,
                "range": capabilities.top_p_range if capabilities.supports_top_p else None,
            },
            "frequency_penalty": {
                "supported": capabilities.supports_frequency_penalty,
                "range": capabilities.frequency_penalty_range if capabilities.supports_frequency_penalty else None,
            },
            "presence_penalty": {
                "supported": capabilities.supports_presence_penalty,
                "range": capabilities.presence_penalty_range if capabilities.supports_presence_penalty else None,
            },
        },
        "unsupported_params": list(capabilities.unsupported_params),
    }


def get_parameter_help(model_name: str, provider: str = "") -> str:
    """
    Get user-friendly help text about model parameter constraints.
    
    Args:
        model_name: Name of the model
        provider: Provider name
        
    Returns:
        Formatted help text
    """
    info = get_model_info(model_name, provider)
    lines = [f"**Model:** {model_name} ({info['model_type']} type)"]
    
    if info['has_reasoning']:
        lines.append("🧠 **Reasoning Model:** Uses internal thinking process")
    
    if info['supports_vision']:
        lines.append("👁️ **Vision Capable:** Can analyze images")
    
    param_support = info['parameter_support']
    
    # Temperature
    temp_info = param_support['temperature']
    if temp_info['forced_value'] is not None:
        lines.append(f"🌡️ **Temperature:** Fixed at {temp_info['forced_value']} (cannot be changed)")
    elif temp_info['supported']:
        lines.append(f"🌡️ **Temperature:** {temp_info['range'][0]} - {temp_info['range'][1]}")
    else:
        lines.append("🌡️ **Temperature:** Not supported")
    
    # Other parameters
    for param_name, param_info in param_support.items():
        if param_name == 'temperature':
            continue  # Already handled above
        
        if param_info['supported']:
            range_str = f"{param_info['range'][0]} - {param_info['range'][1]}"
            lines.append(f"⚙️ **{param_name.replace('_', ' ').title()}:** {range_str}")
        else:
            lines.append(f"❌ **{param_name.replace('_', ' ').title()}:** Not supported")
    
    if info['unsupported_params']:
        lines.append(f"🚫 **Unsupported:** {', '.join(info['unsupported_params'])}")
    
    return "\n".join(lines)
