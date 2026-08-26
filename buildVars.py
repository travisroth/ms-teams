# Build customizations for Microsoft Teams Accessibility Enhancements.

from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries, SpeechDictionaries
from site_scons.site_tools.NVDATool.utils import _


addon_info = AddonInfo(
	addon_name="msTeamsMessageHelpFilter",
	# Translators: Summary/title shown in NVDA's Add-on Store and Add-on Manager.
	addon_summary=_("Microsoft Teams accessibility enhancements"),
	# Translators: Long add-on description shown in NVDA's Add-on Store.
	addon_description=_(
		"Filters repetitive message help and adds focus-free recent-message reading commands "
		+ "for the New Microsoft Teams client.",
	),
	addon_version="1.6.0",
	# Translators: Changes in this release, shown in NVDA's Add-on Store.
	addon_changelog=_(
		"Removed the global plugin and all braille monkey patching of BrailleHandler.update. "
		+ "The app module is now named after the executable, so NVDA loads it without "
		+ "registration. Navigation help is filtered at the NVDAObject properties, and "
		+ "Chromium live region announcements are filtered where they enter NVDA. Also "
		+ "suppresses the chat list filter count and send progress announcements.",
	),
	addon_author="Ryan Praeuner; Travis Roth <travis@travisroth.com>",
	addon_url="https://github.com/travisroth/ms-teams",
	addon_sourceURL="https://github.com/travisroth/ms-teams",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2026.1",
	addon_lastTestedNVDAVersion="2026.3",
	addon_updateChannel=None,
	addon_license="GNU General Public License version 2 or later",
	addon_licenseURL="https://github.com/travisroth/ms-teams/blob/master/COPYING.txt",
)

pythonSources: list[str] = [
	"addon/appModules/*.py",
]

i18nSources: list[str] = pythonSources + ["buildVars.py"]

excludedFiles: list[str] = [
	"**/__pycache__/*",
	"**/*.pyc",
]

baseLanguage: str = "en"

markdownExtensions: list[str] = []

brailleTables: BrailleTables = {}

symbolDictionaries: SymbolDictionaries = {}

speechDictionaries: SpeechDictionaries = {}
