# pylint: skip-file
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[2]
VERSION = (PACKAGE_DIR / "src" / "vrchat_speech_assistant" / "_version.py").read_text().split('"')[1]

project = "VRChat Speech Assistant"
author = "Amelien Deshams"
copyright = f"{datetime.now().year}, {author}"
version = VERSION
extensions = [
    "recommonmark",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx_automodapi.automodapi",
    "sphinx_copybutton",
]
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".txt": "markdown",
}
master_doc = "index"
exclude_patterns = ["Thumbs.db"]
templates_path = []
add_module_names = False
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_use_param = True
napoleon_use_ivar = True
numpydoc_show_class_members = False
todo_include_todos = True
