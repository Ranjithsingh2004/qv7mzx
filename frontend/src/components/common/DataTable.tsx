import type { ReactNode } from 'react';
import './DataTable.css';

export interface Column<T> {
  key: string;
  header: string;
  /** Numeric columns are right-aligned and use tabular figures. */
  numeric?: boolean;
  render: (row: T) => ReactNode;
}

/**
 * A plain data table.
 *
 * Used both as a chart's accessible equivalent and as the settlement-period
 * detail view, so one implementation carries the alignment and figure rules.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  emptyMessage = 'No rows match the current filters.',
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  caption: string;
  emptyMessage?: string;
}) {
  return (
    <table className="dtable">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              scope="col"
              className={column.numeric ? 'dtable__th dtable__th--num' : 'dtable__th'}
            >
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td className="dtable__empty" colSpan={columns.length}>
              {emptyMessage}
            </td>
          </tr>
        ) : (
          rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.numeric ? 'dtable__td dtable__td--num tnum' : 'dtable__td'}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
