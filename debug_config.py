#!/usr/bin/env python3
"""
HANU Feedbot - Debug Configuration
=================================

This script provides comprehensive debugging information about the bot's
configuration, environment, and system state for troubleshooting.
"""

import os
import sys
import json
import platform
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional

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

def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
    """Mask sensitive values for safe display"""
    if len(value) <= show_chars * 2:
        return '*' * len(value)
    return value[:show_chars] + '...' + value[-show_chars:]

class DebugConfigurator:
    def __init__(self):
        self.debug_info = {}
        self.issues_found = []
        self.recommendations = []
    
    def show_system_information(self):
        """Display system information"""
        print_header("System Information")
        
        system_info = {
            'Platform': platform.platform(),
            'System': platform.system(),
            'Machine': platform.machine(),
            'Processor': platform.processor(),
            'Python Version': platform.python_version(),
            'Python Executable': sys.executable,
            'Python Path': sys.path[:3] + ['...'] if len(sys.path) > 3 else sys.path,
            'Current Working Directory': os.getcwd(),
            'Script Location': __file__,
            'Environment PATH': os.environ.get('PATH', '').split(os.pathsep)[:5] + ['...']
        }
        
        for key, value in system_info.items():
            if isinstance(value, list):
                print_info(f"{key}:")
                for item in value:
                    print(f"    {item}")
            else:
                print_info(f"{key}: {value}")
        
        self.debug_info['system'] = system_info
    
    def show_environment_variables(self):
        """Display environment variables (masked)"""
        print_header("Environment Variables")
        
        # Group environment variables
        bot_vars = {}
        discord_vars = {}
        gemini_vars = {}
        r2_vars = {}
        other_vars = {}
        
        for key, value in os.environ.items():
            if 'discord' in key.lower() or 'bot' in key.lower():
                discord_vars[key] = value
            elif 'gemini' in key.lower() or 'ai' in key.lower():
                gemini_vars[key] = value
            elif 'r2' in key.lower() or 'cloudflare' in key.lower():
                r2_vars[key] = value
            elif key.startswith(('HANU_', 'BOT_', 'FEED_', 'CHANNEL_', 'MAX_', 'ADMIN_', 'JOB_')):
                bot_vars[key] = value
            elif not key.startswith(('PATH', 'HOME', 'USER', 'TEMP', 'TMP', 'SYSTEM', 'WINDOWS', 'PROGRAM')):
                other_vars[key] = value
        
        # Display grouped variables
        var_groups = [
            ("Bot Configuration", bot_vars),
            ("Discord Configuration", discord_vars),
            ("Gemini AI Configuration", gemini_vars),
            ("Cloudflare R2 Configuration", r2_vars),
            ("Other Environment Variables", other_vars)
        ]
        
        sensitive_keywords = ['token', 'key', 'secret', 'pass', 'auth', 'credential']
        
        for group_name, variables in var_groups:
            if variables:
                print_info(f"\n{group_name}:")
                for key, value in sorted(variables.items()):
                    is_sensitive = any(keyword in key.lower() for keyword in sensitive_keywords)
                    
                    if is_sensitive:
                        display_value = mask_sensitive_value(value)
                    else:
                        display_value = value
                    
                    print(f"    {key}: {display_value}")
        
        self.debug_info['environment'] = {
            'bot_vars': list(bot_vars.keys()),
            'discord_vars': list(discord_vars.keys()),
            'gemini_vars': list(gemini_vars.keys()),
            'r2_vars': list(r2_vars.keys()),
            'total_vars': len(os.environ)
        }
    
    def show_file_paths(self):
        """Display file paths and accessibility"""
        print_header("File Paths & Accessibility")
        
        # Important files and directories
        important_paths = {
            'Config Files': ['.env', 'feeds.txt', 'requirements.txt'],
            'State Files': ['seen.json', 'feed_map.json', 'avatar_cache.json', 'groups.json', 'channels.json'],
            'Bot Modules': ['bot/__init__.py', 'bot/main.py', 'bot/config.py', 'bot/parser.py', 'bot/formatter.py'],
            'Scripts': ['cron_worker.py', 'setup_local_environment.py', 'run_local_tests.py'],
            'Logs': ['test_logs/', 'bot.lock']
        }
        
        for category, paths in important_paths.items():
            print_info(f"\n{category}:")
            for path_str in paths:
                path = Path(path_str)
                
                if path.exists():
                    if path.is_file():
                        size = path.stat().st_size
                        modified = path.stat().st_mtime
                        print_success(f"  {path}: {size} bytes, modified {modified}")
                    else:
                        items = len(list(path.iterdir())) if path.is_dir() else 0
                        print_success(f"  {path}/: {items} items")
                else:
                    print_warning(f"  {path}: Not found")
        
        # Test current directory permissions
        print_info("\nDirectory Permissions:")
        current_dir = Path('.')
        
        try:
            test_file = current_dir / 'temp_debug_test.txt'
            test_file.write_text('test')
            test_file.unlink()
            print_success("Current directory: Read/Write OK")
        except Exception as e:
            print_error(f"Current directory: Permission issue - {e}")
            self.issues_found.append(f"Directory permission issue: {e}")
    
    def show_dependency_versions(self):
        """Display installed package versions"""
        print_header("Python Dependencies")
        
        # Critical dependencies
        critical_deps = [
            'feedparser', 'requests', 'discord', 'google.generativeai',
            'pendulum', 'aiohttp', 'beautifulsoup4', 'dotenv'
        ]
        
        # Optional dependencies
        optional_deps = [
            'flask', 'celery', 'redis', 'boto3', 'pytest', 'psutil'
        ]
        
        print_info("Critical Dependencies:")
        for dep in critical_deps:
            try:
                if dep == 'beautifulsoup4':
                    import bs4
                    module = bs4
                    display_name = 'beautifulsoup4 (bs4)'
                elif dep == 'google.generativeai':
                    import google.generativeai
                    module = google.generativeai
                    display_name = 'google.generativeai'
                elif dep == 'dotenv':
                    import dotenv
                    module = dotenv
                    display_name = 'python-dotenv'
                else:
                    module = __import__(dep)
                    display_name = dep
                
                version = getattr(module, '__version__', 'unknown')
                location = getattr(module, '__file__', 'unknown')
                print_success(f"  {display_name}: v{version}")
                print(f"    Location: {location}")
                
            except ImportError as e:
                print_error(f"  {dep}: Not installed - {e}")
                self.issues_found.append(f"Missing dependency: {dep}")
            except Exception as e:
                print_warning(f"  {dep}: Import error - {e}")
        
        print_info("\nOptional Dependencies:")
        for dep in optional_deps:
            try:
                module = __import__(dep)
                version = getattr(module, '__version__', 'unknown')
                print_success(f"  {dep}: v{version}")
            except ImportError:
                print_info(f"  {dep}: Not installed (optional)")
            except Exception as e:
                print_warning(f"  {dep}: Import error - {e}")
    
    def show_bot_configuration(self):
        """Display bot-specific configuration"""
        print_header("Bot Configuration Analysis")
        
        # Import bot configuration if possible
        try:
            sys.path.append('bot')
            from bot.config import *
            print_success("Bot configuration module imported successfully")
            
            # Show configuration values
            config_vars = [var for var in dir() if not var.startswith('_') and var.isupper()]
            if config_vars:
                print_info("Configuration variables:")
                for var in config_vars:
                    try:
                        value = eval(var)
                        if isinstance(value, (str, int, float, bool)):
                            print(f"  {var}: {value}")
                        else:
                            print(f"  {var}: {type(value).__name__}")
                    except:
                        print(f"  {var}: <unable to evaluate>")
            
        except ImportError as e:
            print_warning(f"Could not import bot configuration: {e}")
        except Exception as e:
            print_error(f"Error accessing bot configuration: {e}")
        
        # Check configuration consistency
        print_info("\nConfiguration Validation:")
        
        # Check MAX_AGE_HOURS
        max_age = os.environ.get('MAX_AGE_HOURS')
        if max_age:
            try:
                age_int = int(max_age)
                if 1 <= age_int <= 168:  # 1 hour to 1 week
                    print_success(f"MAX_AGE_HOURS: {age_int} (reasonable)")
                else:
                    print_warning(f"MAX_AGE_HOURS: {age_int} (unusual value)")
                    self.recommendations.append(f"Consider adjusting MAX_AGE_HOURS from {age_int} to 24-48")
            except ValueError:
                print_error(f"MAX_AGE_HOURS: Invalid value '{max_age}'")
                self.issues_found.append("MAX_AGE_HOURS is not a valid integer")
        
        # Check Discord configuration
        bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
        channel_id = os.environ.get('CHANNEL_ID')
        
        if bot_token and webhook_url:
            print_success("Both bot token and webhook URL configured")
        elif bot_token:
            print_warning("Only bot token configured (no webhook)")
        elif webhook_url:
            print_warning("Only webhook URL configured (no bot token)")
        else:
            print_error("Neither bot token nor webhook URL configured")
            self.issues_found.append("Discord credentials not configured")
    
    def test_discord_bot_info(self):
        """Test Discord bot information"""
        print_header("Discord Bot Information")
        
        bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        if not bot_token:
            print_warning("No Discord bot token available")
            return
        
        try:
            # Create a simple client to get bot info
            import asyncio
            import aiohttp
            
            async def get_bot_info():
                headers = {'Authorization': f'Bot {bot_token}'}
                
                async with aiohttp.ClientSession() as session:
                    # Get bot user info
                    async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
                        if resp.status == 200:
                            bot_info = await resp.json()
                            print_success(f"Bot User: {bot_info.get('username')}#{bot_info.get('discriminator')}")
                            print_info(f"Bot ID: {bot_info.get('id')}")
                            print_info(f"Bot Avatar: {bot_info.get('avatar', 'None')}")
                            print_info(f"Bot Verified: {bot_info.get('verified', False)}")
                            
                            # Get guilds
                            async with session.get('https://discord.com/api/users/@me/guilds', headers=headers) as guild_resp:
                                if guild_resp.status == 200:
                                    guilds = await guild_resp.json()
                                    print_success(f"Bot is in {len(guilds)} guilds:")
                                    for guild in guilds[:5]:  # Show first 5
                                        print(f"  • {guild.get('name')} (ID: {guild.get('id')})")
                                    if len(guilds) > 5:
                                        print(f"  ... and {len(guilds) - 5} more")
                                else:
                                    print_warning(f"Could not fetch guilds: HTTP {guild_resp.status}")
                        else:
                            print_error(f"Could not fetch bot info: HTTP {resp.status}")
                            if resp.status == 401:
                                self.issues_found.append("Discord bot token is invalid")
            
            # Run the async function
            asyncio.run(get_bot_info())
            
        except Exception as e:
            print_error(f"Error fetching Discord bot info: {e}")
    
    def test_import_capabilities(self):
        """Test importing various bot modules"""
        print_header("Bot Module Import Test")
        
        bot_modules = [
            ('bot.main', 'Main bot module'),
            ('bot.config', 'Configuration'),
            ('bot.parser', 'Feed parser'),
            ('bot.formatter', 'Content formatter'),
            ('bot.gemini_client', 'Gemini AI client'),
            ('bot.dispatcher', 'Discord dispatcher'),
            ('bot.facebook_downloader', 'Facebook downloader'),
            ('bot.avatar_cache', 'Avatar cache')
        ]
        
        successful_imports = 0
        
        for module_name, description in bot_modules:
            try:
                module = __import__(module_name, fromlist=[''])
                print_success(f"{module_name}: OK - {description}")
                
                # Show key functions/classes if possible
                attrs = [attr for attr in dir(module) if not attr.startswith('_')]
                if attrs:
                    key_attrs = [attr for attr in attrs if any(keyword in attr.lower() 
                                for keyword in ['main', 'run', 'process', 'handle', 'get', 'load', 'save'])][:3]
                    if key_attrs:
                        print(f"    Key functions: {', '.join(key_attrs)}")
                
                successful_imports += 1
                
            except ImportError as e:
                print_error(f"{module_name}: Import failed - {e}")
                self.issues_found.append(f"Cannot import {module_name}")
            except Exception as e:
                print_warning(f"{module_name}: Import warning - {e}")
        
        print_info(f"\nImport Summary: {successful_imports}/{len(bot_modules)} modules imported successfully")
    
    def show_channel_information(self):
        """Show Discord channel information"""
        print_header("Discord Channel Information")
        
        channel_id = os.environ.get('CHANNEL_ID')
        fallback_channel_id = os.environ.get('GLOBAL_FALLBACK_CHANNEL_ID')
        
        if channel_id:
            print_info(f"Primary Channel ID: {channel_id}")
            
            # Validate channel ID format
            try:
                channel_int = int(channel_id)
                if channel_int > 0:
                    print_success("Channel ID format is valid")
                    
                    # Estimate when this ID was created (Discord snowflake)
                    discord_epoch = 1420070400000  # Discord epoch
                    timestamp = ((channel_int >> 22) + discord_epoch) / 1000
                    from datetime import datetime
                    created_date = datetime.fromtimestamp(timestamp)
                    print_info(f"Channel ID created approximately: {created_date}")
                else:
                    print_error("Channel ID must be positive")
            except ValueError:
                print_error("Channel ID is not a valid integer")
        else:
            print_warning("No primary channel ID configured")
        
        if fallback_channel_id:
            print_info(f"Fallback Channel ID: {fallback_channel_id}")
        else:
            print_info("No fallback channel ID configured")
    
    def generate_debug_summary(self):
        """Generate summary of debug findings"""
        print_header("Debug Summary")
        
        print(f"\n{Colors.BOLD}Issues Found: {len(self.issues_found)}{Colors.END}")
        if self.issues_found:
            for i, issue in enumerate(self.issues_found, 1):
                print_error(f"{i}. {issue}")
        else:
            print_success("No critical issues found")
        
        print(f"\n{Colors.BOLD}Recommendations: {len(self.recommendations)}{Colors.END}")
        if self.recommendations:
            for i, rec in enumerate(self.recommendations, 1):
                print_info(f"{i}. {rec}")
        else:
            print_info("No specific recommendations at this time")
        
        # Generate debug report file
        debug_report = {
            'timestamp': str(datetime.now()),
            'system_info': self.debug_info,
            'issues_found': self.issues_found,
            'recommendations': self.recommendations,
            'environment_summary': {
                'discord_configured': bool(os.environ.get('DISCORD_BOT_TOKEN') and os.environ.get('DISCORD_WEBHOOK_URL')),
                'gemini_configured': bool(os.environ.get('GEMINI_API_KEY')),
                'feeds_file_exists': Path('feeds.txt').exists(),
                'bot_modules_exist': Path('bot').exists() and Path('bot/main.py').exists()
            }
        }
        
        report_file = Path('debug_report.json')
        with open(report_file, 'w') as f:
            json.dump(debug_report, f, indent=2, default=str)
        
        print_info(f"\nDebug report saved to: {report_file}")

def main():
    """Main debug function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                HANU FEEDBOT DEBUG CONFIG                     ║")
    print("║              Configuration & Environment Debug              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    from datetime import datetime
    
    debugger = DebugConfigurator()
    
    # Run all debug checks
    debugger.show_system_information()
    debugger.show_environment_variables()
    debugger.show_file_paths()
    debugger.show_dependency_versions()
    debugger.show_bot_configuration()
    debugger.test_discord_bot_info()
    debugger.test_import_capabilities()
    debugger.show_channel_information()
    
    # Generate summary
    debugger.generate_debug_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Debug interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error during debug: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
