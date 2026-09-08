import type { Column } from './DataTable'

/** Turns the visible columns and sorted rows into a CSV the browser downloads. */
export function downloadCsv<Row>(
  filename: string,
  columns: Column<Row>[],
  rows: Row[],
  cell: (row: Row, column: Column<Row>) => string | number | null | undefined,
): void {
  const escape = (value: string | number | null | undefined) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [
    columns.map((c) => escape(c.header)).join(','),
    ...rows.map((row) => columns.map((column) => escape(cell(row, column))).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
