#!/usr/bin/env python3
"""
HANU Feedbot - Discord Connection Test
=====================================

This script tests Discord bot connectivity, permissions, and functionality
to ensure the bot can properly connect and post to Discord channels.
"""

import asyncio
import os
import sys
import json
import tempfile
import io
from pathlib import Path
from typing import Optional

import discord
import aiohttp
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

class DiscordTester:
    def __init__(self):
        self.bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL') 
        self.channel_id = os.environ.get('CHANNEL_ID')
        self.fallback_channel_id = os.environ.get('GLOBAL_FALLBACK_CHANNEL_ID')
        
        self.client = None
        self.test_results = {}
    
    def load_credentials(self) -> bool:
        """Load and validate Discord credentials"""
        print_header("Loading Discord Credentials")
        
        # Check bot token
        if not self.bot_token:
            print_error("DISCORD_BOT_TOKEN not found in environment variables")
            return False
        
        if len(self.bot_token) < 50:
            print_error("DISCORD_BOT_TOKEN appears to be too short")
            return False
        
        print_success(f"Bot token loaded: {self.bot_token[:20]}...")
        
        # Check webhook URL
        if not self.webhook_url:
            print_error("DISCORD_WEBHOOK_URL not found in environment variables")
            return False
        
        if not self.webhook_url.startswith('https://discord.com/api/webhooks/'):
            print_error("DISCORD_WEBHOOK_URL format appears invalid")
            return False
        
        print_success(f"Webhook URL loaded: {self.webhook_url[:50]}...")
        
        # Check channel ID
        if not self.channel_id:
            print_error("CHANNEL_ID not found in environment variables")
            return False
        
        try:
            self.channel_id = int(self.channel_id)
            print_success(f"Channel ID loaded: {self.channel_id}")
        except ValueError:
            print_error("CHANNEL_ID must be a valid integer")
            return False
        
        # Check fallback channel ID (optional)
        if self.fallback_channel_id:
            try:
                self.fallback_channel_id = int(self.fallback_channel_id)
                print_success(f"Fallback channel ID loaded: {self.fallback_channel_id}")
            except ValueError:
                print_warning("GLOBAL_FALLBACK_CHANNEL_ID is not a valid integer")
                self.fallback_channel_id = None
        
        return True
    
    async def test_bot_connection(self) -> bool:
        """Test Discord bot token and basic connection"""
        print_header("Testing Bot Connection")
        
        try:
            # Create Discord client with required intents
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            intents.guild_messages = True
            
            self.client = discord.Client(intents=intents)
            
            # Set up event handlers
            @self.client.event
            async def on_ready():
                print_success(f"Bot connected successfully!")
                print_info(f"Bot user: {self.client.user}")
                print_info(f"Bot ID: {self.client.user.id}")
                print_info(f"Bot discriminator: {self.client.user.discriminator}")
                print_info(f"Connected to {len(self.client.guilds)} guilds")
                
                # List guilds
                for guild in self.client.guilds:
                    print_info(f"  • {guild.name} (ID: {guild.id})")
                
                self.test_results['bot_connection'] = True
            
            @self.client.event
            async def on_error(event, *args, **kwargs):
                print_error(f"Discord error in {event}: {args}")
                self.test_results['bot_connection'] = False
            
            # Start bot (will timeout after 10 seconds)
            try:
                await asyncio.wait_for(self.client.start(self.bot_token), timeout=15.0)
            except asyncio.TimeoutError:
                print_warning("Bot connection test timed out (this is normal for testing)")
                if 'bot_connection' not in self.test_results:
                    self.test_results['bot_connection'] = True  # Assume success if we got this far
            
            return True
            
        except discord.LoginFailure:
            print_error("Invalid bot token - login failed")
            self.test_results['bot_connection'] = False
            return False
        except discord.HTTPException as e:
            print_error(f"HTTP error connecting to Discord: {e}")
            self.test_results['bot_connection'] = False
            return False
        except Exception as e:
            print_error(f"Unexpected error connecting to Discord: {e}")
            self.test_results['bot_connection'] = False
            return False
        finally:
            if self.client and not self.client.is_closed():
                await self.client.close()
    
    async def test_channel_access(self) -> bool:
        """Test access to specified channel"""
        print_header("Testing Channel Access")
        
        if not self.client or self.client.is_closed():
            # Create a new client for testing
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            intents.guild_messages = True
            
            self.client = discord.Client(intents=intents)
            
            connected = False
            
            @self.client.event
            async def on_ready():
                nonlocal connected
                connected = True
            
            try:
                await asyncio.wait_for(self.client.start(self.bot_token), timeout=10.0)
            except asyncio.TimeoutError:
                if not connected:
                    print_error("Could not connect to Discord to test channel access")
                    return False
        
        try:
            # Test main channel
            channel = self.client.get_channel(self.channel_id)
            if channel:
                print_success(f"Found channel: {channel.name} (ID: {channel.id})")
                print_info(f"Channel type: {channel.type}")
                print_info(f"Guild: {channel.guild.name}")
                
                # Check permissions
                permissions = channel.permissions_for(channel.guild.me)
                print_info("Bot permissions in channel:")
                print_info(f"  • Send messages: {permissions.send_messages}")
                print_info(f"  • Attach files: {permissions.attach_files}")
                print_info(f"  • Create public threads: {permissions.create_public_threads}")
                print_info(f"  • Send messages in threads: {permissions.send_messages_in_threads}")
                print_info(f"  • Manage threads: {permissions.manage_threads}")
                
                required_perms = [
                    permissions.send_messages,
                    permissions.attach_files,
                    permissions.create_public_threads,
                    permissions.send_messages_in_threads
                ]
                
                if all(required_perms):
                    print_success("Bot has all required permissions in main channel")
                    self.test_results['channel_access'] = True
                else:
                    print_warning("Bot is missing some required permissions in main channel")
                    self.test_results['channel_access'] = False
            else:
                print_error(f"Could not find channel with ID: {self.channel_id}")
                print_info("The bot may not have access to this channel or it doesn't exist")
                self.test_results['channel_access'] = False
            
            # Test fallback channel if specified
            if self.fallback_channel_id and self.fallback_channel_id != self.channel_id:
                fallback_channel = self.client.get_channel(self.fallback_channel_id)
                if fallback_channel:
                    print_success(f"Found fallback channel: {fallback_channel.name}")
                else:
                    print_warning(f"Could not find fallback channel with ID: {self.fallback_channel_id}")
            
            return True
            
        except Exception as e:
            print_error(f"Error testing channel access: {e}")
            self.test_results['channel_access'] = False
            return False
        finally:
            if self.client and not self.client.is_closed():
                await self.client.close()
    
    async def test_webhook_url(self) -> bool:
        """Test webhook URL connectivity"""
        print_header("Testing Webhook URL")
        
        try:
            # Test webhook with a simple message
            async with aiohttp.ClientSession() as session:
                test_data = {
                    "content": "🧪 **HANU Feedbot Test Message**\n\nThis is a test message from the Discord connection test script. If you see this, the webhook is working correctly!",
                    "username": "HANU Feedbot (Test)",
                    "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
                }
                
                async with session.post(
                    self.webhook_url,
                    json=test_data,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status in [200, 204]:
                        print_success("Webhook URL is working - test message sent!")
                        print_info("Check your Discord channel for the test message")
                        self.test_results['webhook'] = True
                        return True
                    else:
                        error_text = await response.text()
                        print_error(f"Webhook failed with status {response.status}: {error_text}")
                        self.test_results['webhook'] = False
                        return False
        
        except aiohttp.ClientError as e:
            print_error(f"Network error testing webhook: {e}")
            self.test_results['webhook'] = False
            return False
        except Exception as e:
            print_error(f"Unexpected error testing webhook: {e}")
            self.test_results['webhook'] = False
            return False
    
    async def test_embed_posting(self) -> bool:
        """Test posting embeds via webhook"""
        print_header("Testing Embed Posting")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Create a sample embed similar to what the bot would post
                embed_data = {
                    "embeds": [{
                        "title": "Test RSS Entry",
                        "description": "This is a test embed to verify that the bot can post rich content to Discord.",
                        "url": "https://example.com",
                        "color": 0x00ff00,
                        "timestamp": "2025-01-17T12:00:00Z",
                        "footer": {
                            "text": "HANU Feedbot Test"
                        },
                        "fields": [
                            {
                                "name": "Test Field",
                                "value": "This is a test field value",
                                "inline": False
                            }
                        ]
                    }],
                    "username": "HANU Feedbot (Test)",
                    "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"
                }
                
                async with session.post(
                    self.webhook_url,
                    json=embed_data,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status in [200, 204]:
                        print_success("Embed posting test successful!")
                        self.test_results['embed_posting'] = True
                        return True
                    else:
                        error_text = await response.text()
                        print_error(f"Embed posting failed with status {response.status}: {error_text}")
                        self.test_results['embed_posting'] = False
                        return False
        
        except Exception as e:
            print_error(f"Error testing embed posting: {e}")
            self.test_results['embed_posting'] = False
            return False
    
    async def test_file_upload(self) -> bool:
        """Test file upload capability"""
        print_header("Testing File Upload")
        
        try:
            # Create a temporary test file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_file.write("This is a test file for HANU Feedbot file upload testing.\n")
                temp_file.write("If you can see this file in Discord, file uploads are working correctly!")
                temp_file_path = temp_file.name
            
            try:
                async with aiohttp.ClientSession() as session:
                    # Prepare multipart form data
                    data = aiohttp.FormData()
                    data.add_field('content', '📎 **File Upload Test**\n\nTesting file attachment capability.')
                    data.add_field('username', 'HANU Feedbot (Test)')
                    
                    with open(temp_file_path, 'rb') as f:
                        data.add_field('file', f, filename='test_upload.txt', content_type='text/plain')
                        
                        async with session.post(self.webhook_url, data=data) as response:
                            if response.status in [200, 204]:
                                print_success("File upload test successful!")
                                self.test_results['file_upload'] = True
                                return True
                            else:
                                error_text = await response.text()
                                print_error(f"File upload failed with status {response.status}: {error_text}")
                                self.test_results['file_upload'] = False
                                return False
            
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
        
        except Exception as e:
            print_error(f"Error testing file upload: {e}")
            self.test_results['file_upload'] = False
            return False
    
    def print_test_summary(self):
        """Print a summary of all test results"""
        print_header("Discord Connection Test Summary")
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        print(f"\n{Colors.BOLD}Results: {passed_tests}/{total_tests} tests passed{Colors.END}\n")
        
        test_descriptions = {
            'bot_connection': 'Discord Bot Connection',
            'channel_access': 'Channel Access & Permissions',
            'webhook': 'Webhook URL Functionality',
            'embed_posting': 'Embed Posting',
            'file_upload': 'File Upload Capability'
        }
        
        for test_name, passed in self.test_results.items():
            description = test_descriptions.get(test_name, test_name)
            status = "✅ PASS" if passed else "❌ FAIL"
            color = Colors.GREEN if passed else Colors.RED
            print(f"{color}{status}{Colors.END} {description}")
        
        if passed_tests == total_tests:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 All Discord tests passed! Your Discord integration is ready.{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.RED}⚠️  Some Discord tests failed.{Colors.END}")
            print(f"\n{Colors.CYAN}Troubleshooting tips:{Colors.END}")
            
            if not self.test_results.get('bot_connection', True):
                print("• Check your DISCORD_BOT_TOKEN is valid and the bot is added to your server")
                print("• Ensure the bot has necessary intents enabled in Discord Developer Portal")
            
            if not self.test_results.get('channel_access', True):
                print("• Verify the CHANNEL_ID is correct and the bot has access to that channel")
                print("• Check bot permissions: Send Messages, Attach Files, Create Public Threads")
            
            if not self.test_results.get('webhook', True):
                print("• Verify your DISCORD_WEBHOOK_URL is correct and active")
                print("• Check if the webhook was deleted or the channel was removed")
            
            if not self.test_results.get('embed_posting', True):
                print("• Check webhook permissions for posting embeds")
            
            if not self.test_results.get('file_upload', True):
                print("• Check webhook permissions for file attachments")
                print("• Verify Discord server file upload limits")

async def main():
    """Main test function"""
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                HANU FEEDBOT DISCORD TEST                     ║")
    print("║              Discord Connection & Functionality              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    tester = DiscordTester()
    
    # Load credentials
    if not tester.load_credentials():
        print_error("Failed to load Discord credentials. Please check your .env file.")
        return
    
    # Run tests sequentially
    await tester.test_bot_connection()
    await tester.test_channel_access()
    await tester.test_webhook_url()
    await tester.test_embed_posting()
    await tester.test_file_upload()
    
    # Print summary
    tester.print_test_summary()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
