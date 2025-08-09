"""
Tool orchestration layer for SkynetV2.

Provides internal tool call schema and execution mapping for AI agent tool orchestration.
This enables the AI to generate structured tool invocation JSON and execute them through
the existing tool registry.
"""

from __future__ import annotations

import json
import time
import re
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Union

try:
    import discord
except ImportError:
    discord = None  # Handle import in Red environment

try:
    from .logging_system import log_info, log_error_event
except ImportError:
    # Fallback logging functions
    async def log_info(message: str, **kwargs):
        pass
    async def log_error_event(guild, user, channel, message: str):
        pass


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


@dataclass
class Variable:
    """Represents a contextual variable that can be injected into prompts."""
    name: str
    description: str
    value_type: str  # "string", "datetime", "user", "channel", "guild"
    category: str = "general"  # general, time, user, server, system
    requires_guild: bool = False
    requires_user: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)


class VariableResolver:
    """Resolves contextual variables for prompt injection."""
    
    def __init__(self, cog):
        self.cog = cog
        self._variables: Dict[str, Variable] = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        """Initialize available variables."""
        # Time variables
        self._variables["timestamp"] = Variable(
            name="timestamp",
            description="Current timestamp in ISO format",
            value_type="datetime",
            category="time"
        )
        
        self._variables["time"] = Variable(
            name="time",
            description="Current time in HH:MM format",
            value_type="string",
            category="time"
        )
        
        self._variables["date"] = Variable(
            name="date",
            description="Current date in YYYY-MM-DD format",
            value_type="string",
            category="time"
        )
        
        self._variables["datetime"] = Variable(
            name="datetime",
            description="Current date and time in readable format",
            value_type="string",
            category="time"
        )
        
        # User variables
        self._variables["user_name"] = Variable(
            name="user_name",
            description="Username of the current user",
            value_type="string",
            category="user",
            requires_user=True
        )
        
        self._variables["user_display_name"] = Variable(
            name="user_display_name",
            description="Display name (nickname or username) of the current user in the server",
            value_type="string",
            category="user",
            requires_user=True,
            requires_guild=True
        )
        
        self._variables["user_mention"] = Variable(
            name="user_mention",
            description="Mentionable string for the current user",
            value_type="string",
            category="user",
            requires_user=True
        )
        
        self._variables["user_id"] = Variable(
            name="user_id",
            description="Discord ID of the current user",
            value_type="string",
            category="user",
            requires_user=True
        )
        
        self._variables["user_joined"] = Variable(
            name="user_joined",
            description="Date when the user joined the server",
            value_type="string",
            category="user",
            requires_user=True,
            requires_guild=True
        )
        
        # Server/Guild variables
        self._variables["server_name"] = Variable(
            name="server_name",
            description="Name of the current Discord server",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["server_id"] = Variable(
            name="server_id",
            description="Discord ID of the current server",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["server_member_count"] = Variable(
            name="server_member_count",
            description="Number of members in the current server",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["channel_name"] = Variable(
            name="channel_name",
            description="Name of the current channel",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["channel_id"] = Variable(
            name="channel_id",
            description="Discord ID of the current channel",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["channel_mention"] = Variable(
            name="channel_mention",
            description="Mentionable string for the current channel",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        # System variables
        self._variables["bot_name"] = Variable(
            name="bot_name",
            description="Name of the bot",
            value_type="string",
            category="system"
        )
        
        self._variables["bot_mention"] = Variable(
            name="bot_mention",
            description="Mentionable string for the bot",
            value_type="string",
            category="system"
        )
        
        self._variables["command_prefix"] = Variable(
            name="command_prefix",
            description="Command prefix for the bot in this server",
            value_type="string",
            category="system",
            requires_guild=True
        )
        
        # Additional contextual variables
        self._variables["weekday"] = Variable(
            name="weekday",
            description="Current day of the week (Monday, Tuesday, etc.)",
            value_type="string",
            category="time"
        )
        
        self._variables["user_created"] = Variable(
            name="user_created",
            description="Date when the user's Discord account was created",
            value_type="string",
            category="user",
            requires_user=True
        )
        
        self._variables["user_avatar"] = Variable(
            name="user_avatar",
            description="URL of the user's avatar image",
            value_type="string",
            category="user",
            requires_user=True
        )
        
        self._variables["server_created"] = Variable(
            name="server_created",
            description="Date when the server was created",
            value_type="string",
            category="server",
            requires_guild=True
        )
        
        self._variables["server_owner"] = Variable(
            name="server_owner",
            description="Name of the server owner",
            value_type="string",
            category="server",
            requires_guild=True
        )
    
    async def resolve_variable(self, var_name: str, guild=None, channel=None, user=None) -> Optional[str]:
        """Resolve a single variable to its value."""
        if var_name not in self._variables:
            return None
        
        variable = self._variables[var_name]
        
        # Check requirements
        if variable.requires_guild and not guild:
            return f"[{var_name}: requires guild context]"
        if variable.requires_user and not user:
            return f"[{var_name}: requires user context]"
        
        try:
            # Time variables
            if var_name == "timestamp":
                return datetime.now().isoformat()
            elif var_name == "time":
                return datetime.now().strftime("%H:%M")
            elif var_name == "date":
                return datetime.now().strftime("%Y-%m-%d")
            elif var_name == "datetime":
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif var_name == "weekday":
                return datetime.now().strftime("%A")
            
            # User variables
            elif var_name == "user_name" and user:
                return str(user.name)
            elif var_name == "user_display_name" and user and guild:
                member = guild.get_member(user.id)
                return member.display_name if member else str(user.name)
            elif var_name == "user_mention" and user:
                return user.mention
            elif var_name == "user_id" and user:
                return str(user.id)
            elif var_name == "user_joined" and user and guild:
                member = guild.get_member(user.id)
                if member and member.joined_at:
                    return member.joined_at.strftime("%Y-%m-%d")
                return "Unknown"
            elif var_name == "user_created" and user:
                if hasattr(user, 'created_at') and user.created_at:
                    return user.created_at.strftime("%Y-%m-%d")
                return "Unknown"
            elif var_name == "user_avatar" and user:
                if hasattr(user, 'display_avatar'):
                    return str(user.display_avatar.url)
                elif hasattr(user, 'avatar_url'):
                    return str(user.avatar_url)
                return "No avatar"
            
            # Server variables
            elif var_name == "server_name" and guild:
                return guild.name
            elif var_name == "server_id" and guild:
                return str(guild.id)
            elif var_name == "server_member_count" and guild:
                return str(guild.member_count or 0)
            elif var_name == "server_created" and guild:
                if hasattr(guild, 'created_at') and guild.created_at:
                    return guild.created_at.strftime("%Y-%m-%d")
                return "Unknown"
            elif var_name == "server_owner" and guild:
                if hasattr(guild, 'owner') and guild.owner:
                    return str(guild.owner.name)
                return "Unknown"
            elif var_name == "channel_name" and channel:
                return channel.name if hasattr(channel, 'name') else "Unknown"
            elif var_name == "channel_id" and channel:
                return str(channel.id)
            elif var_name == "channel_mention" and channel:
                return channel.mention if hasattr(channel, 'mention') else f"#{channel.name}"
            
            # System variables
            elif var_name == "bot_name":
                return self.cog.bot.user.name if self.cog.bot.user else "SkynetV2"
            elif var_name == "bot_mention":
                return self.cog.bot.user.mention if self.cog.bot.user else "@SkynetV2"
            elif var_name == "command_prefix" and guild:
                # Get command prefix for this guild
                try:
                    prefixes = await self.cog.bot.get_valid_prefixes(guild)
                    return prefixes[0] if prefixes else "!"
                except:
                    return "!"
            
            return f"[{var_name}: unresolved]"
            
        except Exception as e:
            await log_info(f"Error resolving variable {var_name}: {e}")
            return f"[{var_name}: error]"
    
    async def resolve_prompt(self, prompt: str, guild=None, channel=None, user=None) -> str:
        """Resolve all variables in a prompt string."""
        if not prompt:
            return prompt
        
        # Find all variable placeholders: {{variable_name}}
        pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}'
        matches = re.findall(pattern, prompt)
        
        resolved_prompt = prompt
        for var_name in matches:
            placeholder = f"{{{{{var_name}}}}}"
            value = await self.resolve_variable(var_name, guild, channel, user)
            if value is not None:
                resolved_prompt = resolved_prompt.replace(placeholder, value)
        
        return resolved_prompt
    
    def get_available_variables(self, guild=None, user=None) -> List[Variable]:
        """Get list of available variables for the given context."""
        available = []
        
        for variable in self._variables.values():
            # Check if requirements are met
            if variable.requires_guild and not guild:
                continue
            if variable.requires_user and not user:
                continue
            
            available.append(variable)
        
        return available
    
    def get_variables_by_category(self, category: str, guild=None, user=None) -> List[Variable]:
        """Get variables filtered by category."""
        return [var for var in self.get_available_variables(guild, user) if var.category == category]
    
    def get_variables_help_text(self, guild=None, user=None) -> str:
        """Generate help text for available variables."""
        variables = self.get_available_variables(guild, user)
        
        if not variables:
            return "No variables available in this context."
        
        # Group by category
        categories = {}
        for var in variables:
            if var.category not in categories:
                categories[var.category] = []
            categories[var.category].append(var)
        
        help_text = "**Available Variables:**\n"
        help_text += "Use `{{variable_name}}` in prompts to inject contextual data.\n\n"
        
        for category, vars_list in categories.items():
            help_text += f"**{category.title()} Variables:**\n"
            for var in vars_list:
                help_text += f"• `{{{{{var.name}}}}}` - {var.description}\n"
            help_text += "\n"
        
        help_text += "**Example:** `Hello {{user_display_name}}, the time is {{time}} on {{date}}.`"
        return help_text


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
        self.variable_resolver = VariableResolver(self)
    
    async def resolve_prompt_variables(self, prompt: str, guild=None, channel=None, user=None) -> str:
        """Convenience method to resolve variables in prompts."""
        if not hasattr(self, 'variable_resolver'):
            self._init_orchestration()
        return await self.variable_resolver.resolve_prompt(prompt, guild, channel, user)
    
    def get_available_variables_help(self, guild=None, user=None) -> str:
        """Get help text for available variables."""
        if not hasattr(self, 'variable_resolver'):
            self._init_orchestration()
        return self.variable_resolver.get_variables_help_text(guild, user)
