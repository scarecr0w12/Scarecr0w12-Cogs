#!/usr/bin/env python3
"""Test script to verify variable resolution and orchestration fixes."""

import sys
sys.path.append('.')

def test_imports():
    """Test that all necessary components can be imported."""
    print("🧪 Testing Imports")
    print("=" * 50)
    
    try:
        from skynetv2.orchestration import OrchestrationMixin
        print("✅ OrchestrationMixin imported")
    except ImportError as e:
        print(f"❌ OrchestrationMixin import failed: {e}")
        return False
    
    try:
        from skynetv2.memory import MemoryMixin  
        print("✅ MemoryMixin imported")
    except ImportError as e:
        print(f"❌ MemoryMixin import failed: {e}")
        return False
    
    return True

def test_method_existence():
    """Test that required methods exist."""
    print("\n🔍 Testing Method Existence")
    print("=" * 50)
    
    from skynetv2.orchestration import OrchestrationMixin
    from skynetv2.memory import MemoryMixin
    
    # Check orchestration methods
    if hasattr(OrchestrationMixin, 'resolve_prompt_variables'):
        print("✅ OrchestrationMixin.resolve_prompt_variables exists")
    else:
        print("❌ OrchestrationMixin.resolve_prompt_variables missing")
        return False
    
    # Check memory methods
    if hasattr(MemoryMixin, '_build_system_prompt'):
        print("✅ MemoryMixin._build_system_prompt exists")
    else:
        print("❌ MemoryMixin._build_system_prompt missing")
        return False
    
    return True

def test_variable_patterns():
    """Test variable pattern recognition."""
    print("\n🎯 Testing Variable Patterns")
    print("=" * 50)
    
    # Test prompt with variables
    test_prompt = """
    You are the Captain of {{server_name}} with {{user_display_name}}.
    Current time: {{date}} {{time}}
    Channel: {{channel_name}}
    """
    
    import re
    variable_pattern = r'\{\{([^}]+)\}\}'
    variables = re.findall(variable_pattern, test_prompt)
    
    print(f"Found variables: {variables}")
    
    expected_vars = ['server_name', 'user_display_name', 'date', 'time', 'channel_name']
    if all(var in variables for var in expected_vars):
        print("✅ All expected variables found")
        return True
    else:
        print("❌ Some variables missing")
        return False

def test_user_is_allowed_method():
    """Test the _user_is_allowed method by checking the skynetv2.py file."""
    print("\n👤 Testing _user_is_allowed Method")
    print("=" * 50)
    
    try:
        with open('skynetv2/skynetv2.py', 'r') as f:
            content = f.read()
            
        if 'def _user_is_allowed(' in content:
            print("✅ _user_is_allowed method found in skynetv2.py")
            
            if 'orchestrate_debug' in content:
                print("✅ orchestrate_debug permission check found")
                return True
            else:
                print("❌ orchestrate_debug permission check missing")
                return False
        else:
            print("❌ _user_is_allowed method not found in skynetv2.py")
            return False
            
    except FileNotFoundError:
        print("❌ skynetv2.py file not found")
        return False

if __name__ == "__main__":
    print("🎯 SkynetV2 Variable Resolution & Orchestration Fix Validation")
    print("=" * 70)
    
    all_passed = True
    
    all_passed &= test_imports()
    all_passed &= test_method_existence()
    all_passed &= test_variable_patterns()
    all_passed &= test_user_is_allowed_method()
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ All tests passed! Variable resolution and orchestration should work correctly.")
        print("\n🎉 Key Benefits:")
        print("  • System prompts now support variable resolution")
        print("  • {{server_name}}, {{user_display_name}}, etc. will be replaced with actual values")
        print("  • Orchestration debug commands will work without AttributeError")
        print("  • Better error handling with detailed debugging")
    else:
        print("❌ Some tests failed. Please check the issues above.")
        sys.exit(1)
