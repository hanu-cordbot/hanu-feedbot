#!/usr/bin/env python3
"""
HANU Feedbot - Local Test Runner
===============================

Master test runner that orchestrates all local testing scripts
and provides comprehensive validation of the bot environment.
"""

import os
import sys
import time
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

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
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")

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

class TestRunner:
    def __init__(self, args):
        self.args = args
        self.test_results = {}
        self.test_logs = {}
        self.start_time = time.time()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create logs directory
        self.logs_dir = Path("test_logs")
        self.logs_dir.mkdir(exist_ok=True)
    
    def run_test_script(self, script_name: str, description: str, timeout: int = 300) -> bool:
        """Run a test script and capture results"""
        print_header(f"Running {description}")
        
        script_path = Path(script_name)
        if not script_path.exists():
            print_error(f"Test script not found: {script_name}")
            self.test_results[script_name] = False
            return False
        
        log_file = self.logs_dir / f"{self.session_id}_{script_name.replace('.py', '.log')}"
        
        try:
            print_info(f"Executing: {script_name}")
            print_info(f"Timeout: {timeout} seconds")
            print_info(f"Log file: {log_file}")
            
            start_time = time.time()
            
            # Run the script
            result = subprocess.run(
                [sys.executable, script_name],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Path.cwd()
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Save log
            log_content = {
                'script': script_name,
                'description': description,
                'start_time': start_time,
                'end_time': end_time,
                'execution_time': execution_time,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
            with open(log_file, 'w') as f:
                json.dump(log_content, f, indent=2)
            
            self.test_logs[script_name] = log_content
            
            # Analyze results
            if result.returncode == 0:
                print_success(f"Completed successfully in {execution_time:.2f} seconds")
                
                # Look for success indicators in output
                if "tests passed" in result.stdout.lower() or "✅" in result.stdout:
                    success_count = result.stdout.lower().count("✅") or result.stdout.lower().count("pass")
                    print_info(f"Found {success_count} success indicators")
                
                self.test_results[script_name] = True
                return True
            else:
                print_error(f"Failed with exit code {result.returncode}")
                if result.stderr:
                    print_error(f"Error output: {result.stderr[:200]}...")
                
                self.test_results[script_name] = False
                return False
        
        except subprocess.TimeoutExpired:
            print_error(f"Test timed out after {timeout} seconds")
            self.test_results[script_name] = False
            return False
        except Exception as e:
            print_error(f"Error running test: {e}")
            self.test_results[script_name] = False
            return False
    
    def run_environment_setup(self) -> bool:
        """Run environment setup script"""
        if self.args.skip_setup:
            print_info("Skipping environment setup (--skip-setup flag)")
            return True
        
        return self.run_test_script(
            "setup_local_environment.py",
            "Environment Setup & Dependency Installation",
            timeout=600  # 10 minutes for installation
        )
    
    def run_environment_validation(self) -> bool:
        """Run environment validation script"""
        return self.run_test_script(
            "validate_environment.py",
            "Environment Configuration Validation",
            timeout=120
        )
    
    def run_discord_tests(self) -> bool:
        """Run Discord connection tests"""
        if self.args.skip_discord:
            print_info("Skipping Discord tests (--skip-discord flag)")
            return True
        
        return self.run_test_script(
            "test_discord_connection.py",
            "Discord Bot & Webhook Testing",
            timeout=180
        )
    
    def run_gemini_tests(self) -> bool:
        """Run Gemini API tests"""
        if self.args.skip_gemini:
            print_info("Skipping Gemini tests (--skip-gemini flag)")
            return True
        
        return self.run_test_script(
            "test_gemini_api.py",
            "Gemini AI API Testing",
            timeout=180
        )
    
    def run_feed_processing_tests(self) -> bool:
        """Run feed processing tests"""
        if self.args.skip_feeds:
            print_info("Skipping feed processing tests (--skip-feeds flag)")
            return True
        
        return self.run_test_script(
            "test_feed_processing.py",
            "RSS Feed Processing Testing",
            timeout=300
        )
    
    def run_cron_worker_tests(self) -> bool:
        """Run cron worker tests"""
        if self.args.skip_worker:
            print_info("Skipping cron worker tests (--skip-worker flag)")
            return True
        
        # Add dry run flag if specified
        script_name = "test_cron_worker_local.py"
        if not self.args.no_dry_run:
            # The script defaults to dry run mode
            return self.run_test_script(
                script_name,
                "Cron Worker Testing (Dry Run)",
                timeout=600
            )
        else:
            print_warning("Running cron worker tests in LIVE mode!")
            return self.run_test_script(
                script_name,
                "Cron Worker Testing (LIVE MODE)",
                timeout=600
            )
    
    def analyze_test_logs(self) -> Dict[str, Any]:
        """Analyze test logs for detailed results"""
        print_header("Analyzing Test Results")
        
        analysis = {
            'total_tests': len(self.test_results),
            'passed_tests': sum(self.test_results.values()),
            'failed_tests': len(self.test_results) - sum(self.test_results.values()),
            'total_execution_time': 0,
            'test_details': {},
            'issues_found': [],
            'recommendations': []
        }
        
        for script_name, log_data in self.test_logs.items():
            analysis['total_execution_time'] += log_data.get('execution_time', 0)
            
            # Analyze individual test output
            stdout = log_data.get('stdout', '')
            stderr = log_data.get('stderr', '')
            
            test_detail = {
                'passed': self.test_results.get(script_name, False),
                'execution_time': log_data.get('execution_time', 0),
                'return_code': log_data.get('return_code', -1),
                'success_count': stdout.lower().count('✅') + stdout.lower().count('pass'),
                'error_count': stdout.lower().count('❌') + stdout.lower().count('fail'),
                'warning_count': stdout.lower().count('⚠️') + stdout.lower().count('warning')
            }
            
            analysis['test_details'][script_name] = test_detail
            
            # Extract issues
            if stderr:
                analysis['issues_found'].append(f"{script_name}: {stderr[:100]}...")
            
            if test_detail['error_count'] > 0:
                analysis['issues_found'].append(f"{script_name}: Found {test_detail['error_count']} errors in output")
        
        # Generate recommendations
        if analysis['failed_tests'] > 0:
            analysis['recommendations'].append("Review failed test logs for specific issues")
        
        if analysis['total_execution_time'] > 1800:  # 30 minutes
            analysis['recommendations'].append("Tests took longer than expected - check system performance")
        
        return analysis
    
    def generate_test_report(self, analysis: Dict[str, Any]):
        """Generate a comprehensive test report"""
        print_header("Test Execution Report")
        
        # Summary statistics
        print(f"\n{Colors.BOLD}Test Execution Summary:{Colors.END}")
        print(f"  • Total tests run: {analysis['total_tests']}")
        print(f"  • Tests passed: {Colors.GREEN}{analysis['passed_tests']}{Colors.END}")
        print(f"  • Tests failed: {Colors.RED}{analysis['failed_tests']}{Colors.END}")
        print(f"  • Success rate: {analysis['passed_tests']/analysis['total_tests']*100:.1f}%")
        print(f"  • Total execution time: {analysis['total_execution_time']:.2f} seconds")
        print(f"  • Session ID: {self.session_id}")
        
        # Individual test results
        print(f"\n{Colors.BOLD}Individual Test Results:{Colors.END}")
        
        test_descriptions = {
            'setup_local_environment.py': 'Environment Setup',
            'validate_environment.py': 'Environment Validation',
            'test_discord_connection.py': 'Discord Integration',
            'test_gemini_api.py': 'Gemini AI Integration',
            'test_feed_processing.py': 'RSS Feed Processing',
            'test_cron_worker_local.py': 'Cron Worker Functionality'
        }
        
        for script_name, details in analysis['test_details'].items():
            description = test_descriptions.get(script_name, script_name)
            status = "✅ PASS" if details['passed'] else "❌ FAIL"
            color = Colors.GREEN if details['passed'] else Colors.RED
            
            print(f"{color}{status}{Colors.END} {description}")
            print(f"    Time: {details['execution_time']:.2f}s | "
                  f"Successes: {details['success_count']} | "
                  f"Errors: {details['error_count']} | "
                  f"Warnings: {details['warning_count']}")
        
        # Issues found
        if analysis['issues_found']:
            print(f"\n{Colors.BOLD}{Colors.RED}Issues Found:{Colors.END}")
            for issue in analysis['issues_found']:
                print(f"  • {issue}")
        
        # Recommendations
        if analysis['recommendations']:
            print(f"\n{Colors.BOLD}{Colors.CYAN}Recommendations:{Colors.END}")
            for recommendation in analysis['recommendations']:
                print(f"  • {recommendation}")
        
        # Log file locations
        print(f"\n{Colors.BOLD}Log Files:{Colors.END}")
        for log_file in self.logs_dir.glob(f"{self.session_id}_*.log"):
            print(f"  • {log_file}")
        
        # Final assessment
        if analysis['passed_tests'] == analysis['total_tests']:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All tests passed! Your HANU Feedbot is ready for production.{Colors.END}")
            print(f"\n{Colors.CYAN}Next steps:{Colors.END}")
            print("  1. Review any warnings in the test outputs")
            print("  2. Consider running a test post to Discord to verify end-to-end functionality")
            print("  3. Set up your production deployment (GitHub Actions, Railway, etc.)")
            print("  4. Monitor the first few runs in production")
        elif analysis['failed_tests'] <= 2:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}⚠️  Most tests passed with minor issues.{Colors.END}")
            print(f"\n{Colors.CYAN}Action items:{Colors.END}")
            print("  1. Review failed tests and address specific issues")
            print("  2. Re-run specific test scripts after fixes")
            print("  3. Consider proceeding with caution if issues are non-critical")
        else:
            print(f"\n{Colors.BOLD}{Colors.RED}❌ Multiple tests failed. Address issues before proceeding.{Colors.END}")
            print(f"\n{Colors.CYAN}Critical action items:{Colors.END}")
            print("  1. Fix all failed tests before proceeding")
            print("  2. Check environment configuration and credentials")
            print("  3. Verify all dependencies are properly installed")
            print("  4. Review log files for detailed error information")
        
        # Save report to file
        report_file = self.logs_dir / f"{self.session_id}_test_report.json"
        with open(report_file, 'w') as f:
            json.dump({
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis,
                'test_results': self.test_results,
                'args': vars(self.args)
            }, f, indent=2)
        
        print(f"\n{Colors.INFO}📄 Detailed report saved to: {report_file}{Colors.END}")
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"{Colors.BOLD}{Colors.PURPLE}")
        print("╔══════════════════════════════════════════════════════════════════════╗")
        print("║                    HANU FEEDBOT LOCAL TEST SUITE                    ║")
        print("║                  Comprehensive Testing & Validation                 ║")
        print("╚══════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.END}")
        
        print_info(f"Test session ID: {self.session_id}")
        print_info(f"Logs directory: {self.logs_dir}")
        
        # Show configuration
        print_info("\nTest configuration:")
        print_info(f"  • Skip setup: {self.args.skip_setup}")
        print_info(f"  • Skip Discord tests: {self.args.skip_discord}")
        print_info(f"  • Skip Gemini tests: {self.args.skip_gemini}")
        print_info(f"  • Skip feed tests: {self.args.skip_feeds}")
        print_info(f"  • Skip worker tests: {self.args.skip_worker}")
        print_info(f"  • Dry run mode: {not self.args.no_dry_run}")
        
        # Run tests in sequence
        tests = [
            ('Environment Setup', self.run_environment_setup),
            ('Environment Validation', self.run_environment_validation),
            ('Discord Tests', self.run_discord_tests),
            ('Gemini API Tests', self.run_gemini_tests),
            ('Feed Processing Tests', self.run_feed_processing_tests),
            ('Cron Worker Tests', self.run_cron_worker_tests)
        ]
        
        for test_name, test_func in tests:
            if self.args.interactive:
                response = input(f"\nRun {test_name}? (Y/n): ").strip().lower()
                if response in ['n', 'no']:
                    print_info(f"Skipping {test_name}")
                    continue
            
            success = test_func()
            
            if not success and self.args.stop_on_failure:
                print_error(f"Stopping due to failure in {test_name} (--stop-on-failure flag)")
                break
            
            # Small delay between tests
            time.sleep(1)
        
        # Analyze results and generate report
        analysis = self.analyze_test_logs()
        self.generate_test_report(analysis)

def create_sample_feeds_file():
    """Create sample feeds file for testing"""
    sample_feeds_content = """# Sample RSS Feeds for Testing
# These are reliable, publicly available feeds for testing purposes

# Technology News
https://feeds.feedburner.com/TechCrunch
https://www.wired.com/feed/rss
https://rss.cnn.com/rss/edition.rss

# General News  
https://feeds.bbci.co.uk/news/rss.xml
https://rss.reuters.com/reuters/topNews

# Development/Programming
https://github.blog/feed/
https://stackoverflow.blog/feed/

# Science
https://www.science.org/rss/news_current.xml

# Note: Replace these with your actual RSS feeds for production use
"""
    
    sample_file = Path("sample_feeds.txt")
    if not sample_file.exists():
        with open(sample_file, 'w') as f:
            f.write(sample_feeds_content)
        print_success(f"Created sample feeds file: {sample_file}")

def main():
    parser = argparse.ArgumentParser(
        description="HANU Feedbot Local Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_local_tests.py                    # Run all tests
  python run_local_tests.py --skip-setup       # Skip environment setup
  python run_local_tests.py --interactive      # Interactive mode
  python run_local_tests.py --skip-discord     # Skip Discord tests
  python run_local_tests.py --no-dry-run       # Run in live mode (dangerous!)
        """
    )
    
    parser.add_argument('--skip-setup', action='store_true',
                       help='Skip environment setup and dependency installation')
    parser.add_argument('--skip-discord', action='store_true',
                       help='Skip Discord connection tests')
    parser.add_argument('--skip-gemini', action='store_true',
                       help='Skip Gemini API tests')
    parser.add_argument('--skip-feeds', action='store_true',
                       help='Skip RSS feed processing tests')
    parser.add_argument('--skip-worker', action='store_true',
                       help='Skip cron worker tests')
    parser.add_argument('--no-dry-run', action='store_true',
                       help='Disable dry run mode (will actually post to Discord)')
    parser.add_argument('--interactive', action='store_true',
                       help='Interactive mode - ask before running each test')
    parser.add_argument('--stop-on-failure', action='store_true',
                       help='Stop testing if any test fails')
    
    args = parser.parse_args()
    
    # Safety check for live mode
    if args.no_dry_run:
        print_warning("WARNING: --no-dry-run specified. This will post actual content to Discord!")
        response = input("Are you absolutely sure you want to proceed? (yes/NO): ")
        if response.lower() != 'yes':
            print_info("Test cancelled by user")
            return
    
    # Create sample feeds file if needed
    create_sample_feeds_file()
    
    # Run tests
    runner = TestRunner(args)
    runner.run_all_tests()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test suite interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error in test suite: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
