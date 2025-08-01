import os

# --- Configuration ---
PROJECT_ROOT = "."
OUTPUT_FILE = "combined_code.txt"
INCLUDE_EXTENSIONS = ['.py', '.txt', '.md', '.json', '.html', '.css', '.js']
EXCLUDE_DIRS = ['__pycache__', '.venv', '.git', '.vscode', 'node_modules']
EXCLUDE_FILES = ['.env']

def build_context_file():
    """
    Combines all relevant files in the project into a single text file for context.
    """
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        outfile.write("# === Project Overview ===\n")
        outfile.write("# Add your project summary here.\n\n")
        for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if file in EXCLUDE_FILES:
                    continue
                if any(file.endswith(ext) for ext in INCLUDE_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    outfile.write(f"# === FILE: {os.path.relpath(file_path, PROJECT_ROOT)} ===\n\n")
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                            outfile.write(infile.read())
                        outfile.write("\n\n# === END FILE ===\n\n")
                    except Exception as e:
                        outfile.write(f"# --- Error reading file {file_path}: {e} ---\n\n")

if __name__ == "__main__":
    build_context_file()
    print(f"Project context built into {OUTPUT_FILE}")
    print(f"Excluded directories: {EXCLUDE_DIRS}")
