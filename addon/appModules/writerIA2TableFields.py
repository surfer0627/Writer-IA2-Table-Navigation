# -*- coding: UTF-8 -*-
# A part of Writer IA2 Table Navigation add-on for NVDA
# This file is covered by the GNU General Public License.
# See the file LICENSE for more details.

"""Build Writer IA2 table control fields.

This module is intentionally import-time inert.

It only defines helpers for constructing table / cell control fields.
It must not call UI, speech, braille, focus, caret, UNO, or dispatch APIs.
"""

from __future__ import annotations


class WriterIA2TableFieldBuilder:
	"""Build NVDA TextInfo control fields for Writer IA2 table cells."""

	def makeTableControlField(
		self,
		tableContext: dict,
	) -> object:
		textInfos, controlTypes = self._importFieldModules()

		field = textInfos.ControlField()
		field["role"] = controlTypes.Role.TABLE

		tableID = self._getFirstValue(
			tableContext,
			(
				"tableID",
				"table-id",
			),
		)
		if tableID is not None:
			field["table-id"] = tableID

		rowCount = self._asInt(
			self._getFirstValue(
				tableContext,
				(
					"nRows",
					"rowCount",
					"table-rowcount",
				),
			),
		)
		if rowCount is not None:
			field["table-rowcount"] = rowCount

		columnCount = self._asInt(
			self._getFirstValue(
				tableContext,
				(
					"nColumns",
					"columnCount",
					"table-columncount",
				),
			),
		)
		if columnCount is not None:
			field["table-columncount"] = columnCount

		return field

	def makeCellControlField(
		self,
		tableContext: dict,
		entry: dict,
	) -> object:
		textInfos, controlTypes = self._importFieldModules()

		field = textInfos.ControlField()
		field["role"] = controlTypes.Role.TABLECELL

		tableID = self._getFirstValue(
			entry,
			(
				"tableID",
				"table-id",
			),
		)
		if tableID is None:
			tableID = self._getFirstValue(
				tableContext,
				(
					"tableID",
					"table-id",
				),
			)
		if tableID is not None:
			field["table-id"] = tableID

		rowNumber = self._asInt(
			self._getFirstValue(
				entry,
				(
					"rowNumber",
					"row",
					"table-rownumber",
				),
			),
		)
		if rowNumber is not None:
			field["table-rownumber"] = rowNumber

		columnNumber = self._asInt(
			self._getFirstValue(
				entry,
				(
					"columnNumber",
					"column",
					"columnIndex",
					"col",
					"table-columnnumber",
				),
			),
		)
		if columnNumber is not None:
			field["table-columnnumber"] = columnNumber

		rowHeaderText = self._asText(
			self._getFirstValue(
				entry,
				(
					"rowHeaderText",
					"table-rowheadertext",
				),
			),
		)
		field["table-rowheadertext"] = rowHeaderText

		columnHeaderText = self._asText(
			self._getFirstValue(
				entry,
				(
					"columnHeaderText",
					"table-columnheadertext",
				),
			),
		)
		field["table-columnheadertext"] = columnHeaderText

		rowSpan = self._asInt(
			self._getFirstValue(
				entry,
				(
					"rowSpan",
					"table-rowsspanned",
				),
			),
		)
		if rowSpan is not None:
			field["table-rowsspanned"] = rowSpan

		columnSpan = self._asInt(
			self._getFirstValue(
				entry,
				(
					"columnSpan",
					"table-columnsspanned",
				),
			),
		)
		if columnSpan is not None:
			field["table-columnsspanned"] = columnSpan

		return field

	def makeControlStartCommands(
		self,
		tableContext: dict,
		entry: dict,
	) -> list:
		textInfos, _controlTypes = self._importFieldModules()

		tableField = self.makeTableControlField(tableContext)
		cellField = self.makeCellControlField(tableContext, entry)

		return [
			textInfos.FieldCommand("controlStart", tableField),
			textInfos.FieldCommand("controlStart", cellField),
		]

	def makeControlEndCommands(
		self,
	) -> list:
		textInfos, _controlTypes = self._importFieldModules()

		return [
			textInfos.FieldCommand("controlEnd", None),
			textInfos.FieldCommand("controlEnd", None),
		]

	def injectTableFieldsIntoFieldStream(
		self,
		fieldStream: list,
		tableContext: dict,
		entry: dict,
	) -> list:
		"""Return a field stream wrapped with table and cell control fields.

		The wrapper order is:

			table controlStart
			cell controlStart
			original field stream
			cell controlEnd
			table controlEnd

		This keeps the inner TextInfo responsible for text, bookmark, caret and
		object lifetime, while this helper only adds table semantics.
		"""
		return (
			self.makeControlStartCommands(
				tableContext,
				entry,
			)
			+ list(fieldStream)
			+ self.makeControlEndCommands()
		)

	def makeDebugSummary(
		self,
		tableContext: dict,
		entry: dict,
	) -> dict:
		tableField = self.makeTableControlField(tableContext)
		cellField = self.makeCellControlField(tableContext, entry)

		return {
			"tableFieldKeys": ",".join(sorted(str(key) for key in tableField.keys())),
			"cellFieldKeys": ",".join(sorted(str(key) for key in cellField.keys())),
			"tableID": cellField.get("table-id", tableField.get("table-id")),
			"rowNumber": cellField.get("table-rownumber"),
			"columnNumber": cellField.get("table-columnnumber"),
			"rowCount": tableField.get("table-rowcount"),
			"columnCount": tableField.get("table-columncount"),
			"rowSpan": cellField.get("table-rowsspanned"),
			"columnSpan": cellField.get("table-columnsspanned"),
			"rowHeaderText": cellField.get("table-rowheadertext", ""),
			"columnHeaderText": cellField.get("table-columnheadertext", ""),
		}

	def _importFieldModules(
		self,
	):
		import controlTypes
		import textInfos

		return textInfos, controlTypes

	def _getFirstValue(
		self,
		source: dict,
		keys: tuple,
	):
		if not isinstance(source, dict):
			return None

		for key in keys:
			if key not in source:
				continue
			value = source.get(key)
			if value is not None:
				return value

		return None

	def _asInt(
		self,
		value,
	):
		if value is None:
			return None

		try:
			return int(value)
		except Exception:
			return None

	def _asText(
		self,
		value,
	) -> str:
		if value is None:
			return ""

		try:
			return str(value)
		except Exception:
			return ""
