# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

from site_scons.site_tools.NVDATool.typings import (
	AddonInfo,
	BrailleTables,
	SymbolDictionaries,
	SpeechDictionaries,
)

# Since some strings in `addon_info` are translatable,
# we need to include them in the .po files.
# Gettext recognizes only strings given as parameters to the `_` function.
# To avoid initializing translations in this module we simply import a "fake" `_` function
# which returns whatever is given to it as an argument.
from site_scons.site_tools.NVDATool.utils import _

# Add-on information variables
addon_info = AddonInfo(
	# add-on Name/identifier, internal for NVDA
	addon_name="writerIa2TableNavigation",

	# Add-on summary/title, usually the user visible name of the add-on
	# Translators: Summary/title for this add-on
	# to be shown on installation and add-on information found in add-on store
	addon_summary=_("Writer IA2 Table Navigation"),

	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-on store
	addon_description=_("""Experimental proof of concept for IA2-based table cell navigation in LibreOffice Writer.

This add-on is intended for testing NVDA issue #4133. It is not an official NVDA build and not a final fix."""),

	# version
	addon_version="0.1.0",

	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""Initial experimental alpha release.

Implements IA2-based table cell navigation in LibreOffice Writer using control+alt+arrow keys. Speech and braille behavior are experimental."""),

	# Author(s)
	addon_author="Victor Tsai <surfer0627@gmail.com>",

	# URL for the add-on documentation support
	addon_url="https://github.com/surfer0627/Writer-IA2-Table-Navigation",

	# URL for the add-on repository where the source code can be found
	addon_sourceURL="https://github.com/surfer0627/Writer-IA2-Table-Navigation",

	# Documentation file name
	addon_docFileName="readme.html",

	# Minimum NVDA version supported (e.g. "2019.3.0", minor version is optional)
	addon_minimumNVDAVersion="2025.3",

	# Last NVDA version supported/tested (e.g. "2024.4.0", ideally more recent than minimum version)
	addon_lastTestedNVDAVersion="2026.1",

	# Add-on update channel (default is None, denoting stable releases,
	# and for development releases, use "dev".)
	# This is an experimental alpha add-on.
	addon_updateChannel="dev",

	# Add-on license such as GPL 2
	addon_license="GPL v2",

	# URL for the license document the add-on is licensed under
	addon_licenseURL="https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
)

# Define the python files that are the sources of your add-on.
# You can either list every file (using ""/") as a path separator,
# or use glob expressions.
pythonSources: list[str] = [
	"addon/appModules/*.py",
]

# Files that contain strings for translation. Usually your python sources
i18nSources: list[str] = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
excludedFiles: list[str] = []

# Base language for the NVDA add-on
baseLanguage: str = "en"

# Markdown extensions for add-on documentation
markdownExtensions: list[str] = [
	"markdown.extensions.tables",
]

# Custom braille translation tables
brailleTables: BrailleTables = {}

# Custom speech symbol dictionaries
symbolDictionaries: SymbolDictionaries = {}

# Custom speech dictionaries
speechDictionaries: SpeechDictionaries = {}

