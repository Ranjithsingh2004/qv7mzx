import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/client';
import { Badge } from '../common/Badge';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import { InfoHint } from '../common/InfoHint';
import { Legend } from '../common/Legend';
import { StatTile } from '../common/StatTile';
import { EmptyState, ErrorState, LoadingState } from '../common/States';
import { ControlBar } from '../ControlBar';
import type { AnalysisParams } from '../../api/types';

describe('StatTile', () => {
  it('renders its label, value and detail', () => {
    render(<StatTile label="MAE" value="2,039 MW" detail="18.1% of mean actual" />);
    expect(screen.getByText('MAE')).toBeInTheDocument();
    expect(screen.getByText('2,039 MW')).toBeInTheDocument();
    expect(screen.getByText('18.1% of mean actual')).toBeInTheDocument();
  });

  it('exposes a definition behind an accessible toggle', async () => {
    const user = userEvent.setup();
    render(<StatTile label="RMSE" value="2,505 MW" hint="Root mean squared error." />);
    const trigger = screen.getByRole('button', { name: 'About RMSE' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await user.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('note')).toHaveTextContent('Root mean squared error.');
  });
});

describe('InfoHint', () => {
  it('renders hint text as text, never as markup', async () => {
    const user = userEvent.setup();
    render(<InfoHint label="About it" text="<img src=x onerror=alert(1)>" />);
    await user.click(screen.getByRole('button', { name: 'About it' }));
    const note = screen.getByRole('note');
    // The string is escaped into a text node, so no element is created.
    expect(note).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(note.querySelector('img')).toBeNull();
  });
});

describe('Badge', () => {
  it('pairs a tone with a text label so state is never colour alone', () => {
    render(
      <Badge tone="warning" glyph="!">
        Excluded — published after cutoff
      </Badge>,
    );
    expect(screen.getByText(/Excluded/)).toBeInTheDocument();
  });
});

describe('Legend', () => {
  it('lists every series by name', () => {
    render(
      <Legend
        items={[
          { label: 'Actual', color: '#2a78d6', shape: 'line' },
          { label: 'Forecast', color: '#eb6834', shape: 'dashed-line' },
        ]}
      />,
    );
    expect(screen.getByText('Actual')).toBeInTheDocument();
    expect(screen.getByText('Forecast')).toBeInTheDocument();
  });
});

interface Row {
  hour: string;
  value: number | null;
}

const COLUMNS: Column<Row>[] = [
  { key: 'hour', header: 'Hour', render: (row) => row.hour },
  {
    key: 'value',
    header: 'Actual',
    numeric: true,
    render: (row) => (row.value === null ? '—' : `${row.value} MW`),
  },
];

describe('DataTable', () => {
  it('renders headers and rows', () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={[
          { hour: '00:00', value: 15366 },
          { hour: '01:00', value: 15681 },
        ]}
        rowKey={(row) => row.hour}
        caption="Hourly actuals"
      />,
    );
    expect(screen.getByRole('columnheader', { name: 'Hour' })).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(3); // header + 2
    expect(screen.getByText('15366 MW')).toBeInTheDocument();
  });

  it('shows a missing value as an em dash, not a zero', () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={[{ hour: '02:00', value: null }]}
        rowKey={(row) => row.hour}
        caption="Hourly actuals"
      />,
    );
    const row = screen.getAllByRole('row')[1];
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('shows an empty message when nothing matches', () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={[]}
        rowKey={(row) => row.hour}
        caption="Hourly actuals"
        emptyMessage="No hours match these filters."
      />,
    );
    expect(screen.getByText('No hours match these filters.')).toBeInTheDocument();
  });

  it('carries an accessible caption', () => {
    render(
      <DataTable columns={COLUMNS} rows={[]} rowKey={(row) => row.hour} caption="Hourly actuals" />,
    );
    expect(screen.getByRole('table', { name: 'Hourly actuals' })).toBeInTheDocument();
  });
});

describe('states', () => {
  it('announces loading to assistive technology', () => {
    render(<LoadingState />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders an empty state', () => {
    render(<EmptyState title="No matched hours" body="Widen the window." />);
    expect(screen.getByText('No matched hours')).toBeInTheDocument();
  });

  it('guides the user to the controls for an invalid-parameter error', () => {
    render(
      <ErrorState error={new ApiError('cutoff_time: out of range', 'invalid_request', 422)} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('cannot produce an analysis');
    expect(screen.getByText(/Adjust the controls/)).toBeInTheDocument();
    // Retrying the same bad input would just fail again.
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });

  it('offers a retry for an upstream failure', async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <ErrorState
        error={new ApiError('Elexon did not respond', 'upstream_unavailable', 502)}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Elexon BMRS could not be reached');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

const PARAMS: AnalysisParams = {
  decisionFrom: '2026-01-01',
  decisionTo: '2026-01-31',
  cutoffTime: '09:00',
  cutoffDaysBefore: 1,
  alignment: 'hourly_mean',
  mapeFloorMw: 100,
};

const MODES = {
  hourly_mean: 'Mean of the half-hourly settlement periods inside each hour',
  period_start: 'Only the settlement period starting exactly on the hour',
};

describe('ControlBar', () => {
  it('marks the matching date preset as pressed', () => {
    render(<ControlBar params={PARAMS} onChange={vi.fn()} alignmentModes={MODES} />);
    expect(screen.getByRole('button', { name: /January 2026/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: /First week/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('emits both dates when a preset is chosen', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlBar params={PARAMS} onChange={onChange} alignmentModes={MODES} />);
    await user.click(screen.getByRole('button', { name: /First week/ }));
    expect(onChange).toHaveBeenCalledWith({
      decisionFrom: '2026-01-01',
      decisionTo: '2026-01-07',
    });
  });

  it('emits a cutoff time change', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlBar params={PARAMS} onChange={onChange} alignmentModes={MODES} />);
    await user.selectOptions(screen.getByLabelText('Time (Europe/London)'), '17:00');
    expect(onChange).toHaveBeenCalledWith({ cutoffTime: '17:00' });
  });

  it('emits days-before as a number, not a string', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlBar params={PARAMS} onChange={onChange} alignmentModes={MODES} />);
    await user.selectOptions(screen.getByLabelText('Days before delivery'), '2');
    expect(onChange).toHaveBeenCalledWith({ cutoffDaysBefore: 2 });
  });

  it('states that the default cutoff is an assumption', () => {
    render(<ControlBar params={PARAMS} onChange={vi.fn()} alignmentModes={MODES} />);
    expect(screen.getByText(/documented assumption, not a market rule/)).toBeInTheDocument();
  });

  it('disables every control while the first load is in flight', () => {
    render(<ControlBar params={PARAMS} onChange={vi.fn()} alignmentModes={MODES} disabled />);
    expect(screen.getByRole('button', { name: /First week/ })).toBeDisabled();
    expect(screen.getByLabelText('Time (Europe/London)')).toBeDisabled();
  });
});
