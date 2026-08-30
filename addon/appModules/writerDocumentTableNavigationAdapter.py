# -*- coding: UTF-8 -*-
# A part of Writer IA2 Table Navigation for NVDA.

from __future__ import annotations

import textInfos
from compoundDocuments import CompoundTextLeafTextInfo

from .writerTableNavCore import WriterIA2TableNavigator


class WriterDocumentTableNavigationAdapter:
	"""Bridge Writer IA2 table coordinates to document-level TextInfos.

	This adapter converts the 1-based table coordinates used by
	DocumentWithTableNavigation into Writer's existing IA2 table target lookup,
	then represents the target cell using the real Writer text leaf inside a
	document-level SymphonyDocumentTextInfo.

	It does not move focus or update the document selection.
	"""

	def __init__(
		self,
		navigator: WriterIA2TableNavigator | None = None,
	):
		self._navigator = navigator if navigator is not None else WriterIA2TableNavigator()

	def getTableCellAt(
		self,
		tableID,
		startPos: textInfos.TextInfo,
		row: int,
		column: int,
	) -> textInfos.TextInfo:
		"""Return the document TextInfo for a Writer table cell.

		:param tableID:
			Table identifier supplied by DocumentWithTableNavigation.
			The current Writer CompoundTextInfo implementation exposes a native
			table-id which is not sufficient to locate a table globally, so the
			actual table is anchored from startPos instead.
		:param startPos:
			Document TextInfo inside the source table.
		:param row:
			One-based target row.
		:param column:
			One-based target column.
		:raises LookupError:
			If the source table, target cell, or target text leaf cannot be found.
		"""
		if not isinstance(row, int) or row < 1:
			raise LookupError(
				"Invalid target row",
			)

		if not isinstance(column, int) or column < 1:
			raise LookupError(
				"Invalid target column",
			)

		sourceObj = self._getStartObject(
			startPos,
		)

		context = self._getSourceContext(
			sourceObj,
		)

		targetRowIndex = row - 1
		targetColumnIndex = column - 1

		self._validateTargetCoordinate(
			context,
			targetRowIndex,
			targetColumnIndex,
		)

		targetCell = self._getTargetCell(
			context,
			targetRowIndex,
			targetColumnIndex,
		)

		(
			startLeaf,
			startLeafInfo,
			endLeaf,
			endLeafInfo,
		) = self._findTargetTextLeafRange(
			targetCell,
		)

		if startLeaf is None or startLeafInfo is None or endLeaf is None or endLeafInfo is None:
			raise LookupError(
				"Writer target table cell has no compound text leaf",
			)

		self._validateTargetLeafDocument(
			startPos,
			startLeaf,
		)

		if endLeaf is not startLeaf:
			self._validateTargetLeafDocument(
				startPos,
				endLeaf,
			)

		return self._buildDocumentTextInfo(
			startPos,
			startLeaf,
			startLeafInfo,
			endLeaf,
			endLeafInfo,
		)

	def _getStartObject(
		self,
		startPos: textInfos.TextInfo,
	) -> object:
		if startPos is None:
			raise LookupError(
				"Writer table start position is missing",
			)

		try:
			sourceObj = startPos.NVDAObjectAtStart
		except Exception as e:
			raise LookupError(
				"Unable to get the Writer object at the start position",
			) from e

		if sourceObj is None:
			raise LookupError(
				"Writer start position has no NVDAObject",
			)

		return sourceObj

	def _getSourceContext(
		self,
		sourceObj: object,
	) -> dict[str, object]:
		try:
			context = self._navigator.getContextFromObject(
				sourceObj,
			)
		except Exception as e:
			raise LookupError(
				"Unable to get Writer table context from the start position",
			) from e

		if not isinstance(context, dict):
			raise LookupError(
				"Writer table context is invalid",
			)

		if not context.get("inTable"):
			failReason = context.get("failReason") or context.get("failStage") or "notInTable"

			raise LookupError(
				f"Writer start position is not in a table: {failReason}",
			)

		if context.get("table2Obj") is None:
			raise LookupError(
				"Writer source table has no IAccessibleTable2 object",
			)

		return context

	def _validateTargetCoordinate(
		self,
		context: dict[str, object],
		targetRowIndex: int,
		targetColumnIndex: int,
	) -> None:
		nRows = context.get(
			"nRows",
		)
		nColumns = context.get(
			"nColumns",
		)

		if not isinstance(nRows, int) or not isinstance(nColumns, int) or nRows <= 0 or nColumns <= 0:
			raise LookupError(
				"Writer table dimensions are invalid",
			)

		if (
			targetRowIndex < 0
			or targetRowIndex >= nRows
			or targetColumnIndex < 0
			or targetColumnIndex >= nColumns
		):
			raise LookupError(
				"Writer target table coordinate is outside the table",
			)

	def _getTargetCell(
		self,
		context: dict[str, object],
		targetRowIndex: int,
		targetColumnIndex: int,
	) -> object:
		sourceRowIndex = context.get(
			"rowIndex",
		)
		sourceColumnIndex = context.get(
			"columnIndex",
		)
		sourceCellObj = context.get(
			"cellObj",
		)

		#
		# DocumentWithTableNavigation sometimes asks for the current cell
		# again, for example when refreshing the current table position.
		#
		# In that case the existing Writer target lookup must be allowed to
		# return the source cell. For a genuinely different coordinate, keep
		# sourceCellObj so the navigator's false-span protections remain active.
		#
		targetIsSourceCoordinate = sourceRowIndex == targetRowIndex and sourceColumnIndex == targetColumnIndex

		lookupSourceCellObj = None if targetIsSourceCoordinate else sourceCellObj

		try:
			(
				targetOk,
				targetCell,
				targetFailReason,
			) = self._navigator.getTargetNVDAObject(
				context.get(
					"table2Obj",
				),
				targetRowIndex,
				targetColumnIndex,
				tableObj=context.get(
					"tableObj",
				),
				sourceCellObj=lookupSourceCellObj,
			)
		except Exception as e:
			raise LookupError(
				"Writer target table lookup failed",
			) from e

		if not targetOk or targetCell is None:
			raise LookupError(
				targetFailReason or "Writer target table cell was not found",
			)

		return targetCell

	def _findTargetTextLeaf(
		self,
		targetCell: object,
	) -> tuple[
		object | None,
		CompoundTextLeafTextInfo | None,
	]:
		"""Find the real text leaf inside a Writer IA2 table cell."""
		queue: list[tuple[object, int]] = [
			(
				targetCell,
				0,
			),
		]
		seen: set[int] = set()

		while queue:
			obj, depth = queue.pop(0)

			if obj is None:
				continue

			objIdentity = id(
				obj,
			)

			if objIdentity in seen:
				continue

			seen.add(
				objIdentity,
			)

			#
			# A SymphonyIATableCell advertises a TextInfo class, but the
			# acceptance probes established the paragraph descendant as the
			# actual compound text leaf used by SymphonyDocument.
			#
			if obj is not targetCell:
				leafInfo = self._makeLeafTextInfo(
					obj,
				)

				if leafInfo is not None:
					return (
						obj,
						leafInfo,
					)

			if depth >= 8:
				continue

			for child in self._getChildren(
				obj,
			):
				queue.append(
					(
						child,
						depth + 1,
					),
				)

		return (
			None,
			None,
		)

	def _findTargetTextLeafRange(
		self,
		targetCell: object,
	) -> tuple[
		object | None,
		CompoundTextLeafTextInfo | None,
		object | None,
		CompoundTextLeafTextInfo | None,
	]:
		"""Return the first and last compound text leaves inside one Writer cell.

		TreeCompoundTextInfo walks between leaf objects using flowsTo. Start with
		the existing first-leaf lookup, then follow the same flow only while it
		remains inside the target cell.
		"""
		firstLeaf, firstInfo = self._findTargetTextLeaf(
			targetCell,
		)

		if firstLeaf is None or firstInfo is None:
			return (
				None,
				None,
				None,
				None,
			)

		lastLeaf = firstLeaf
		lastInfo = firstInfo
		currentLeaf = firstLeaf
		seen: set[int] = {
			id(firstLeaf),
		}

		for _ in range(1000):
			try:
				nextLeaf = getattr(
					currentLeaf,
					"flowsTo",
					None,
				)
			except Exception:
				break

			if nextLeaf is None:
				break

			nextIdentity = id(
				nextLeaf,
			)

			if nextIdentity in seen:
				break

			seen.add(
				nextIdentity,
			)

			if not self._isObjectInsideTargetCell(
				nextLeaf,
				targetCell,
			):
				break

			nextInfo = self._makeLeafTextInfo(
				nextLeaf,
			)

			if nextInfo is None:
				break

			lastLeaf = nextLeaf
			lastInfo = nextInfo
			currentLeaf = nextLeaf

		return (
			firstLeaf,
			firstInfo,
			lastLeaf,
			lastInfo,
		)

	def _isObjectInsideTargetCell(
		self,
		obj: object,
		targetCell: object,
	) -> bool:
		"""Return True while obj remains in the target cell's ancestry."""
		try:
			targetCellIA2UniqueID = getattr(
				targetCell,
				"IA2UniqueID",
				None,
			)
		except Exception:
			targetCellIA2UniqueID = None

		current = obj
		seen: set[int] = set()

		for _ in range(100):
			if current is None:
				return False

			if current is targetCell:
				return True

			if targetCellIA2UniqueID is not None:
				try:
					currentIA2UniqueID = getattr(
						current,
						"IA2UniqueID",
						None,
					)
				except Exception:
					currentIA2UniqueID = None

				if currentIA2UniqueID == targetCellIA2UniqueID:
					return True

			currentIdentity = id(
				current,
			)

			if currentIdentity in seen:
				return False

			seen.add(
				currentIdentity,
			)

			try:
				current = getattr(
					current,
					"parent",
					None,
				)
			except Exception:
				return False

		return False

	def _makeLeafTextInfo(
		self,
		obj: object,
	) -> CompoundTextLeafTextInfo | None:
		try:
			makeTextInfo = getattr(
				obj,
				"makeTextInfo",
				None,
			)
		except Exception:
			return None

		if not callable(
			makeTextInfo,
		):
			return None

		try:
			info = makeTextInfo(
				textInfos.POSITION_ALL,
			)
		except Exception:
			return None

		if not isinstance(
			info,
			CompoundTextLeafTextInfo,
		):
			return None

		return info

	def _getChildren(
		self,
		obj: object,
	) -> list[object]:
		try:
			children = getattr(
				obj,
				"children",
				None,
			)

			if children is not None:
				return list(
					children,
				)
		except Exception:
			pass

		try:
			childCount = int(
				getattr(
					obj,
					"childCount",
					0,
				)
				or 0
			)
		except Exception:
			childCount = 0

		children = []

		for index in range(
			childCount,
		):
			try:
				child = obj.getChild(
					index,
				)
			except Exception:
				child = None

			if child is not None:
				children.append(
					child,
				)

		return children

	def _validateTargetLeafDocument(
		self,
		startPos: textInfos.TextInfo,
		targetLeaf: object,
	) -> None:
		"""Ensure the target leaf belongs to the same compound document."""
		try:
			document = startPos.obj
		except Exception as e:
			raise LookupError(
				"Writer document object is unavailable",
			) from e

		if document is None:
			raise LookupError(
				"Writer document object is missing",
			)

		try:
			targetTreeInterceptor = getattr(
				targetLeaf,
				"treeInterceptor",
				None,
			)
		except Exception:
			targetTreeInterceptor = None

		if targetTreeInterceptor is document:
			return

		#
		# CompoundDocument also supports containment checking. Keep this as a
		# compatibility fallback in case the target object's treeInterceptor
		# reference is unavailable while its accessible ancestry is still part
		# of the same document.
		#
		try:
			if targetLeaf in document:
				return
		except Exception:
			pass

		raise LookupError(
			"Writer target text leaf does not belong to the source document",
		)

	def _buildDocumentTextInfo(
		self,
		startPos: textInfos.TextInfo,
		startLeaf: object,
		startLeafInfo: CompoundTextLeafTextInfo,
		endLeaf: object | None = None,
		endLeafInfo: CompoundTextLeafTextInfo | None = None,
	) -> textInfos.TextInfo:
		"""Wrap a Writer leaf range in the source document TextInfo.

		TreeCompoundTextInfo currently has no public constructor which accepts
		an arbitrary compound text leaf as a document position. Keep the private
		field compatibility bridge isolated in this method.
		"""
		try:
			documentInfo = startPos.copy()
		except Exception as e:
			raise LookupError(
				"Unable to copy the Writer document TextInfo",
			) from e

		if documentInfo is None:
			raise LookupError(
				"Writer document TextInfo copy is missing",
			)

		normalize = getattr(
			documentInfo,
			"_normalizeStartAndEnd",
			None,
		)

		if not callable(
			normalize,
		):
			raise LookupError(
				"Writer document TextInfo does not support the compound text bridge",
			)

		if endLeaf is None:
			endLeaf = startLeaf

		if endLeafInfo is None:
			endLeafInfo = startLeafInfo

		try:
			documentInfo._startObj = startLeaf
			documentInfo._endObj = endLeaf
			documentInfo._start = startLeafInfo
			documentInfo._end = endLeafInfo

			normalize()
		except Exception as e:
			raise LookupError(
				"Unable to build the Writer target document TextInfo",
			) from e

		return documentInfo
