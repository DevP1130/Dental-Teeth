#!/usr/bin/env python3
"""
Simple script to test if your OpenAI API key is valid.
Set your API key as an environment variable: export OPENAI_API_KEY="your-key-here"
Or uncomment the line below and put your key directly (not recommended for production).
"""

import os
from openai import OpenAI

def test_openai_key():
    # Get API key from environment variable (recommended)
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # Uncomment the line below and replace with your actual key if you prefer (not recommended)
    # api_key = "your-api-key-here"
    
    if not api_key:
        print("❌ No API key found!")
        print("Please set your OpenAI API key as an environment variable:")
        print("export OPENAI_API_KEY='your-api-key-here'")
        print("Or uncomment the line in this script to set it directly.")
        return False
    
    try:
        # Initialize the OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Make a simple request to list available models
        print("🔍 Testing API key...")
        models = client.models.list()
        
        print("✅ API key is VALID!")
        print(f"📊 Found {len(models.data)} available models")
        
        # Show a few example models
        print("\n🤖 Some available models:")
        for i, model in enumerate(models.data[:5]):
            print(f"  • {model.id}")
        
        if len(models.data) > 5:
            print(f"  ... and {len(models.data) - 5} more")
            
        return True
        
    except Exception as e:
        error_message = str(e)
        
        if "authentication" in error_message.lower() or "unauthorized" in error_message.lower():
            print("❌ API key is INVALID!")
            print("Please check your OpenAI API key and try again.")
        elif "quota" in error_message.lower():
            print("⚠️  API key is valid but you've exceeded your quota.")
            print("Please check your OpenAI billing and usage limits.")
        else:
            print(f"❌ Error testing API key: {error_message}")
        
        return False

if __name__ == "__main__":
    print("🚀 OpenAI API Key Tester")
    print("=" * 30)
    test_openai_key()
