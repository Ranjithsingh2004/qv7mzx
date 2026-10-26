import { useMemo, useState } from 'react';
import type { Analysis, AnalysisParams, PeriodRecord, RecordStatus } from '../../api/types';
import { csvExportUrl } from '../../api/client';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import {
  count,
  deliveryDayLabel,
  hours,
  londonDateTime,
  mw,
  signedMw,
} from '../../lib/format';
import './sections.css';

const PAGE_SIZE = 50;

const STATUS_LABEL: Record<RecordStatus, string> = {
  matched: 'Matched',
  no_eligible_forecast: 'Forecast published after cutoff',
  no_forecast_published: 'No forecast published',
  no_actual: 'No actual published',
};

type StatusFilter = 'all' | RecordStatus | 'unmatched' | 'largest';

/**
 * The auditable record: one row per target hour, with the forecast, the
 * publication time behind it, the outturn and the error.
 *
 * Unmatched hours are listed with their reason rather than filtered out, and
 * the CSV export is served by the API from the same analysis the table renders
 * — so an exported file and the screen cannot disagree.
 */
export function PeriodDetailSection({
  analysis,
  params,
  refreshing,
}: {
  analysis: Analysis;
  params: AnalysisParams;
  refreshing: boolean;
}) {
  const [day, setDay] = useState('all');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    let rows = analysis.records;
    if (day !== 'all') rows = rows.filter((row) => row.delivery_date === day);
    if (status === 'unmatched') rows = rows.filter((row) => row.status !== 'matched');
    else if (status === 'largest') {
      rows = [...rows]
        .filter((row) => row.error_mw !== null)
        .sort((a, b) => Math.abs(b.error_mw ?? 0) - Math.abs(a.error_mw ?? 0))
        .slice(0, 25);
    } else if (status !== 'all') rows = rows.filter((row) => row.status === status);
    return rows;
  }, [analysis.records, day, status]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const columns: Column<PeriodRecord>[] = [
    {
      key: 'target',
      header: 'Target hour (London)',
      render: (row) => londonDateTime(row.target_start),
    },
    {
      key: 'periods',
      header: 'Settlement periods',
      render: (row) =>
        row.settlement_periods.length > 0 ? row.settlement_periods.join(', ') : '—',
    },
    { key: 'actual', header: 'Actual', numeric: true, render: (row) => mw(row.actual_mw) },
    { key: 'forecast', header: 'Forecast', numeric: true, render: (row) => mw(row.forecast_mw) },
    { key: 'error', header: 'Error', numeric: true, render: (row) => signedMw(row.error_mw) },
    {
      key: 'publish',
      header: 'Forecast published (London)',
      render: (row) =>
        row.forecast_publish_time ? londonDateTime(row.forecast_publish_time) : '—',
    },
    {
      key: 'lead',
      header: 'Lead time',
      numeric: true,
      render: (row) => hours(row.horizon_hours),
    },
    {
      key: 'vintages',
      header: 'Vintages used / available',
      numeric: true,
      render: (row) => `${row.vintages_eligible} / ${row.vintages_available}`,
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) =>
        row.status === 'matched' ? (
          row.actual_partial ? (
            <Badge tone="warning" glyph="!">
              Partial actual
            </Badge>
          ) : (
            <Badge tone="good" glyph="✔">
              Matched
            </Badge>
          )
        ) : (
          <Badge tone="warning" glyph="!">
            {STATUS_LABEL[row.status]}
          </Badge>
        ),
    },
  ];

  return (
    <section className="section" id="detail" aria-labelledby="detail-heading">
      <div className="section__head">
        <h2 className="section__title" id="detail-heading">
          Settlement period detail
        </h2>
        <p className="section__lede">
          Every analysed hour, with the publication time of the forecast actually used. This is
          the audit trail behind the metrics — and the same rows the CSV export contains.
        </p>
      </div>

      <Card
        refreshing={refreshing}
        title={`${count(filtered.length)} of ${count(analysis.records.length)} hours`}
        subtitle={`Alignment: ${analysis.alignment_description.toLowerCase()}`}
        actions={
          <a
            className="button button--primary"
            href={csvExportUrl(params)}
            download
            data-testid="csv-link"
          >
            <span aria-hidden="true">↓</span> Export CSV
          </a>
        }
      >
        <div className="toolbar">
          <label className="field">
            <span className="field__label">Delivery day</span>
            <select
              className="field__input"
              value={day}
              onChange={(event) => {
                setDay(event.target.value);
                setPage(0);
              }}
            >
              <option value="all">All days</option>
              {analysis.daily.map((row) => (
                <option key={row.delivery_date} value={row.delivery_date}>
                  {deliveryDayLabel(row.delivery_date)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Show</span>
            <select
              className="field__input"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as StatusFilter);
                setPage(0);
              }}
            >
              <option value="all">All hours</option>
              <option value="largest">25 largest absolute errors</option>
              <option value="matched">Matched only</option>
              <option value="unmatched">Unmatched only</option>
              <option value="no_eligible_forecast">Forecast published after cutoff</option>
              <option value="no_actual">Missing actual</option>
            </select>
          </label>
        </div>

        <div className="detail__scroll">
          <DataTable
            columns={columns}
            rows={visible}
            rowKey={(row) => row.target_start}
            caption="Analysed target hours with forecast, actual, error and forecast publication time"
            emptyMessage="No hours match these filters. Try widening them."
          />
        </div>

        {pageCount > 1 && (
          <nav className="pager" aria-label="Table pages">
            <button
              type="button"
              className="button"
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              disabled={safePage === 0}
            >
              Previous
            </button>
            <span className="pager__label tnum">
              Page {safePage + 1} of {pageCount}
            </span>
            <button
              type="button"
              className="button"
              onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
              disabled={safePage >= pageCount - 1}
            >
              Next
            </button>
          </nav>
        )}

        <p className="section__note">
          The CSV carries every hour in the current decision window — including unmatched ones,
          with empty value columns and their status intact, so a gap stays visible in a
          spreadsheet instead of reading as zero generation.
        </p>
      </Card>
    </section>
  );
}
