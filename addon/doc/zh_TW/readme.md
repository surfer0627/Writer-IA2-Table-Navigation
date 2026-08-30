# Writer IA2 Table Navigation

Writer IA2 Table Navigation 是一個實驗性的 NVDA 附加元件，用來在 Windows 上的 LibreOffice Writer 表格中移動與讀取內容。

這個專案使用 IAccessible2（IA2）處理 Writer 的表格結構，並探索 [nvaccess/nvda#4133](https://github.com/nvaccess/nvda/issues/4133) 的可能解法。

這不是 NVDA 官方版本，也不是 NVDA 核心中的正式修正。

## 系統需求

* NVDA 2025.3 或更新版本
* LibreOffice Writer 25.8.0.1 或更新版本

## 指令

當游標位於 LibreOffice Writer 表格內時，可以使用以下指令：

| 指令 | 功能 |
| --- | --- |
| `control+alt+leftArrow` | 移到前一欄 |
| `control+alt+rightArrow` | 移到下一欄 |
| `control+alt+upArrow` | 移到上一列 |
| `control+alt+downArrow` | 移到下一列 |
| `control+alt+pageUp` | 移到第一列 |
| `control+alt+pageDown` | 移到最後一列 |
| `control+alt+home` | 移到第一欄 |
| `control+alt+end` | 移到最後一欄 |
| `NVDA+control+alt+upArrow` | 由上往下垂直讀出目前欄，不移動系統游標 |
| `NVDA+control+alt+leftArrow` | 由左往右水平讀出目前列，不移動系統游標 |
| `NVDA+control+alt+rightArrow` | 從目前儲存格水平向右讀到此列的最後一個儲存格 |
| `NVDA+control+alt+downArrow` | 從目前儲存格垂直向下讀到此欄的最後一個儲存格 |
| `control+alt+r` | 從目前儲存格水平向右讀到此列的最後一個儲存格 |
| `control+alt+c` | 從目前儲存格垂直向下讀到此欄的最後一個儲存格 |

## 技術方式

目前的流程如下：

1. 找出目前所在的 Writer 表格儲存格。
2. 使用 `IAccessibleTableCell` 和 `IAccessibleTable2` 取得儲存格位置、跨列跨欄資訊與表格大小。
3. 計算要移動到的列與欄。
4. 找出包含該座標的 NVDA 表格儲存格物件。附加元件會先嘗試 `IAccessibleTable2.cellAt(row, column)`，必要時再使用快取的座標對應或掃描子物件。
5. 將焦點移到目標 `SymphonyIATableCell`。
6. 使用 Writer 目前的文字物件提供語音，並使用目前的 Symphony 段落提供點字顯示。

`SymphonyIATableCell` 主要用來處理表格結構與移動。

儲存格文字則主要從 Writer 目前的文字物件取得。

## 已知限制

目前已知限制包括：

* 只支援 LibreOffice Writer。
* 只支援 Windows。
* 尚未測試 OpenOffice。
* 尚未支援瀏覽模式中的表格快速導覽。
* 已處理合併儲存格，但仍需要更多不同文件的測試。

### 表格 Say All

Writer 的表格結構與文字內容來自不同的無障礙物件。

表格的列、欄與儲存格結構主要由 IA2 提供，而儲存格文字通常來自一個或多個 Symphony 段落。

因此，這個附加元件會：

1. 建立要朗讀的列或欄順序。
2. 為每個儲存格取得新的 TextInfo。
3. 加入需要的表格欄位資訊。
4. 將這些內容交給 NVDA 的原生 Say All 功能朗讀。

這一層主要是用來連接 Writer 的表格結構與文字內容。

如果未來 Writer 可以直接為每個表格儲存格提供穩定的 TextInfo，這部分程式可以再簡化。

## 測試與回報

如果遇到問題，請提供：

* NVDA 版本。
* LibreOffice 版本。
* Windows 版本。
* 使用了哪一個指令。
* 預期移動到哪個儲存格或讀到什麼內容。
* 實際發生什麼情況。
* 語音、點字、焦點與系統游標是否到達正確位置。
* 表格中是否有空白儲存格、合併儲存格、跨列跨欄或一個儲存格內有多個段落。

適合測試的文件包括：

* 一般表格。
* 有空白儲存格的表格。
* 水平合併儲存格。
* 垂直合併儲存格。
* 同時有跨列與跨欄的表格。
* 一個儲存格內有多個段落的表格。

## 建置

這個專案使用 [NVDA Add-on Template](https://github.com/nvaccess/AddonTemplate)。

安裝需要的建置工具後，在專案根目錄執行：

	scons

接著可以安裝產生的 `.nvda-addon` 檔案進行測試。
