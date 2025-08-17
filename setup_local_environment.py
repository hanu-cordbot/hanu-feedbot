#!/usr/bin/env python3
"""
HANU Feedbot - Local Environment Setup Script
============================================

This script performs a comprehensive setup and validation of the local environment
for the HANU Discord RSS feedbot. It checks all dependencies, validates configurations,
and prepares the environment for testing and development.
"""

import os
import sys
import subprocess
import json
import platform
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import tempfile

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

def check_python_version() -> bool:
    """Check if Python version is 3.8 or higher"""
    print_header("Checking Python Environment")
    
    version = sys.version_info
    print_info(f"Python version: {version.major}.{version.minor}.{version.micro}")
    print_info(f"Python executable: {sys.executable}")
    print_info(f"Platform: {platform.platform()}")
    
    if version.major == 3 and version.minor >= 8:
        print_success("Python version is compatible (3.8+)")
        return True
    else:
        print_error(f"Python 3.8+ required, found {version.major}.{version.minor}")
        return False

def check_pip_availability() -> bool:
    """Check if pip is available"""
    try:
        import pip
        result = subprocess.run([sys.executable, "-m", "pip", "--version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print_success(f"pip is available: {result.stdout.strip()}")
            return True
        else:
            print_error("pip is not working properly")
            return False
    except Exception as e:
        print_error(f"pip is not available: {e}")
        return False

def install_dependencies() -> bool:
    """Install packages from requirements.txt"""
    print_header("Installing Dependencies")
    
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print_error("requirements.txt not found!")
        return False
    
    print_info("Installing packages from requirements.txt...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print_success("All dependencies installed successfully")
            print_info("Installed packages:")
            # Show installed packages
            pkg_result = subprocess.run([
                sys.executable, "-m", "pip", "list"
            ], capture_output=True, text=True, timeout=30)
            
            if pkg_result.returncode == 0:
                # Parse and show relevant packages
                lines = pkg_result.stdout.strip().split('\n')[2:]  # Skip header
                relevant_packages = []
                with open("requirements.txt", "r") as f:
                    required = [line.strip().split('>=')[0].split('==')[0].lower() 
                              for line in f if line.strip() and not line.startswith('#')]
                
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            pkg_name = parts[0].lower()
                            if pkg_name in required:
                                print(f"  • {parts[0]} {parts[1]}")
                                relevant_packages.append(pkg_name)
                
                missing = set(required) - set(relevant_packages)
                if missing:
                    print_warning(f"Some packages may not be installed: {', '.join(missing)}")
            
            return True
        else:
            print_error("Failed to install dependencies")
            print(f"Error output: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print_error("Installation timed out after 5 minutes")
        return False
    except Exception as e:
        print_error(f"Installation failed: {e}")
        return False

def check_required_files() -> bool:
    """Check if all required files exist"""
    print_header("Checking Required Files")
    
    required_files = [
        ".env",
        "requirements.txt", 
        "feeds.txt",
        "cron_worker.py",
        "bot/main.py",
        "bot/config.py",
        "bot/parser.py",
        "bot/formatter.py",
        "bot/gemini_client.py",
        "bot/facebook_downloader.py",
        "bot/dispatcher.py"
    ]
    
    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print_success(f"Found: {file_path}")
        else:
            print_error(f"Missing: {file_path}")
            all_exist = False
    
    return all_exist

def validate_env_file() -> Tuple[bool, Dict[str, str]]:
    """Validate .env file and return environment variables"""
    print_header("Validating Environment Configuration")
    
    env_file = Path(".env")
    if not env_file.exists():
        print_error(".env file not found!")
        return False, {}
    
    # Load environment variables
    env_vars = {}
    try:
        with open(".env", "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
                    else:
                        print_warning(f"Line {line_num}: Invalid format: {line}")
    except Exception as e:
        print_error(f"Failed to read .env file: {e}")
        return False, {}
    
    # Required environment variables
    required_vars = {
        'DISCORD_BOT_TOKEN': 'Discord bot token',
        'DISCORD_WEBHOOK_URL': 'Discord webhook URL', 
        'CHANNEL_ID': 'Discord channel ID',
        'GEMINI_API_KEY': 'Google Gemini API key',
        'MAX_AGE_HOURS': 'Maximum age for posts (hours)',
    }
    
    optional_vars = {
        'GLOBAL_FALLBACK_CHANNEL_ID': 'Fallback channel ID',
        'R2_BUCKET': 'Cloudflare R2 bucket name',
        'R2_ACCESS_KEY_ID': 'R2 access key',
        'R2_SECRET_ACCESS_KEY': 'R2 secret key',
        'YT_DLP_COOKIES': 'YouTube-DL cookies file',
        'ADMIN_PASS': 'Admin password',
    }
    
    all_valid = True
    
    # Check required variables
    print_info("Checking required environment variables:")
    for var, description in required_vars.items():
        if var in env_vars and env_vars[var]:
            # Mask sensitive values
            if 'TOKEN' in var or 'KEY' in var or 'SECRET' in var:
                masked_value = env_vars[var][:8] + '...' + env_vars[var][-4:] if len(env_vars[var]) > 12 else '***'
                print_success(f"{var}: {masked_value} ({description})")
            else:
                print_success(f"{var}: {env_vars[var]} ({description})")
        else:
            print_error(f"{var}: Missing or empty ({description})")
            all_valid = False
    
    # Check optional variables
    print_info("\nChecking optional environment variables:")
    for var, description in optional_vars.items():
        if var in env_vars and env_vars[var]:
            if 'SECRET' in var or 'KEY' in var or 'PASS' in var:
                masked_value = env_vars[var][:4] + '...' + env_vars[var][-2:] if len(env_vars[var]) > 6 else '***'
                print_success(f"{var}: {masked_value} ({description})")
            else:
                print_success(f"{var}: {env_vars[var]} ({description})")
        else:
            print_warning(f"{var}: Not set ({description})")
    
    # Validate specific format requirements
    print_info("\nValidating format requirements:")
    
    # Channel ID should be numeric
    if 'CHANNEL_ID' in env_vars:
        try:
            int(env_vars['CHANNEL_ID'])
            print_success("CHANNEL_ID is a valid integer")
        except ValueError:
            print_error("CHANNEL_ID must be a valid integer")
            all_valid = False
    
    # MAX_AGE_HOURS should be numeric
    if 'MAX_AGE_HOURS' in env_vars:
        try:
            hours = int(env_vars['MAX_AGE_HOURS'])
            if hours > 0:
                print_success(f"MAX_AGE_HOURS is valid: {hours} hours")
            else:
                print_error("MAX_AGE_HOURS must be positive")
                all_valid = False
        except ValueError:
            print_error("MAX_AGE_HOURS must be a valid integer")
            all_valid = False
    
    # Discord webhook URL format
    if 'DISCORD_WEBHOOK_URL' in env_vars:
        webhook_url = env_vars['DISCORD_WEBHOOK_URL']
        if webhook_url.startswith('https://discord.com/api/webhooks/') and len(webhook_url) > 50:
            print_success("Discord webhook URL format appears valid")
        else:
            print_error("Discord webhook URL format may be invalid")
            all_valid = False
    
    return all_valid, env_vars

def check_file_permissions() -> bool:
    """Check read/write permissions for state files"""
    print_header("Checking File Permissions")
    
    # State files that need read/write access
    state_files = ['seen.json', 'feed_map.json', 'avatar_cache.json', 'groups.json', 'channels.json']
    temp_test_file = 'temp_permission_test.txt'
    
    all_good = True
    
    # Test write permission in current directory
    try:
        with open(temp_test_file, 'w') as f:
            f.write('test')
        os.remove(temp_test_file)
        print_success("Write permission in current directory: OK")
    except Exception as e:
        print_error(f"Cannot write to current directory: {e}")
        all_good = False
    
    # Check state files
    for file_path in state_files:
        path = Path(file_path)
        if path.exists():
            try:
                # Test read
                with open(path, 'r') as f:
                    f.read(1)
                print_success(f"Read access to {file_path}: OK")
                
                # Test write (append mode to avoid corrupting data)
                with open(path, 'a') as f:
                    pass
                print_success(f"Write access to {file_path}: OK")
                
            except Exception as e:
                print_error(f"Permission issue with {file_path}: {e}")
                all_good = False
        else:
            print_warning(f"{file_path} does not exist (will be created)")
    
    return all_good

def create_missing_state_files() -> bool:
    """Create empty state files if they don't exist"""
    print_header("Creating Missing State Files")
    
    state_files_defaults = {
        'seen.json': '{}',
        'feed_map.json': '{}',
        'avatar_cache.json': '{}', 
        'groups.json': '{}',
        'channels.json': '{}',
        'details_threads.json': '{}'
    }
    
    created_any = False
    for file_path, default_content in state_files_defaults.items():
        path = Path(file_path)
        if not path.exists():
            try:
                with open(path, 'w') as f:
                    f.write(default_content)
                print_success(f"Created {file_path}")
                created_any = True
            except Exception as e:
                print_error(f"Failed to create {file_path}: {e}")
                return False
        else:
            print_info(f"{file_path} already exists")
    
    if not created_any:
        print_success("All state files already exist")
    
    return True

def check_importable_modules() -> bool:
    """Check if all required Python modules can be imported"""
    print_header("Checking Python Module Imports")
    
    required_modules = [
        'feedparser',
        'requests', 
        'discord',
        'google.generativeai',
        'pendulum',
        'aiohttp',
        'beautifulsoup4',
        'flask',
        'celery',
        'redis',
        'boto3',
        'pytest',
        'dotenv'
    ]
    
    # Special cases for modules with different import names
    import_mapping = {
        'beautifulsoup4': 'bs4',
        'google.generativeai': 'google.generativeai',
        'python-dotenv': 'dotenv'
    }
    
    all_imported = True
    for module in required_modules:
        import_name = import_mapping.get(module, module)
        try:
            __import__(import_name)
            print_success(f"✓ {module} ({import_name})")
        except ImportError as e:
            print_error(f"✗ {module} ({import_name}): {e}")
            all_imported = False
        except Exception as e:
            print_warning(f"? {module} ({import_name}): {e}")
    
    return all_imported

def check_system_dependencies() -> bool:
    """Check for system-level dependencies"""
    print_header("Checking System Dependencies")
    
    dependencies = {
        'yt-dlp': 'YouTube video downloader',
        'git': 'Version control system'
    }
    
    all_available = True
    for cmd, description in dependencies.items():
        try:
            result = subprocess.run([cmd, '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                print_success(f"{cmd}: {version_line}")
            else:
                print_error(f"{cmd}: Command failed")
                all_available = False
        except FileNotFoundError:
            print_error(f"{cmd}: Not found in PATH ({description})")
            all_available = False
        except subprocess.TimeoutExpired:
            print_error(f"{cmd}: Command timed out")
            all_available = False
        except Exception as e:
            print_error(f"{cmd}: Error checking - {e}")
            all_available = False
    
    return all_available

def test_network_connectivity() -> bool:
    """Test basic network connectivity"""
    print_header("Testing Network Connectivity")
    
    test_urls = [
        ('https://www.google.com', 'General internet connectivity'),
        ('https://discord.com', 'Discord API accessibility'),
        ('https://generativelanguage.googleapis.com', 'Google Gemini API accessibility'),
        ('https://fetchrss.com', 'RSS feed service accessibility')
    ]
    
    all_connected = True
    for url, description in test_urls:
        try:
            import requests
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print_success(f"{description}: OK ({url})")
            else:
                print_warning(f"{description}: HTTP {response.status_code} ({url})")
        except requests.exceptions.Timeout:
            print_error(f"{description}: Timeout ({url})")
            all_connected = False
        except requests.exceptions.ConnectionError:
            print_error(f"{description}: Connection failed ({url})")
            all_connected = False
        except Exception as e:
            print_error(f"{description}: Error - {e}")
            all_connected = False
    
    return all_connected

def generate_setup_summary(results: Dict[str, bool]) -> None:
    """Generate a summary of the setup results"""
    print_header("Setup Summary")
    
    total_checks = len(results)
    passed_checks = sum(results.values())
    
    print(f"\n{Colors.BOLD}Results: {passed_checks}/{total_checks} checks passed{Colors.END}\n")
    
    for check_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        color = Colors.GREEN if passed else Colors.RED
        print(f"{color}{status}{Colors.END} {check_name}")
    
    if passed_checks == total_checks:
        print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All checks passed! Your environment is ready for testing.{Colors.END}")
        print(f"\n{Colors.CYAN}Next steps:{Colors.END}")
        print("1. Run test_discord_connection.py to test Discord integration")
        print("2. Run test_gemini_api.py to test Gemini AI integration") 
        print("3. Run test_feed_processing.py to test RSS feed processing")
        print("4. Run run_local_tests.py to run all tests together")
    else:
        print(f"\n{Colors.BOLD}{Colors.RED}⚠️  Some checks failed. Please fix the issues above before proceeding.{Colors.END}")
        print(f"\n{Colors.CYAN}Troubleshooting tips:{Colors.END}")
        if not results.get('Python Environment'):
            print("• Install Python 3.8 or higher")
        if not results.get('Dependencies'):
            print("• Run: pip install -r requirements.txt")
        if not results.get('Environment Configuration'):
            print("• Check your .env file and ensure all required variables are set")
        if not results.get('File Permissions'):
            print("• Ensure you have read/write permissions in the current directory")
        if not results.get('Network Connectivity'):
            print("• Check your internet connection and firewall settings")

def main():
    """Main setup function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                    HANU FEEDBOT SETUP                        ║")
    print("║              Local Environment Configuration                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    # Store results for summary
    results = {}
    
    # Check Python environment
    results['Python Environment'] = check_python_version() and check_pip_availability()
    
    # Check required files
    results['Required Files'] = check_required_files()
    
    # Install dependencies  
    results['Dependencies'] = install_dependencies()
    
    # Validate environment configuration
    env_valid, env_vars = validate_env_file()
    results['Environment Configuration'] = env_valid
    
    # Check file permissions
    results['File Permissions'] = check_file_permissions()
    
    # Create missing state files
    results['State Files'] = create_missing_state_files()
    
    # Check module imports
    results['Module Imports'] = check_importable_modules()
    
    # Check system dependencies
    results['System Dependencies'] = check_system_dependencies()
    
    # Test network connectivity
    results['Network Connectivity'] = test_network_connectivity()
    
    # Generate summary
    generate_setup_summary(results)

if __name__ == "__main__":
    main()
