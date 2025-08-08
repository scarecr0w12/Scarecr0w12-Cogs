"""
Tool orchestration layer for SkynetV2.

Provides internal tool call schema and execution mapping for AI agent tool orchestration.
This enables the AI to generate structured tool invocation JSON and execute them through
the existing tool registry.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Union

try:
    import discord
except ImportError:
    discord = None  # Handle import in Red environment


@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    choices: Optional[List[str]] = None  # For enum-like parameters


@dataclass
class ToolSchema:
    """Schema definition for a tool that can be called by agents."""
    name: str
    description: str
    parameters: List[ToolParameter]
    category: str = "general"  # general, search, content, analysis
    requires_guild: bool = True
    admin_only: bool = False
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format for LLM consumption."""
        properties: Dict[str, Any] = {}
        required = []
        
        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description
            }
            if param.choices:
                prop["enum"] = param.choices  # List[str] -> Any is valid
            if param.default is not None:
                prop["default"] = param.default
                
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            },
            "category": self.category,
            "requires_guild": self.requires_guild,
            "admin_only": self.admin_only
        }


@dataclass
class ToolCall:
    """Represents a tool invocation request."""
    name: str
    parameters: Dict[str, Any]
    call_id: Optional[str] = None  # For tracking multiple calls
    
    @classmethod
    def from_json(cls, data: Union[str, Dict[str, Any]]) -> 'ToolCall':
        """Parse from JSON string or dict."""
        if isinstance(data, str):
            parsed_data = json.loads(data)
        else:
            parsed_data = data
        return cls(
            name=parsed_data["name"],
            parameters=parsed_data.get("parameters", {}),
            call_id=parsed_data.get("call_id")
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), indent=2)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    call_id: Optional[str]
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), indent=2)


class ToolOrchestrator:
    """Orchestrates tool calls from AI agents through existing tool registry."""
    
    def __init__(self, cog):
        self.cog = cog
        self._schemas: Dict[str, ToolSchema] = {}
        self._initialize_schemas()
    
    def _initialize_schemas(self):
        """Initialize tool schemas from the existing tool registry."""
        # Map existing tools to schemas
        self._schemas["ping"] = ToolSchema(
            name="ping",
            description="Simple connectivity test that returns 'pong'",
            parameters=[],
            category="general",
            requires_guild=False,
            admin_only=False
        )
        
        self._schemas["websearch"] = ToolSchema(
            name="websearch", 
            description="Search the web using configured search provider",
            parameters=[
                ToolParameter("query", "string", "Search query string", required=True)
            ],
            category="search",
            requires_guild=True,
            admin_only=False
        )
        
        self._schemas["autosearch"] = ToolSchema(
            name="autosearch",
            description="Automatically classify query and determine best search strategy (search/scrape/crawl/deep_research)",
            parameters=[
                ToolParameter("query", "string", "Query to analyze and potentially execute", required=True),
                ToolParameter("execute", "boolean", "Whether to execute the determined strategy", default=False)
            ],
            category="search",
            requires_guild=True,
            admin_only=False
        )
    
    def get_available_tools(self, guild=None, user=None) -> List[ToolSchema]:
        """Get list of available tools for the given context."""
        available = []
        
        for schema in self._schemas.values():
            # Check if tool is enabled (if guild context exists)
            if guild and hasattr(self.cog, '_tool_is_enabled'):
                # This would need to be awaited in async context
                pass
                
            # Check admin requirements
            if schema.admin_only and user and guild:
                member = guild.get_member(user.id)
                if not member or not member.guild_permissions.manage_guild:
                    continue
            
            available.append(schema)
        
        return available
    
    def get_tools_json_schema(self, guild=None, user=None) -> List[Dict[str, Any]]:
        """Get JSON schema representation of available tools."""
        return [tool.to_json_schema() for tool in self.get_available_tools(guild, user)]
    
    async def execute_tool_call(self, call: ToolCall, guild, channel, user) -> ToolResult:
        """Execute a tool call through the existing tool infrastructure."""
        start_time = time.perf_counter()
        call_id = call.call_id or f"{call.name}_{int(start_time * 1000)}"
        
        try:
            # Validate tool exists and is available
            if call.name not in self._schemas:
                return ToolResult(
                    call_id=call_id,
                    success=False,
                    error=f"Unknown tool: {call.name}"
                )
            
            schema = self._schemas[call.name]
            
            # Check if tool is enabled
            if hasattr(self.cog, '_tool_is_enabled') and not await self.cog._tool_is_enabled(guild, call.name):
                return ToolResult(
                    call_id=call_id,
                    success=False,
                    error=f"Tool '{call.name}' is disabled"
                )
            
            # Check admin permissions
            if schema.admin_only:
                member = guild.get_member(user.id)
                if not member or not member.guild_permissions.manage_guild:
                    return ToolResult(
                        call_id=call_id,
                        success=False,
                        error=f"Tool '{call.name}' requires admin permissions"
                    )
            
            # Check rate limits
            if hasattr(self.cog, '_check_tool_rate_limits'):
                rate_error = await self.cog._check_tool_rate_limits(guild, channel, user, call.name)
                if rate_error:
                    return ToolResult(
                        call_id=call_id,
                        success=False,
                        error=f"Rate limit: {rate_error}"
                    )
            
            # Execute the tool
            if call.name == "ping":
                result = "pong"
            elif call.name == "websearch":
                query = call.parameters.get("query", "")
                if not query:
                    raise ValueError("query parameter is required")
                if hasattr(self.cog, '_tool_run_websearch'):
                    result = await self.cog._tool_run_websearch(guild=guild, query=query, user=user)
                else:
                    result = f"[MOCK] websearch for: {query}"
            elif call.name == "autosearch":
                query = call.parameters.get("query", "")
                execute = call.parameters.get("execute", False)
                if not query:
                    raise ValueError("query parameter is required")
                if hasattr(self.cog, '_tool_run_autosearch'):
                    result = await self.cog._tool_run_autosearch(guild=guild, query=query, user=user, execute=execute)
                else:
                    result = f"[MOCK] autosearch for: {query} (execute={execute})"
            else:
                raise ValueError(f"Tool execution not implemented: {call.name}")
            
            execution_time = int((time.perf_counter() - start_time) * 1000)
            
            return ToolResult(
                call_id=call_id,
                success=True,
                result=result,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                call_id=call_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    async def execute_multiple_calls(self, calls: List[ToolCall], guild, channel, user) -> List[ToolResult]:
        """Execute multiple tool calls in sequence."""
        results = []
        for call in calls:
            result = await self.execute_tool_call(call, guild, channel, user)
            results.append(result)
            # Stop on first failure if critical
            if not result.success and call.name in ["ping"]:  # Add critical tools here
                break
        return results
    
    def simulate_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Simulate a tool call for debugging - returns JSON representation."""
        call = ToolCall(name=tool_name, parameters=parameters, call_id=f"sim_{int(time.perf_counter() * 1000)}")
        
        # Simulate successful result for debugging
        result = ToolResult(
            call_id=call.call_id,
            success=True,
            result=f"[SIMULATED] Tool '{tool_name}' would execute with parameters: {json.dumps(parameters)}",
            execution_time_ms=42
        )
        
        return json.dumps({
            "tool_call": json.loads(call.to_json()),
            "result": json.loads(result.to_json())
        }, indent=2)


# Mixin to be added to the main SkynetV2 cog
class OrchestrationMixin:
    """Mixin providing orchestration capabilities to SkynetV2."""
    
    def _init_orchestration(self):
        """Initialize orchestration system."""
        self.orchestrator = ToolOrchestrator(self)
