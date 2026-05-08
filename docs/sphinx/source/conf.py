# conf.py

import os
import sys

sys.path.insert(0, os.path.abspath('../../../src'))
print(os.path.abspath('../../..'))

# Configuration file for the Sphinx documentation builder.

project = 'IoT-PWR Docs'
copyright = '2026, tpiasek'
author = 'tpiasek'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',          # generate docs from docstrings
    'sphinx.ext.napoleon',         # Google/NumPy style docstrings handling
    'sphinx_autodoc_typehints',    # types documentation from type hints
    # 'breathe',                   # future doxygen integration
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
# html_static_path = ['_static']
