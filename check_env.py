import sys
import pathlib
import importlib.util

print("Running Python:", sys.executable)
spec = importlib.util.find_spec("bot.main")
print("bot.main from :", pathlib.Path(spec.origin).resolve())
