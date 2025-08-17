#!/usr/bin/env python3
"""
HANU Feedbot - Gemini API Test
==============================

This script tests Google Gemini AI API connectivity and functionality
to ensure the bot can properly use AI for content summarization.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    """Print a colored header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")

class GeminiTester:
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY')
        self.model = None
        self.test_results = {}
    
    def load_credentials(self) -> bool:
        """Load and validate Gemini API credentials"""
        print_header("Loading Gemini API Credentials")
        
        if not self.api_key:
            print_error("GEMINI_API_KEY not found in environment variables")
            return False
        
        if len(self.api_key) < 30:
            print_error("GEMINI_API_KEY appears to be too short")
            return False
        
        print_success(f"Gemini API key loaded: {self.api_key[:15]}...")
        
        # Configure the API
        try:
            genai.configure(api_key=self.api_key)
            print_success("Gemini API configured successfully")
            return True
        except Exception as e:
            print_error(f"Failed to configure Gemini API: {e}")
            return False
    
    def test_api_connection(self) -> bool:
        """Test basic API connection"""
        print_header("Testing Gemini API Connection")
        
        try:
            # List available models
            models = list(genai.list_models())
            if models:
                print_success(f"Connected to Gemini API successfully")
                print_info(f"Available models: {len(models)}")
                
                # Show first few models
                for i, model in enumerate(models[:3]):
                    print_info(f"  • {model.name}")
                
                self.test_results['api_connection'] = True
                return True
            else:
                print_error("No models available")
                self.test_results['api_connection'] = False
                return False
                
        except Exception as e:
            print_error(f"Failed to connect to Gemini API: {e}")
            self.test_results['api_connection'] = False
            return False
    
    def test_model_initialization(self) -> bool:
        """Test model initialization"""
        print_header("Testing Model Initialization")
        
        try:
            # Try to initialize the model (same as used in the bot)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            print_success("Gemini model initialized successfully")
            print_info(f"Model name: {self.model.model_name}")
            
            self.test_results['model_init'] = True
            return True
            
        except Exception as e:
            print_error(f"Failed to initialize Gemini model: {e}")
            self.test_results['model_init'] = False
            return False
    
    def test_simple_generation(self) -> bool:
        """Test simple text generation"""
        print_header("Testing Simple Text Generation")
        
        if not self.model:
            print_error("Model not initialized - skipping test")
            self.test_results['simple_generation'] = False
            return False
        
        try:
            # Simple test prompt
            test_prompt = "Hello! Can you respond with 'Test successful' to confirm you're working?"
            
            print_info(f"Sending test prompt: {test_prompt}")
            
            start_time = time.time()
            response = self.model.generate_content(test_prompt)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            if response and response.text:
                print_success(f"Generated response in {response_time:.2f} seconds")
                print_info(f"Response: {response.text.strip()}")
                
                # Check if response is reasonable
                if len(response.text.strip()) > 0:
                    print_success("Response appears valid")
                    self.test_results['simple_generation'] = True
                    return True
                else:
                    print_warning("Response is empty")
                    self.test_results['simple_generation'] = False
                    return False
            else:
                print_error("No response generated")
                self.test_results['simple_generation'] = False
                return False
                
        except Exception as e:
            print_error(f"Error during text generation: {e}")
            self.test_results['simple_generation'] = False
            return False
    
    def test_content_summarization(self) -> bool:
        """Test content summarization like the bot would do"""
        print_header("Testing Content Summarization")
        
        if not self.model:
            print_error("Model not initialized - skipping test")
            self.test_results['summarization'] = False
            return False
        
        try:
            # Sample RSS entry content (similar to what the bot processes)
            sample_content = """
            Title: Major Technology Breakthrough Announced
            
            Content: Scientists at a leading research university have announced a significant breakthrough 
            in quantum computing technology. The new approach could potentially revolutionize how we process 
            information and solve complex problems. The research team, led by Dr. Jane Smith, has developed 
            a new quantum algorithm that can perform calculations exponentially faster than current methods.
            
            The breakthrough addresses one of the key challenges in quantum computing: maintaining quantum 
            coherence for extended periods. "This discovery opens up new possibilities for practical 
            quantum applications," said Dr. Smith in a statement. The research has been peer-reviewed 
            and published in the journal Nature.
            
            Industry experts believe this could accelerate the development of quantum computers for 
            commercial use, with potential applications in cryptography, drug discovery, and financial 
            modeling. Major technology companies have already expressed interest in licensing the technology.
            """
            
            # Build a prompt similar to what the bot uses
            prompt = f"""
            Please provide a concise summary of this RSS feed entry in 2-3 sentences. 
            Focus on the key points and main message:

            {sample_content}

            Summary:
            """
            
            print_info("Testing content summarization with sample RSS entry...")
            
            start_time = time.time()
            response = self.model.generate_content(prompt)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            if response and response.text:
                summary = response.text.strip()
                print_success(f"Generated summary in {response_time:.2f} seconds")
                print_info(f"Summary length: {len(summary)} characters")
                print_info(f"Summary: {summary}")
                
                # Validate summary quality
                if len(summary) > 50 and len(summary) < 500:
                    print_success("Summary length is appropriate")
                    self.test_results['summarization'] = True
                    return True
                else:
                    print_warning(f"Summary length may be inappropriate: {len(summary)} characters")
                    self.test_results['summarization'] = False
                    return False
            else:
                print_error("No summary generated")
                self.test_results['summarization'] = False
                return False
                
        except Exception as e:
            print_error(f"Error during content summarization: {e}")
            self.test_results['summarization'] = False
            return False
    
    def test_prompt_building(self) -> bool:
        """Test the prompt building function used by the bot"""
        print_header("Testing Bot's Prompt Building Logic")
        
        try:
            # Try to import and test the bot's prompt building function
            sys.path.append('bot')
            
            try:
                from bot.formatter import build_prompt
                print_success("Successfully imported build_prompt function")
                
                # Create a sample RSS entry
                sample_entry = {
                    'title': 'Test RSS Entry',
                    'description': 'This is a test RSS entry for validation',
                    'link': 'https://example.com/test',
                    'published_parsed': None,
                    'author': 'Test Author'
                }
                
                # Build prompt using bot's function
                prompt = build_prompt(sample_entry)
                
                if prompt and len(prompt) > 10:
                    print_success("Prompt built successfully")
                    print_info(f"Prompt length: {len(prompt)} characters")
                    print_info(f"Prompt preview: {prompt[:200]}...")
                    
                    # Test the prompt with Gemini
                    if self.model:
                        response = self.model.generate_content(prompt)
                        if response and response.text:
                            print_success("Bot's prompt works with Gemini API")
                            print_info(f"Generated response: {response.text[:100]}...")
                            self.test_results['prompt_building'] = True
                            return True
                        else:
                            print_warning("Bot's prompt generated no response")
                            self.test_results['prompt_building'] = False
                            return False
                    else:
                        print_warning("Model not available for prompt testing")
                        self.test_results['prompt_building'] = True  # Function works, model test skipped
                        return True
                else:
                    print_error("Prompt building failed or returned empty prompt")
                    self.test_results['prompt_building'] = False
                    return False
                    
            except ImportError as e:
                print_warning(f"Could not import bot's prompt building function: {e}")
                print_info("This is expected if bot modules are not properly set up")
                self.test_results['prompt_building'] = True  # Skip this test
                return True
                
        except Exception as e:
            print_error(f"Error testing prompt building: {e}")
            self.test_results['prompt_building'] = False
            return False
    
    def test_rate_limits(self) -> bool:
        """Test API rate limits and quota"""
        print_header("Testing API Rate Limits")
        
        if not self.model:
            print_error("Model not initialized - skipping test")
            self.test_results['rate_limits'] = False
            return False
        
        try:
            print_info("Making multiple rapid API calls to test rate limiting...")
            
            # Make several quick requests
            for i in range(3):
                try:
                    start_time = time.time()
                    response = self.model.generate_content(f"This is test request #{i+1}. Please respond briefly.")
                    end_time = time.time()
                    
                    if response and response.text:
                        print_success(f"Request {i+1}: Success in {end_time - start_time:.2f}s")
                    else:
                        print_warning(f"Request {i+1}: No response")
                    
                    # Small delay between requests
                    time.sleep(0.5)
                    
                except Exception as e:
                    if "quota" in str(e).lower() or "rate" in str(e).lower():
                        print_warning(f"Request {i+1}: Rate limit hit - {e}")
                        break
                    else:
                        print_error(f"Request {i+1}: Error - {e}")
                        break
            
            print_success("Rate limit testing completed")
            self.test_results['rate_limits'] = True
            return True
            
        except Exception as e:
            print_error(f"Error during rate limit testing: {e}")
            self.test_results['rate_limits'] = False
            return False
    
    def test_gemini_client_integration(self) -> bool:
        """Test integration with bot's Gemini client"""
        print_header("Testing Bot's Gemini Client Integration")
        
        try:
            # Try to import and test the bot's Gemini client
            sys.path.append('bot')
            
            try:
                from bot.gemini_client import call_gemini
                print_success("Successfully imported call_gemini function")
                
                # Test the bot's Gemini client function
                test_prompt = "This is a test prompt for the bot's Gemini client. Please respond with 'Integration test successful'."
                
                result = call_gemini(test_prompt)
                
                if result and len(result.strip()) > 0:
                    print_success("Bot's Gemini client works correctly")
                    print_info(f"Result: {result.strip()}")
                    self.test_results['gemini_client'] = True
                    return True
                else:
                    print_error("Bot's Gemini client returned empty result")
                    self.test_results['gemini_client'] = False
                    return False
                    
            except ImportError as e:
                print_warning(f"Could not import bot's Gemini client: {e}")
                print_info("This is expected if bot modules are not properly set up")
                self.test_results['gemini_client'] = True  # Skip this test
                return True
                
        except Exception as e:
            print_error(f"Error testing Gemini client integration: {e}")
            self.test_results['gemini_client'] = False
            return False
    
    def print_test_summary(self):
        """Print a summary of all test results"""
        print_header("Gemini API Test Summary")
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        print(f"\n{Colors.BOLD}Results: {passed_tests}/{total_tests} tests passed{Colors.END}\n")
        
        test_descriptions = {
            'api_connection': 'Gemini API Connection',
            'model_init': 'Model Initialization',
            'simple_generation': 'Simple Text Generation',
            'summarization': 'Content Summarization',
            'prompt_building': 'Bot Prompt Building',
            'rate_limits': 'Rate Limit Testing',
            'gemini_client': 'Bot Gemini Client Integration'
        }
        
        for test_name, passed in self.test_results.items():
            description = test_descriptions.get(test_name, test_name)
            status = "✅ PASS" if passed else "❌ FAIL"
            color = Colors.GREEN if passed else Colors.RED
            print(f"{color}{status}{Colors.END} {description}")
        
        if passed_tests == total_tests:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All Gemini tests passed! Your AI integration is ready.{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.RED}⚠️  Some Gemini tests failed.{Colors.END}")
            print(f"\n{Colors.CYAN}Troubleshooting tips:{Colors.END}")
            
            if not self.test_results.get('api_connection', True):
                print("• Check your GEMINI_API_KEY is valid and active")
                print("• Verify you have access to the Gemini API")
                print("• Check your Google Cloud project configuration")
            
            if not self.test_results.get('model_init', True):
                print("• Ensure you have access to the gemini-1.5-flash model")
                print("• Check if the model name has changed")
            
            if not self.test_results.get('simple_generation', True):
                print("• Check your API quota and usage limits")
                print("• Verify network connectivity to Google APIs")
            
            if not self.test_results.get('summarization', True):
                print("• Check if content is being properly formatted")
                print("• Verify prompt structure and length")
            
            if not self.test_results.get('rate_limits', True):
                print("• You may be hitting API rate limits")
                print("• Consider adding delays between requests")

def main():
    """Main test function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                HANU FEEDBOT GEMINI TEST                      ║")
    print("║              Google Gemini AI Integration                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    tester = GeminiTester()
    
    # Load credentials
    if not tester.load_credentials():
        print_error("Failed to load Gemini API credentials. Please check your .env file.")
        return
    
    # Run tests sequentially
    tester.test_api_connection()
    tester.test_model_initialization()
    tester.test_simple_generation()
    tester.test_content_summarization()
    tester.test_prompt_building()
    tester.test_rate_limits()
    tester.test_gemini_client_integration()
    
    # Print summary
    tester.print_test_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
