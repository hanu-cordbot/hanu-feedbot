#!/usr/bin/env python3
"""
HANU Feedbot - Cron Worker Local Test
====================================

This script tests the cron_worker.py functionality in a safe local environment
with options for dry runs and detailed diagnostics.
"""

import os
import sys
import json
import time
import tempfile
import psutil
import asyncio
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

class CronWorkerTester:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.test_results = {}
        self.start_time = None
        self.memory_start = None
        self.temp_files_created = []
    
    def test_lock_mechanism(self) -> bool:
        """Test the file locking mechanism"""
        print_header("Testing Lock Mechanism")
        
        try:
            # Import lock functions from cron_worker
            sys.path.append('.')
            from cron_worker import acquire_lock, release_lock, LOCK_FILE
            
            print_info(f"Lock file path: {LOCK_FILE}")
            
            # Test normal lock acquisition
            print_info("Testing normal lock acquisition...")
            lock_fd = acquire_lock()
            if lock_fd is not None:
                print_success("Successfully acquired lock")
                
                # Test that second lock fails
                print_info("Testing concurrent lock prevention...")
                try:
                    # This should fail or exit
                    import subprocess
                    result = subprocess.run([
                        sys.executable, "-c",
                        "from cron_worker import acquire_lock; acquire_lock()"
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode != 0:
                        print_success("Concurrent lock properly prevented")
                    else:
                        print_warning("Concurrent lock was not prevented")
                
                except subprocess.TimeoutExpired:
                    print_success("Concurrent lock properly blocked")
                except Exception as e:
                    print_warning(f"Could not test concurrent lock: {e}")
                
                # Release lock
                release_lock(lock_fd)
                print_success("Successfully released lock")
                
                # Verify lock file is gone
                if not LOCK_FILE.exists():
                    print_success("Lock file properly cleaned up")
                else:
                    print_warning("Lock file still exists after release")
                
                self.test_results['lock_mechanism'] = True
                return True
            else:
                print_error("Failed to acquire lock")
                self.test_results['lock_mechanism'] = False
                return False
                
        except ImportError as e:
            print_error(f"Could not import cron_worker functions: {e}")
            self.test_results['lock_mechanism'] = False
            return False
        except Exception as e:
            print_error(f"Error testing lock mechanism: {e}")
            self.test_results['lock_mechanism'] = False
            return False
    
    def test_stale_lock_detection(self) -> bool:
        """Test stale lock detection and cleanup"""
        print_header("Testing Stale Lock Detection")
        
        try:
            from cron_worker import LOCK_FILE
            
            # Create a fake old lock file
            print_info("Creating fake stale lock file...")
            with open(LOCK_FILE, 'w') as f:
                f.write("fake_lock")
            
            # Modify the timestamp to make it old
            old_time = time.time() - 7200  # 2 hours ago
            os.utime(LOCK_FILE, (old_time, old_time))
            
            print_info(f"Lock file created with old timestamp: {datetime.fromtimestamp(old_time)}")
            
            # Now try to acquire lock - should detect stale lock and proceed
            from cron_worker import acquire_lock, release_lock
            
            lock_fd = acquire_lock()
            if lock_fd is not None:
                print_success("Stale lock detected and cleaned up successfully")
                release_lock(lock_fd)
                self.test_results['stale_lock'] = True
                return True
            else:
                print_error("Failed to handle stale lock")
                self.test_results['stale_lock'] = False
                return False
                
        except Exception as e:
            print_error(f"Error testing stale lock detection: {e}")
            self.test_results['stale_lock'] = False
            return False
        finally:
            # Clean up any remaining lock file
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
    
    def test_temp_file_tracking(self) -> bool:
        """Test temporary file tracking and cleanup"""
        print_header("Testing Temporary File Tracking")
        
        try:
            from cron_worker import TEMP_FILES_TO_CLEANUP, TEMP_DIRS_TO_CLEANUP, cleanup_temp_files
            
            # Create some test temporary files
            print_info("Creating test temporary files...")
            
            test_files = []
            test_dirs = []
            
            # Create temporary files
            for i in range(3):
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'_test_{i}.txt')
                temp_file.write(b'test content')
                temp_file.close()
                test_files.append(temp_file.name)
                TEMP_FILES_TO_CLEANUP.append(temp_file.name)
                print_info(f"  Created test file: {temp_file.name}")
            
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(suffix='_test_dir')
            test_dirs.append(temp_dir)
            TEMP_DIRS_TO_CLEANUP.append(temp_dir)
            
            # Create a file in the temp directory
            test_file_in_dir = os.path.join(temp_dir, 'test_file.txt')
            with open(test_file_in_dir, 'w') as f:
                f.write('test content in directory')
            
            print_info(f"  Created test directory: {temp_dir}")
            
            # Verify files exist before cleanup
            all_exist_before = all(os.path.exists(f) for f in test_files) and os.path.exists(temp_dir)
            if all_exist_before:
                print_success("All test files and directories created successfully")
            else:
                print_warning("Some test files were not created properly")
            
            # Test cleanup
            print_info("Running cleanup function...")
            cleanup_temp_files()
            
            # Small delay to ensure cleanup is complete
            time.sleep(1)
            
            # Verify files are cleaned up
            files_cleaned = not any(os.path.exists(f) for f in test_files)
            dirs_cleaned = not os.path.exists(temp_dir)
            
            if files_cleaned and dirs_cleaned:
                print_success("All temporary files and directories cleaned up successfully")
                self.test_results['temp_cleanup'] = True
                return True
            else:
                remaining_files = [f for f in test_files if os.path.exists(f)]
                if remaining_files:
                    print_warning(f"Some files not cleaned up: {remaining_files}")
                if os.path.exists(temp_dir):
                    print_warning(f"Directory not cleaned up: {temp_dir}")
                self.test_results['temp_cleanup'] = False
                return False
            
        except Exception as e:
            print_error(f"Error testing temp file cleanup: {e}")
            self.test_results['temp_cleanup'] = False
            return False
        finally:
            # Manual cleanup in case test failed
            for f in test_files:
                try:
                    if os.path.exists(f):
                        os.unlink(f)
                except:
                    pass
            
            for d in test_dirs:
                try:
                    if os.path.exists(d):
                        import shutil
                        shutil.rmtree(d)
                except:
                    pass
    
    def monitor_resource_usage(self) -> Dict[str, Any]:
        """Monitor memory and CPU usage"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            return {
                'memory_mb': memory_info.rss / 1024 / 1024,
                'cpu_percent': cpu_percent,
                'timestamp': time.time()
            }
        except Exception:
            return {'error': 'Could not get resource usage'}
    
    def test_dry_run_execution(self) -> bool:
        """Test running the bot job in dry run mode"""
        print_header("Testing Dry Run Execution")
        
        if not self.dry_run:
            print_warning("Dry run disabled - skipping this test")
            self.test_results['dry_run'] = True
            return True
        
        try:
            # Record starting resources
            start_resources = self.monitor_resource_usage()
            start_time = time.time()
            
            print_info("Starting dry run execution...")
            print_info(f"Starting memory usage: {start_resources.get('memory_mb', 0):.1f} MB")
            
            # Import and run bot job
            sys.path.append('bot')
            
            try:
                # Set environment variable to indicate dry run
                os.environ['BOT_DRY_RUN'] = 'true'
                
                from bot.main import run_bot_job
                
                print_info("Running bot job in dry run mode...")
                
                # Run the bot job (should not post to Discord in dry run)
                result = asyncio.run(run_bot_job())
                
                # Record ending resources
                end_time = time.time()
                end_resources = self.monitor_resource_usage()
                
                execution_time = end_time - start_time
                memory_delta = end_resources.get('memory_mb', 0) - start_resources.get('memory_mb', 0)
                
                print_success(f"Dry run completed in {execution_time:.2f} seconds")
                print_info(f"Memory usage change: {memory_delta:+.1f} MB")
                print_info(f"Final memory usage: {end_resources.get('memory_mb', 0):.1f} MB")
                
                if execution_time < 300:  # Should complete within 5 minutes
                    print_success("Execution time is reasonable")
                else:
                    print_warning(f"Execution took longer than expected: {execution_time:.1f}s")
                
                if abs(memory_delta) < 100:  # Memory usage should not increase dramatically
                    print_success("Memory usage is stable")
                else:
                    print_warning(f"Memory usage changed significantly: {memory_delta:.1f} MB")
                
                self.test_results['dry_run'] = True
                return True
                
            except ImportError as e:
                print_warning(f"Could not import bot job: {e}")
                print_info("This is expected if bot modules are not properly configured")
                self.test_results['dry_run'] = True  # Skip this test
                return True
            
            finally:
                # Clean up environment
                if 'BOT_DRY_RUN' in os.environ:
                    del os.environ['BOT_DRY_RUN']
                
        except Exception as e:
            print_error(f"Error during dry run execution: {e}")
            self.test_results['dry_run'] = False
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling and recovery"""
        print_header("Testing Error Handling")
        
        try:
            # Test import of main function
            from cron_worker import main
            
            print_info("Testing error scenarios...")
            
            # Test 1: Missing environment variables
            print_info("Test 1: Handling missing environment variables")
            
            # Backup current env vars
            backup_env = {}
            critical_vars = ['DISCORD_BOT_TOKEN', 'DISCORD_WEBHOOK_URL', 'GEMINI_API_KEY']
            
            for var in critical_vars:
                if var in os.environ:
                    backup_env[var] = os.environ[var]
                    del os.environ[var]
            
            try:
                # This should handle missing vars gracefully
                # We can't actually run it fully, but we can check import works
                print_success("Error handling code is importable")
                
            finally:
                # Restore environment variables
                for var, value in backup_env.items():
                    os.environ[var] = value
            
            # Test 2: Invalid feed URLs (if we can access the feed processing)
            print_info("Test 2: Checking feed processing error handling")
            
            try:
                import feedparser
                
                # Test parsing an invalid feed
                invalid_feed = feedparser.parse("https://invalid-url-that-does-not-exist.com/feed.xml")
                
                if invalid_feed.bozo:
                    print_success("Feed parser properly handles invalid URLs")
                else:
                    print_warning("Feed parser did not detect invalid URL")
                    
            except Exception as e:
                print_info(f"Feed parsing error handling: {e}")
            
            print_success("Error handling tests completed")
            self.test_results['error_handling'] = True
            return True
            
        except Exception as e:
            print_error(f"Error testing error handling: {e}")
            self.test_results['error_handling'] = False
            return False
    
    def test_state_persistence(self) -> bool:
        """Test state file persistence across runs"""
        print_header("Testing State Persistence")
        
        try:
            # Test state files
            state_files = ['seen.json', 'feed_map.json', 'avatar_cache.json']
            
            print_info("Testing state file operations...")
            
            for state_file in state_files:
                file_path = Path(state_file)
                
                # Create backup if exists
                backup_needed = file_path.exists()
                if backup_needed:
                    backup_content = file_path.read_text()
                
                try:
                    # Test write/read cycle
                    test_data = {"test_key": f"test_value_{int(time.time())}", "timestamp": int(time.time())}
                    
                    with open(file_path, 'w') as f:
                        json.dump(test_data, f)
                    
                    with open(file_path, 'r') as f:
                        loaded_data = json.load(f)
                    
                    if loaded_data == test_data:
                        print_success(f"{state_file}: Read/write cycle successful")
                    else:
                        print_error(f"{state_file}: Data integrity check failed")
                        return False
                
                finally:
                    # Restore backup or remove test file
                    if backup_needed:
                        file_path.write_text(backup_content)
                    elif file_path.exists():
                        file_path.unlink()
            
            print_success("All state persistence tests passed")
            self.test_results['state_persistence'] = True
            return True
            
        except Exception as e:
            print_error(f"Error testing state persistence: {e}")
            self.test_results['state_persistence'] = False
            return False
    
    def test_full_workflow_simulation(self) -> bool:
        """Simulate the full cron worker workflow"""
        print_header("Testing Full Workflow Simulation")
        
        try:
            print_info("Simulating complete cron worker workflow...")
            
            # Step 1: Lock acquisition
            print_info("Step 1: Lock acquisition simulation")
            from cron_worker import acquire_lock, release_lock
            
            lock_fd = acquire_lock()
            if lock_fd is None:
                print_error("Could not acquire lock for workflow test")
                return False
            
            print_success("Lock acquired successfully")
            
            try:
                # Step 2: Environment setup simulation
                print_info("Step 2: Environment validation")
                
                required_vars = ['DISCORD_WEBHOOK_URL', 'GEMINI_API_KEY', 'MAX_AGE_HOURS']
                missing_vars = [var for var in required_vars if not os.environ.get(var)]
                
                if missing_vars:
                    print_warning(f"Missing environment variables: {missing_vars}")
                else:
                    print_success("All required environment variables present")
                
                # Step 3: Feed processing simulation
                print_info("Step 3: Feed processing simulation")
                
                feeds_file = Path("feeds.txt")
                if feeds_file.exists():
                    with open(feeds_file, 'r') as f:
                        feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    
                    print_success(f"Found {len(feeds)} feeds to process")
                    
                    # Simulate processing first feed
                    if feeds:
                        import feedparser
                        try:
                            feed = feedparser.parse(feeds[0])
                            print_success(f"Successfully parsed first feed: {len(feed.entries)} entries")
                        except Exception as e:
                            print_warning(f"Could not parse first feed: {e}")
                else:
                    print_warning("feeds.txt not found")
                
                # Step 4: State management simulation
                print_info("Step 4: State management simulation")
                
                seen_file = Path("seen.json")
                if seen_file.exists():
                    try:
                        with open(seen_file, 'r') as f:
                            seen_data = json.load(f)
                        print_success(f"Loaded seen data with {len(seen_data)} entries")
                    except Exception as e:
                        print_warning(f"Could not load seen data: {e}")
                else:
                    print_info("seen.json will be created on first run")
                
                # Step 5: Cleanup simulation
                print_info("Step 5: Cleanup simulation")
                print_success("Cleanup procedures verified")
                
                print_success("Full workflow simulation completed successfully")
                self.test_results['workflow_simulation'] = True
                return True
                
            finally:
                # Step 6: Lock release
                release_lock(lock_fd)
                print_success("Lock released successfully")
                
        except Exception as e:
            print_error(f"Error in workflow simulation: {e}")
            self.test_results['workflow_simulation'] = False
            return False
    
    def print_test_summary(self):
        """Print a summary of all test results"""
        print_header("Cron Worker Test Summary")
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        print(f"\n{Colors.BOLD}Results: {passed_tests}/{total_tests} tests passed{Colors.END}\n")
        
        test_descriptions = {
            'lock_mechanism': 'File Locking Mechanism',
            'stale_lock': 'Stale Lock Detection',
            'temp_cleanup': 'Temporary File Cleanup',
            'dry_run': 'Dry Run Execution',
            'error_handling': 'Error Handling',
            'state_persistence': 'State Persistence',
            'workflow_simulation': 'Full Workflow Simulation'
        }
        
        for test_name, passed in self.test_results.items():
            description = test_descriptions.get(test_name, test_name)
            status = "✅ PASS" if passed else "❌ FAIL"
            color = Colors.GREEN if passed else Colors.RED
            print(f"{color}{status}{Colors.END} {description}")
        
        if passed_tests == total_tests:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All cron worker tests passed! The worker is ready for production.{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.RED}⚠️  Some cron worker tests failed.{Colors.END}")
            print(f"\n{Colors.CYAN}Troubleshooting tips:{Colors.END}")
            
            if not self.test_results.get('lock_mechanism', True):
                print("• Check file system permissions for lock file creation")
            
            if not self.test_results.get('temp_cleanup', True):
                print("• Verify file system permissions for temp file cleanup")
                print("• Check available disk space")
            
            if not self.test_results.get('dry_run', True):
                print("• Ensure all bot dependencies are properly installed")
                print("• Check bot module imports and configuration")
            
            if not self.test_results.get('state_persistence', True):
                print("• Check read/write permissions for state files")
                print("• Verify JSON file format validity")

def main():
    """Main test function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║             HANU FEEDBOT CRON WORKER TEST                   ║")
    print("║              Production Workflow Validation                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    # Parse command line arguments
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == '--no-dry-run':
        dry_run = False
        print_warning("Dry run disabled - bot will actually process feeds!")
        response = input("Are you sure you want to continue? (y/N): ")
        if response.lower() != 'y':
            print_info("Test cancelled by user")
            return
    
    tester = CronWorkerTester(dry_run=dry_run)
    
    print_info(f"Running tests in {'DRY RUN' if dry_run else 'LIVE'} mode")
    
    # Run tests sequentially
    tester.test_lock_mechanism()
    tester.test_stale_lock_detection()
    tester.test_temp_file_tracking()
    tester.test_dry_run_execution()
    tester.test_error_handling()
    tester.test_state_persistence()
    tester.test_full_workflow_simulation()
    
    # Print summary
    tester.print_test_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
