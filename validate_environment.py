#!/usr/bin/env python3
"""
HANU Feedbot - Environment Validation
====================================

This script performs comprehensive validation of the environment
to ensure all components are properly configured for the bot.
"""

import os
import sys
import json
import time
import socket
import requests
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

import discord
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

class EnvironmentValidator:
    def __init__(self):
        self.validation_results = {}
        self.critical_issues = []
        self.warnings = []
        self.recommendations = []
    
    def validate_required_files(self) -> bool:
        """Validate that all required files exist"""
        print_header("Validating Required Files")
        
        required_files = {
            '.env': 'Environment configuration',
            'requirements.txt': 'Python dependencies',
            'feeds.txt': 'RSS feed list',
            'cron_worker.py': 'Main worker script',
            'bot/main.py': 'Bot main module',
            'bot/config.py': 'Bot configuration',
            'bot/parser.py': 'Feed parser',
            'bot/formatter.py': 'Content formatter',
            'bot/gemini_client.py': 'Gemini AI client',
            'bot/dispatcher.py': 'Discord dispatcher',
            'bot/facebook_downloader.py': 'Facebook media downloader'
        }
        
        all_exist = True
        for file_path, description in required_files.items():
            path = Path(file_path)
            if path.exists():
                size = path.stat().st_size
                print_success(f"{file_path}: {description} ({size} bytes)")
            else:
                print_error(f"{file_path}: Missing - {description}")
                self.critical_issues.append(f"Missing required file: {file_path}")
                all_exist = False
        
        self.validation_results['required_files'] = all_exist
        return all_exist
    
    def validate_environment_variables(self) -> bool:
        """Validate environment variables"""
        print_header("Validating Environment Variables")
        
        # Critical environment variables
        critical_vars = {
            'DISCORD_BOT_TOKEN': {
                'description': 'Discord bot token',
                'min_length': 50,
                'validator': lambda x: x.startswith(('MTA', 'MTQ', 'OTA'))  # Discord bot token patterns
            },
            'DISCORD_WEBHOOK_URL': {
                'description': 'Discord webhook URL',
                'min_length': 60,
                'validator': lambda x: x.startswith('https://discord.com/api/webhooks/')
            },
            'CHANNEL_ID': {
                'description': 'Discord channel ID',
                'min_length': 10,
                'validator': lambda x: x.isdigit()
            },
            'GEMINI_API_KEY': {
                'description': 'Google Gemini API key',
                'min_length': 30,
                'validator': lambda x: x.startswith('AIza')
            },
            'MAX_AGE_HOURS': {
                'description': 'Maximum age for posts (hours)',
                'min_length': 1,
                'validator': lambda x: x.isdigit() and int(x) > 0
            }
        }
        
        # Optional environment variables
        optional_vars = {
            'GLOBAL_FALLBACK_CHANNEL_ID': 'Fallback Discord channel ID',
            'R2_BUCKET': 'Cloudflare R2 bucket name',
            'R2_ACCESS_KEY_ID': 'R2 access key ID',
            'R2_SECRET_ACCESS_KEY': 'R2 secret access key',
            'R2_ENDPOINT': 'R2 endpoint URL',
            'YT_DLP_COOKIES': 'YouTube-DL cookies file',
            'ADMIN_PASS': 'Admin password',
            'JOB_ENDPOINT': 'Job endpoint path'
        }
        
        all_valid = True
        
        # Validate critical variables
        print_info("Validating critical environment variables:")
        for var_name, config in critical_vars.items():
            value = os.environ.get(var_name)
            
            if not value:
                print_error(f"{var_name}: Missing - {config['description']}")
                self.critical_issues.append(f"Missing critical environment variable: {var_name}")
                all_valid = False
                continue
            
            if len(value) < config['min_length']:
                print_error(f"{var_name}: Too short (minimum {config['min_length']} characters)")
                self.critical_issues.append(f"Invalid {var_name}: too short")
                all_valid = False
                continue
            
            if 'validator' in config and not config['validator'](value):
                print_error(f"{var_name}: Invalid format")
                self.critical_issues.append(f"Invalid {var_name}: wrong format")
                all_valid = False
                continue
            
            # Mask sensitive values for display
            if any(keyword in var_name.lower() for keyword in ['token', 'key', 'secret', 'pass']):
                display_value = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
            else:
                display_value = value
            
            print_success(f"{var_name}: {display_value} - {config['description']}")
        
        # Validate optional variables
        print_info("\nValidating optional environment variables:")
        for var_name, description in optional_vars.items():
            value = os.environ.get(var_name)
            
            if value:
                if any(keyword in var_name.lower() for keyword in ['secret', 'key', 'pass']):
                    display_value = value[:4] + '...' + value[-2:] if len(value) > 6 else '***'
                else:
                    display_value = value
                print_success(f"{var_name}: {display_value} - {description}")
            else:
                print_info(f"{var_name}: Not set - {description}")
        
        self.validation_results['environment_variables'] = all_valid
        return all_valid
    
    def validate_file_permissions(self) -> bool:
        """Validate file permissions"""
        print_header("Validating File Permissions")
        
        # Files that need read access
        read_files = ['.env', 'requirements.txt', 'feeds.txt', 'cron_worker.py']
        
        # Files that need write access (state files)
        write_files = ['seen.json', 'feed_map.json', 'avatar_cache.json', 'groups.json', 'channels.json']
        
        all_good = True
        
        # Test read permissions
        print_info("Testing read permissions:")
        for file_path in read_files:
            path = Path(file_path)
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        f.read(1)  # Try to read one character
                    print_success(f"{file_path}: Read access OK")
                except Exception as e:
                    print_error(f"{file_path}: Read access failed - {e}")
                    self.critical_issues.append(f"Cannot read {file_path}")
                    all_good = False
            else:
                print_warning(f"{file_path}: File does not exist")
        
        # Test write permissions
        print_info("\nTesting write permissions:")
        for file_path in write_files:
            path = Path(file_path)
            try:
                # Try to create/append to file
                with open(path, 'a') as f:
                    pass  # Just test if we can open for writing
                print_success(f"{file_path}: Write access OK")
            except Exception as e:
                print_error(f"{file_path}: Write access failed - {e}")
                self.critical_issues.append(f"Cannot write to {file_path}")
                all_good = False
        
        # Test current directory write permission
        test_file = Path('temp_permission_test.txt')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            test_file.unlink()
            print_success("Current directory: Write access OK")
        except Exception as e:
            print_error(f"Current directory: Write access failed - {e}")
            self.critical_issues.append("Cannot write to current directory")
            all_good = False
        
        self.validation_results['file_permissions'] = all_good
        return all_good
    
    def validate_python_dependencies(self) -> bool:
        """Validate Python dependencies"""
        print_header("Validating Python Dependencies")
        
        # Critical dependencies with version requirements
        critical_deps = {
            'feedparser': 'RSS feed parsing',
            'requests': 'HTTP requests',
            'discord': 'Discord API client',
            'google.generativeai': 'Google Gemini AI',
            'pendulum': 'Date/time handling',
            'aiohttp': 'Async HTTP client',
            'beautifulsoup4': 'HTML parsing',
            'dotenv': 'Environment variables'
        }
        
        # Optional dependencies
        optional_deps = {
            'flask': 'Web framework',
            'celery': 'Task queue',
            'redis': 'Redis client',
            'boto3': 'AWS/S3 client',
            'pytest': 'Testing framework'
        }
        
        all_available = True
        
        print_info("Checking critical dependencies:")
        for module_name, description in critical_deps.items():
            try:
                if module_name == 'beautifulsoup4':
                    import bs4
                    version = getattr(bs4, '__version__', 'unknown')
                elif module_name == 'google.generativeai':
                    import google.generativeai
                    version = getattr(google.generativeai, '__version__', 'unknown')
                elif module_name == 'dotenv':
                    import dotenv
                    version = getattr(dotenv, '__version__', 'unknown')
                else:
                    module = __import__(module_name)
                    version = getattr(module, '__version__', 'unknown')
                
                print_success(f"{module_name}: Available (v{version}) - {description}")
                
            except ImportError as e:
                print_error(f"{module_name}: Not available - {description}")
                self.critical_issues.append(f"Missing critical dependency: {module_name}")
                all_available = False
            except Exception as e:
                print_warning(f"{module_name}: Available but version check failed - {e}")
        
        print_info("\nChecking optional dependencies:")
        for module_name, description in optional_deps.items():
            try:
                module = __import__(module_name)
                version = getattr(module, '__version__', 'unknown')
                print_success(f"{module_name}: Available (v{version}) - {description}")
            except ImportError:
                print_info(f"{module_name}: Not available - {description}")
        
        self.validation_results['python_dependencies'] = all_available
        return all_available
    
    def validate_network_connectivity(self) -> bool:
        """Validate network connectivity"""
        print_header("Validating Network Connectivity")
        
        test_endpoints = [
            ('www.google.com', 80, 'General internet connectivity'),
            ('discord.com', 443, 'Discord API access'),
            ('generativelanguage.googleapis.com', 443, 'Google Gemini API access'),
            ('fetchrss.com', 443, 'RSS feed service access')
        ]
        
        all_connected = True
        
        for host, port, description in test_endpoints:
            try:
                socket.create_connection((host, port), timeout=10).close()
                print_success(f"{host}:{port}: Connected - {description}")
            except socket.error as e:
                print_error(f"{host}:{port}: Failed - {description} ({e})")
                self.critical_issues.append(f"Cannot connect to {host}")
                all_connected = False
            except Exception as e:
                print_warning(f"{host}:{port}: Error - {e}")
        
        # Test HTTP requests
        print_info("\nTesting HTTP requests:")
        test_urls = [
            ('https://httpbin.org/get', 'HTTP GET requests'),
            ('https://api.github.com', 'HTTPS with valid certificate')
        ]
        
        for url, description in test_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print_success(f"{url}: OK - {description}")
                else:
                    print_warning(f"{url}: HTTP {response.status_code} - {description}")
            except requests.exceptions.RequestException as e:
                print_error(f"{url}: Failed - {description} ({e})")
                all_connected = False
        
        self.validation_results['network_connectivity'] = all_connected
        return all_connected
    
    def validate_discord_configuration(self) -> bool:
        """Validate Discord configuration"""
        print_header("Validating Discord Configuration")
        
        bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
        channel_id = os.environ.get('CHANNEL_ID')
        
        if not all([bot_token, webhook_url, channel_id]):
            print_error("Missing Discord credentials")
            self.validation_results['discord_config'] = False
            return False
        
        all_valid = True
        
        # Validate bot token format
        print_info("Validating Discord bot token format:")
        if bot_token.startswith(('MTA', 'MTQ', 'OTA')):
            print_success("Bot token format appears valid")
        else:
            print_warning("Bot token format may be invalid")
            self.warnings.append("Discord bot token format appears unusual")
        
        # Validate webhook URL format
        print_info("Validating webhook URL format:")
        if webhook_url.startswith('https://discord.com/api/webhooks/') and len(webhook_url) > 60:
            webhook_parts = webhook_url.split('/')
            if len(webhook_parts) >= 7:
                webhook_id = webhook_parts[-2]
                webhook_token = webhook_parts[-1]
                if webhook_id.isdigit() and len(webhook_token) > 50:
                    print_success("Webhook URL format is valid")
                else:
                    print_warning("Webhook URL components may be invalid")
                    self.warnings.append("Discord webhook URL format appears unusual")
            else:
                print_error("Webhook URL format is invalid")
                all_valid = False
        else:
            print_error("Webhook URL format is invalid")
            all_valid = False
        
        # Validate channel ID format
        print_info("Validating channel ID format:")
        try:
            channel_id_int = int(channel_id)
            if channel_id_int > 0:
                print_success(f"Channel ID is valid: {channel_id}")
            else:
                print_error("Channel ID must be positive")
                all_valid = False
        except ValueError:
            print_error("Channel ID must be a valid integer")
            all_valid = False
        
        self.validation_results['discord_config'] = all_valid
        return all_valid
    
    def validate_gemini_configuration(self) -> bool:
        """Validate Gemini API configuration"""
        print_header("Validating Gemini API Configuration")
        
        api_key = os.environ.get('GEMINI_API_KEY')
        
        if not api_key:
            print_error("GEMINI_API_KEY not found")
            self.validation_results['gemini_config'] = False
            return False
        
        # Validate API key format
        print_info("Validating Gemini API key format:")
        if api_key.startswith('AIza') and len(api_key) > 30:
            print_success("Gemini API key format appears valid")
        else:
            print_warning("Gemini API key format may be invalid")
            self.warnings.append("Gemini API key format appears unusual")
        
        # Test API access (lightweight test)
        print_info("Testing Gemini API access:")
        try:
            genai.configure(api_key=api_key)
            models = list(genai.list_models())
            if models:
                print_success(f"Gemini API access OK - {len(models)} models available")
            else:
                print_warning("Gemini API accessible but no models found")
                self.warnings.append("No Gemini models available")
            
            self.validation_results['gemini_config'] = True
            return True
            
        except Exception as e:
            print_error(f"Gemini API access failed: {e}")
            self.critical_issues.append("Cannot access Gemini API")
            self.validation_results['gemini_config'] = False
            return False
    
    def validate_feeds_configuration(self) -> bool:
        """Validate RSS feeds configuration"""
        print_header("Validating RSS Feeds Configuration")
        
        feeds_file = Path("feeds.txt")
        if not feeds_file.exists():
            print_error("feeds.txt not found")
            self.critical_issues.append("feeds.txt file missing")
            self.validation_results['feeds_config'] = False
            return False
        
        try:
            with open(feeds_file, 'r') as f:
                lines = f.readlines()
            
            feeds = [line.strip() for line in lines if line.strip() and not line.startswith('#')]
            
            if not feeds:
                print_error("No feeds found in feeds.txt")
                self.critical_issues.append("feeds.txt contains no valid feeds")
                self.validation_results['feeds_config'] = False
                return False
            
            print_success(f"Found {len(feeds)} feeds in feeds.txt")
            
            # Validate first few feed URLs
            print_info("Validating feed URL formats:")
            valid_feeds = 0
            
            for i, feed_url in enumerate(feeds[:5], 1):
                if feed_url.startswith(('http://', 'https://')):
                    print_success(f"Feed {i}: Valid URL format")
                    valid_feeds += 1
                else:
                    print_warning(f"Feed {i}: Invalid URL format - {feed_url}")
            
            if valid_feeds > 0:
                print_success(f"{valid_feeds} feeds have valid URL formats")
                self.validation_results['feeds_config'] = True
                return True
            else:
                print_error("No feeds have valid URL formats")
                self.critical_issues.append("All feed URLs have invalid formats")
                self.validation_results['feeds_config'] = False
                return False
                
        except Exception as e:
            print_error(f"Error reading feeds.txt: {e}")
            self.critical_issues.append(f"Cannot read feeds.txt: {e}")
            self.validation_results['feeds_config'] = False
            return False
    
    def validate_bot_modules(self) -> bool:
        """Validate bot modules can be imported"""
        print_header("Validating Bot Modules")
        
        bot_modules = [
            ('bot.main', 'Main bot module'),
            ('bot.config', 'Configuration module'),
            ('bot.parser', 'Feed parser module'),
            ('bot.formatter', 'Content formatter module'),
            ('bot.gemini_client', 'Gemini AI client module'),
            ('bot.dispatcher', 'Discord dispatcher module'),
            ('bot.facebook_downloader', 'Facebook downloader module'),
            ('bot.avatar_cache', 'Avatar cache module')
        ]
        
        all_importable = True
        
        for module_name, description in bot_modules:
            try:
                __import__(module_name)
                print_success(f"{module_name}: Importable - {description}")
            except ImportError as e:
                print_error(f"{module_name}: Import failed - {description} ({e})")
                self.critical_issues.append(f"Cannot import {module_name}")
                all_importable = False
            except Exception as e:
                print_warning(f"{module_name}: Import warning - {e}")
        
        self.validation_results['bot_modules'] = all_importable
        return all_importable
    
    def generate_recommendations(self):
        """Generate recommendations based on validation results"""
        print_header("Generating Recommendations")
        
        # Performance recommendations
        max_age_hours = os.environ.get('MAX_AGE_HOURS', '36')
        try:
            age_hours = int(max_age_hours)
            if age_hours > 48:
                self.recommendations.append(f"Consider reducing MAX_AGE_HOURS from {age_hours} to 24-48 for better performance")
            elif age_hours < 12:
                self.recommendations.append(f"MAX_AGE_HOURS of {age_hours} is quite low - you might miss content")
        except ValueError:
            pass
        
        # Security recommendations
        if os.environ.get('ADMIN_PASS') == 'whatever they say bro':
            self.recommendations.append("Change the default ADMIN_PASS to a secure password")
        
        # Configuration recommendations
        if not os.environ.get('GLOBAL_FALLBACK_CHANNEL_ID'):
            self.recommendations.append("Consider setting GLOBAL_FALLBACK_CHANNEL_ID for better error handling")
        
        if not os.environ.get('R2_BUCKET'):
            self.recommendations.append("Consider configuring Cloudflare R2 for media storage")
        
        # Display recommendations
        if self.recommendations:
            print_info("Configuration recommendations:")
            for i, recommendation in enumerate(self.recommendations, 1):
                print_info(f"  {i}. {recommendation}")
        else:
            print_success("No additional recommendations at this time")
    
    def print_validation_summary(self):
        """Print a comprehensive validation summary"""
        print_header("Environment Validation Summary")
        
        total_validations = len(self.validation_results)
        passed_validations = sum(self.validation_results.values())
        
        print(f"\n{Colors.BOLD}Results: {passed_validations}/{total_validations} validations passed{Colors.END}\n")
        
        validation_descriptions = {
            'required_files': 'Required Files',
            'environment_variables': 'Environment Variables',
            'file_permissions': 'File Permissions',
            'python_dependencies': 'Python Dependencies',
            'network_connectivity': 'Network Connectivity',
            'discord_config': 'Discord Configuration',
            'gemini_config': 'Gemini API Configuration',
            'feeds_config': 'RSS Feeds Configuration',
            'bot_modules': 'Bot Modules'
        }
        
        for test_name, passed in self.validation_results.items():
            description = validation_descriptions.get(test_name, test_name)
            status = "✅ PASS" if passed else "❌ FAIL"
            color = Colors.GREEN if passed else Colors.RED
            print(f"{color}{status}{Colors.END} {description}")
        
        # Show critical issues
        if self.critical_issues:
            print(f"\n{Colors.BOLD}{Colors.RED}Critical Issues:{Colors.END}")
            for issue in self.critical_issues:
                print(f"{Colors.RED}  • {issue}{Colors.END}")
        
        # Show warnings
        if self.warnings:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}Warnings:{Colors.END}")
            for warning in self.warnings:
                print(f"{Colors.YELLOW}  • {warning}{Colors.END}")
        
        # Final assessment
        if passed_validations == total_validations and not self.critical_issues:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 Environment validation passed! Your bot is ready to run.{Colors.END}")
        elif self.critical_issues:
            print(f"\n{Colors.BOLD}{Colors.RED}❌ Critical issues must be resolved before running the bot.{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}⚠️  Some validations failed. Review the issues above.{Colors.END}")

def main():
    """Main validation function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║             HANU FEEDBOT ENVIRONMENT VALIDATION             ║")
    print("║              Comprehensive Configuration Check              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    validator = EnvironmentValidator()
    
    # Run all validations
    validator.validate_required_files()
    validator.validate_environment_variables()
    validator.validate_file_permissions()
    validator.validate_python_dependencies()
    validator.validate_network_connectivity()
    validator.validate_discord_configuration()
    validator.validate_gemini_configuration()
    validator.validate_feeds_configuration()
    validator.validate_bot_modules()
    
    # Generate recommendations
    validator.generate_recommendations()
    
    # Print summary
    validator.print_validation_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Validation interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error during validation: {e}{Colors.END}")
