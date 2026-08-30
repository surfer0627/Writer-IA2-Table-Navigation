# -*- coding: UTF-8 -*-
from __future__ import annotations

import documentBase
from nvdaBuiltin.appModules import soffice as builtinSoffice

from .writerDocumentTableNavigationAdapter import WriterDocumentTableNavigationAdapter
from .writerTableNavCore import WriterIA2TableNavigator


class WriterTableNavigationSymphonyDocument(
	documentBase.DocumentWithTableNavigation,
	builtinSoffice.SymphonyDocument,
):
	"""SymphonyDocument with NVDA's standard document table navigation."""

	def _getWriterTableNavigator(self) -> WriterIA2TableNavigator:
		navigator = getattr(self, "_writerTableNavigator", None)
		if navigator is None:
			navigator = WriterIA2TableNavigator()
			self._writerTableNavigator = navigator
		return navigator

	def _getWriterDocumentTableNavigationAdapter(self) -> WriterDocumentTableNavigationAdapter:
		adapter = getattr(self, "_writerDocumentTableNavigationAdapter", None)
		if adapter is None:
			adapter = WriterDocumentTableNavigationAdapter(
				navigator=self._getWriterTableNavigator(),
			)
			self._writerDocumentTableNavigationAdapter = adapter
		return adapter

	def _getTableCellCoordsCached(self, info, axis=None):
		cell = super()._getTableCellCoordsCached(info, axis)

		# Writer can expose a false column span for a normal cell next to a
		# block-merged region. Only sanitize the span used by native
		# next-column movement; keep NVDA's cached row information unchanged.
		if axis != documentBase._Axis.COLUMN or cell.colSpan <= 1:
			return cell

		try:
			sourceObj = info.NVDAObjectAtStart
			navigator = self._getWriterTableNavigator()
			sourceCell = navigator.getNearestTableCellFromObject(
				sourceObj,
			)
			if sourceCell is None:
				return cell

			context = navigator.getContextFromObject(
				sourceCell,
			)
			if not context or not context.get("inTable"):
				return cell

			tableObj = context.get("tableObj")
			if tableObj is None:
				tableObj = getattr(
					sourceCell,
					"parent",
					None,
				)

			(
				_rowSpan,
				effectiveColumnSpan,
				_details,
			) = navigator._sanitizeSourceCellSpan(
				context,
				tableObj,
				direction="right",
			)
		except Exception:
			return cell

		if effectiveColumnSpan == cell.colSpan:
			return cell

		return documentBase._TableCell(
			cell.tableID,
			cell.row,
			cell.col,
			cell.rowSpan,
			effectiveColumnSpan,
		)

	def _getTableCellAt(self, tableID, startPos, row, column):
		adapter = self._getWriterDocumentTableNavigationAdapter()
		return adapter.getTableCellAt(tableID, startPos, row, column)
