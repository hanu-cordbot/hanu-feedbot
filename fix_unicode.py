#!/usr/bin/env python3
"""
Quick fix script to remove Unicode emojis from Python files for Windows compatibility
"""
import os
import re
from pathlib import Path

def fix_unicode_in_file(file_path):
    """Remove Unicode emojis and replace with text equivalents"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace common emojis with text equivalents
    replacements = {
        '✅': '[OK]',
        '❌': '[ERROR]',
        '⚠️': '[WARNING]',
        '🚨': '[CRITICAL]',
        '🎯': '[TARGET]',
        '📥': '[DOWNLOAD]',
        '📤': '[UPLOAD]',
        '📷': '[MEDIA]',
        '🔌': '[DISCONNECT]',
        '💀': '[KILL]',
        '⏰': '[TIMEOUT]',
        '🚀': '[START]',
        '🛑': '[STOP]',
        '📝': '[LOG]',
        '⏱️': '[TIMER]',
        '💥': '[CRASH]',
        '🏁': '[FINISH]',
        '🤖': '[BOT]',
        '🔄': '[IMPORT]',
        '🧹': '[CLEANUP]',
        '🔒': '[LOCK]',
        '🔓': '[UNLOCK]',
        '🎬': '[START]'
    }
    
    # Apply replacements
    for emoji, replacement in replacements.items():
        content = content.replace(emoji, replacement)
    
    # Remove any remaining non-ASCII characters in print statements
    content = re.sub(r'print\([^)]*[^\x00-\x7F][^)]*\)', 
                     lambda m: re.sub(r'[^\x00-\x7F]', '?', m.group(0)), 
                     content)
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed: {file_path}")

def main():
    """Fix Unicode in bot files"""
    bot_files = [
        'bot/main.py',
        'bot/parser.py',
        'bot/formatter.py',
        'bot/dispatcher.py',
        'bot/gemini_client.py',
        'bot/avatar_cache.py',
        'bot/facebook_downloader.py'
    ]
    
    for file_path in bot_files:
        if os.path.exists(file_path):
            try:
                fix_unicode_in_file(file_path)
            except Exception as e:
                print(f"Error fixing {file_path}: {e}")
        else:
            print(f"File not found: {file_path}")

if __name__ == "__main__":
    main()
