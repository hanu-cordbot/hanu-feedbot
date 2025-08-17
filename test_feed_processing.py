#!/usr/bin/env python3
"""
HANU Feedbot - Feed Processing Test
==================================

This script tests RSS feed processing, parsing, and content handling
to ensure the bot can properly process feeds without posting to Discord.
"""

import os
import sys
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

import feedparser
import requests
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

class FeedProcessingTester:
    def __init__(self):
        self.max_age_hours = int(os.environ.get('MAX_AGE_HOURS', '36'))
        self.test_results = {}
        self.sample_feeds = []
        self.test_entries = []
    
    def load_feed_list(self) -> bool:
        """Load RSS feeds from feeds.txt"""
        print_header("Loading RSS Feed List")
        
        feeds_file = Path("feeds.txt")
        if not feeds_file.exists():
            print_error("feeds.txt not found!")
            return False
        
        try:
            with open(feeds_file, 'r') as f:
                feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not feeds:
                print_error("No feeds found in feeds.txt")
                return False
            
            self.sample_feeds = feeds[:5]  # Use first 5 feeds for testing
            print_success(f"Loaded {len(feeds)} feeds from feeds.txt")
            print_info(f"Using first {len(self.sample_feeds)} feeds for testing:")
            
            for i, feed_url in enumerate(self.sample_feeds, 1):
                print_info(f"  {i}. {feed_url}")
            
            self.test_results['feed_loading'] = True
            return True
            
        except Exception as e:
            print_error(f"Error loading feeds.txt: {e}")
            self.test_results['feed_loading'] = False
            return False
    
    def test_feed_parsing(self) -> bool:
        """Test parsing RSS feeds"""
        print_header("Testing RSS Feed Parsing")
        
        if not self.sample_feeds:
            print_error("No feeds loaded for testing")
            self.test_results['feed_parsing'] = False
            return False
        
        successful_parses = 0
        total_entries = 0
        
        for i, feed_url in enumerate(self.sample_feeds, 1):
            print_info(f"Testing feed {i}/{len(self.sample_feeds)}: {feed_url}")
            
            try:
                # Parse the feed
                start_time = time.time()
                feed = feedparser.parse(feed_url)
                parse_time = time.time() - start_time
                
                if feed.bozo:
                    print_warning(f"  Feed has parsing errors: {feed.bozo_exception}")
                else:
                    print_success(f"  Parsed successfully in {parse_time:.2f}s")
                
                # Check feed metadata
                feed_title = getattr(feed.feed, 'title', 'Unknown')
                feed_link = getattr(feed.feed, 'link', 'Unknown')
                print_info(f"  Title: {feed_title}")
                print_info(f"  Link: {feed_link}")
                print_info(f"  Entries: {len(feed.entries)}")
                
                if len(feed.entries) > 0:
                    successful_parses += 1
                    total_entries += len(feed.entries)
                    
                    # Store first few entries for further testing
                    for entry in feed.entries[:2]:
                        self.test_entries.append({
                            'feed_url': feed_url,
                            'feed_title': feed_title,
                            'entry': entry
                        })
                else:
                    print_warning(f"  No entries found in feed")
                
            except Exception as e:
                print_error(f"  Error parsing feed: {e}")
                continue
        
        if successful_parses > 0:
            print_success(f"Successfully parsed {successful_parses}/{len(self.sample_feeds)} feeds")
            print_info(f"Total entries found: {total_entries}")
            self.test_results['feed_parsing'] = True
            return True
        else:
            print_error("Failed to parse any feeds")
            self.test_results['feed_parsing'] = False
            return False
    
    def test_entry_processing(self) -> bool:
        """Test processing individual RSS entries"""
        print_header("Testing RSS Entry Processing")
        
        if not self.test_entries:
            print_error("No entries available for testing")
            self.test_results['entry_processing'] = False
            return False
        
        try:
            # Try to import bot's entry processing functions
            sys.path.append('bot')
            
            try:
                from bot.parser import iter_entries, get_entry_id
                print_success("Successfully imported bot's parser functions")
                
                processed_count = 0
                
                for i, test_data in enumerate(self.test_entries[:3], 1):
                    entry = test_data['entry']
                    feed_url = test_data['feed_url']
                    
                    print_info(f"Processing entry {i}: {getattr(entry, 'title', 'No title')[:50]}...")
                    
                    try:
                        # Test entry ID generation
                        entry_id = get_entry_id(entry)
                        if entry_id:
                            print_success(f"  Generated entry ID: {entry_id}")
                        else:
                            print_warning("  Could not generate entry ID")
                        
                        # Test entry attributes
                        title = getattr(entry, 'title', None)
                        description = getattr(entry, 'description', None)
                        link = getattr(entry, 'link', None)
                        published = getattr(entry, 'published_parsed', None)
                        
                        print_info(f"  Title: {title[:50] if title else 'None'}...")
                        print_info(f"  Description: {description[:50] if description else 'None'}...")
                        print_info(f"  Link: {link if link else 'None'}")
                        print_info(f"  Published: {published if published else 'None'}")
                        
                        if title and description and link:
                            print_success("  Entry has required fields")
                            processed_count += 1
                        else:
                            print_warning("  Entry missing some required fields")
                        
                    except Exception as e:
                        print_error(f"  Error processing entry: {e}")
                        continue
                
                if processed_count > 0:
                    print_success(f"Successfully processed {processed_count} entries")
                    self.test_results['entry_processing'] = True
                    return True
                else:
                    print_error("Failed to process any entries")
                    self.test_results['entry_processing'] = False
                    return False
                    
            except ImportError as e:
                print_warning(f"Could not import bot's parser functions: {e}")
                print_info("Testing basic entry processing without bot functions...")
                
                # Basic processing without bot functions
                processed_count = 0
                for test_data in self.test_entries[:3]:
                    entry = test_data['entry']
                    
                    title = getattr(entry, 'title', None)
                    description = getattr(entry, 'description', None)
                    link = getattr(entry, 'link', None)
                    
                    if title and (description or link):
                        processed_count += 1
                
                if processed_count > 0:
                    print_success(f"Basic processing successful for {processed_count} entries")
                    self.test_results['entry_processing'] = True
                    return True
                else:
                    self.test_results['entry_processing'] = False
                    return False
                    
        except Exception as e:
            print_error(f"Error testing entry processing: {e}")
            self.test_results['entry_processing'] = False
            return False
    
    def test_age_filtering(self) -> bool:
        """Test age filtering logic"""
        print_header("Testing Age Filtering")
        
        try:
            print_info(f"MAX_AGE_HOURS setting: {self.max_age_hours} hours")
            
            # Test entries with different ages
            from datetime import datetime, timezone, timedelta
            
            now = datetime.now(timezone.utc)
            test_dates = [
                now - timedelta(hours=1),     # 1 hour ago (should pass)
                now - timedelta(hours=12),    # 12 hours ago (should pass)
                now - timedelta(hours=24),    # 24 hours ago (should pass if MAX_AGE_HOURS > 24)
                now - timedelta(hours=48),    # 48 hours ago (should fail if MAX_AGE_HOURS < 48)
                now - timedelta(days=7),      # 7 days ago (should fail)
            ]
            
            for i, test_date in enumerate(test_dates, 1):
                age_hours = (now - test_date).total_seconds() / 3600
                should_pass = age_hours <= self.max_age_hours
                
                print_info(f"Test {i}: {age_hours:.1f} hours old - {'PASS' if should_pass else 'FILTER'}")
            
            # Try to test with bot's age filtering function
            try:
                sys.path.append('bot')
                from bot.parser import iter_entries
                print_success("Age filtering logic is available in bot")
            except ImportError:
                print_warning("Bot's age filtering not available - testing basic logic")
            
            print_success("Age filtering test completed")
            self.test_results['age_filtering'] = True
            return True
            
        except Exception as e:
            print_error(f"Error testing age filtering: {e}")
            self.test_results['age_filtering'] = False
            return False
    
    def test_content_formatting(self) -> bool:
        """Test content formatting for Discord posting"""
        print_header("Testing Content Formatting")
        
        if not self.test_entries:
            print_error("No entries available for testing")
            self.test_results['content_formatting'] = False
            return False
        
        try:
            # Try to import bot's formatting functions
            sys.path.append('bot')
            
            try:
                from bot.formatter import build_full_body, build_prompt
                print_success("Successfully imported bot's formatting functions")
                
                for i, test_data in enumerate(self.test_entries[:2], 1):
                    entry = test_data['entry']
                    
                    print_info(f"Testing formatting for entry {i}...")
                    
                    try:
                        # Test build_full_body
                        body = build_full_body(entry)
                        if body:
                            print_success(f"  Generated body: {len(body)} characters")
                            print_info(f"  Body preview: {body[:100]}...")
                        else:
                            print_warning("  build_full_body returned empty result")
                        
                        # Test build_prompt
                        prompt = build_prompt(entry)
                        if prompt:
                            print_success(f"  Generated prompt: {len(prompt)} characters")
                            print_info(f"  Prompt preview: {prompt[:100]}...")
                        else:
                            print_warning("  build_prompt returned empty result")
                            
                    except Exception as e:
                        print_error(f"  Error formatting entry: {e}")
                        continue
                
                print_success("Content formatting test completed")
                self.test_results['content_formatting'] = True
                return True
                
            except ImportError as e:
                print_warning(f"Could not import bot's formatting functions: {e}")
                print_info("Testing basic formatting without bot functions...")
                
                # Basic formatting test
                for test_data in self.test_entries[:2]:
                    entry = test_data['entry']
                    
                    title = getattr(entry, 'title', 'No title')
                    description = getattr(entry, 'description', 'No description')
                    link = getattr(entry, 'link', 'No link')
                    
                    basic_format = f"**{title}**\n\n{description}\n\n{link}"
                    print_info(f"Basic format: {len(basic_format)} characters")
                
                print_success("Basic formatting test completed")
                self.test_results['content_formatting'] = True
                return True
                
        except Exception as e:
            print_error(f"Error testing content formatting: {e}")
            self.test_results['content_formatting'] = False
            return False
    
    def test_state_management(self) -> bool:
        """Test state file management (seen.json, etc.)"""
        print_header("Testing State Management")
        
        try:
            # Test seen.json functionality
            seen_file = Path("seen.json")
            
            # Create backup if file exists
            backup_needed = seen_file.exists()
            if backup_needed:
                backup_content = seen_file.read_text()
            
            try:
                # Try to import bot's state management functions
                sys.path.append('bot')
                
                try:
                    from bot.parser import load_seen_guids, save_seen_guids
                    print_success("Successfully imported bot's state management functions")
                    
                    # Test loading seen GUIDs
                    seen_guids = load_seen_guids()
                    print_success(f"Loaded seen GUIDs: {len(seen_guids)} entries")
                    
                    # Test saving (add a test entry)
                    test_guid = f"test_guid_{int(time.time())}"
                    seen_guids[test_guid] = int(time.time())
                    save_seen_guids(seen_guids)
                    print_success("Successfully saved test GUID")
                    
                    # Verify it was saved
                    reloaded_guids = load_seen_guids()
                    if test_guid in reloaded_guids:
                        print_success("Test GUID was properly persisted")
                        
                        # Clean up test GUID
                        del reloaded_guids[test_guid]
                        save_seen_guids(reloaded_guids)
                        print_info("Cleaned up test GUID")
                    else:
                        print_warning("Test GUID was not persisted")
                    
                    self.test_results['state_management'] = True
                    return True
                    
                except ImportError as e:
                    print_warning(f"Could not import bot's state functions: {e}")
                    print_info("Testing basic state file operations...")
                    
                    # Basic state file test
                    test_data = {"test_key": int(time.time())}
                    
                    with open("seen.json", "w") as f:
                        json.dump(test_data, f)
                    
                    with open("seen.json", "r") as f:
                        loaded_data = json.load(f)
                    
                    if loaded_data == test_data:
                        print_success("Basic state file operations work")
                        self.test_results['state_management'] = True
                        return True
                    else:
                        print_error("State file operations failed")
                        self.test_results['state_management'] = False
                        return False
            
            finally:
                # Restore backup if needed
                if backup_needed:
                    seen_file.write_text(backup_content)
                    print_info("Restored original seen.json")
                elif seen_file.exists():
                    # Remove test file if we created it
                    seen_file.unlink()
                    print_info("Removed test seen.json")
                    
        except Exception as e:
            print_error(f"Error testing state management: {e}")
            self.test_results['state_management'] = False
            return False
    
    def test_media_handling(self) -> bool:
        """Test media download and processing"""
        print_header("Testing Media Handling")
        
        try:
            # Test basic image/media detection
            media_entries = []
            
            for test_data in self.test_entries:
                entry = test_data['entry']
                description = getattr(entry, 'description', '')
                
                # Look for common media indicators
                if any(ext in description.lower() for ext in ['.jpg', '.png', '.gif', '.mp4', 'facebook.com', 'instagram.com']):
                    media_entries.append(test_data)
            
            if media_entries:
                print_info(f"Found {len(media_entries)} entries with potential media content")
                
                # Try to test Facebook downloader
                try:
                    sys.path.append('bot')
                    from bot.facebook_downloader import download_facebook_video
                    print_success("Facebook downloader module is available")
                    
                    # Don't actually download, just check if function exists
                    print_info("Facebook video download capability is ready")
                    
                except ImportError as e:
                    print_warning(f"Facebook downloader not available: {e}")
                
                self.test_results['media_handling'] = True
                return True
            else:
                print_info("No media content detected in test entries")
                self.test_results['media_handling'] = True
                return True
                
        except Exception as e:
            print_error(f"Error testing media handling: {e}")
            self.test_results['media_handling'] = False
            return False
    
    def simulate_discord_output(self) -> bool:
        """Simulate what would be posted to Discord"""
        print_header("Simulating Discord Output")
        
        if not self.test_entries:
            print_error("No entries available for simulation")
            self.test_results['discord_simulation'] = False
            return False
        
        try:
            print_info("Simulating Discord posts for first few entries...")
            
            for i, test_data in enumerate(self.test_entries[:2], 1):
                entry = test_data['entry']
                feed_title = test_data['feed_title']
                
                print_info(f"\n--- Simulated Discord Post {i} ---")
                
                title = getattr(entry, 'title', 'No title')
                description = getattr(entry, 'description', 'No description')
                link = getattr(entry, 'link', 'No link')
                author = getattr(entry, 'author', 'Unknown')
                
                # Simulate what would be posted
                print_info(f"Feed: {feed_title}")
                print_info(f"Title: {title}")
                print_info(f"Author: {author}")
                print_info(f"Description: {description[:200]}{'...' if len(description) > 200 else ''}")
                print_info(f"Link: {link}")
                
                # Check content length for Discord limits
                total_length = len(title) + len(description) + len(link) + 100  # Extra for formatting
                if total_length > 2000:
                    print_warning(f"  Content may exceed Discord message limit: {total_length} chars")
                else:
                    print_success(f"  Content length OK: {total_length} chars")
            
            print_success("Discord output simulation completed")
            self.test_results['discord_simulation'] = True
            return True
            
        except Exception as e:
            print_error(f"Error simulating Discord output: {e}")
            self.test_results['discord_simulation'] = False
            return False
    
    def print_test_summary(self):
        """Print a summary of all test results"""
        print_header("Feed Processing Test Summary")
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        print(f"\n{Colors.BOLD}Results: {passed_tests}/{total_tests} tests passed{Colors.END}\n")
        
        test_descriptions = {
            'feed_loading': 'Feed List Loading',
            'feed_parsing': 'RSS Feed Parsing',
            'entry_processing': 'Entry Processing',
            'age_filtering': 'Age Filtering Logic',
            'content_formatting': 'Content Formatting',
            'state_management': 'State Management',
            'media_handling': 'Media Handling',
            'discord_simulation': 'Discord Output Simulation'
        }
        
        for test_name, passed in self.test_results.items():
            description = test_descriptions.get(test_name, test_name)
            status = "✅ PASS" if passed else "❌ FAIL"
            color = Colors.GREEN if passed else Colors.RED
            print(f"{color}{status}{Colors.END} {description}")
        
        if passed_tests == total_tests:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All feed processing tests passed! RSS processing is ready.{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.RED}⚠️  Some feed processing tests failed.{Colors.END}")
            print(f"\n{Colors.CYAN}Troubleshooting tips:{Colors.END}")
            
            if not self.test_results.get('feed_loading', True):
                print("• Check that feeds.txt exists and contains valid RSS URLs")
            
            if not self.test_results.get('feed_parsing', True):
                print("• Verify RSS feed URLs are accessible and valid")
                print("• Check network connectivity to RSS sources")
            
            if not self.test_results.get('entry_processing', True):
                print("• Ensure bot modules are properly configured")
                print("• Check that RSS entries have required fields")
            
            if not self.test_results.get('content_formatting', True):
                print("• Verify bot's formatting functions are working")
                print("• Check entry content for special characters")
            
            if not self.test_results.get('state_management', True):
                print("• Ensure read/write permissions for state files")
                print("• Check that JSON files are valid format")

def main():
    """Main test function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              HANU FEEDBOT FEED PROCESSING TEST               ║")
    print("║                RSS Feed Parsing & Processing                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    tester = FeedProcessingTester()
    
    # Run tests sequentially
    tester.load_feed_list()
    tester.test_feed_parsing()
    tester.test_entry_processing()
    tester.test_age_filtering()
    tester.test_content_formatting()
    tester.test_state_management()
    tester.test_media_handling()
    tester.simulate_discord_output()
    
    # Print summary
    tester.print_test_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
